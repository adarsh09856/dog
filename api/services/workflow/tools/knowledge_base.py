"""Knowledge Base retrieval tool for workflow execution.

This module provides vector similarity search capabilities for retrieving
relevant information from the knowledge base during conversations.

Implements OpenTelemetry tracing for observability in Langfuse.
"""

import json
import re
from typing import Any, Dict, List, Optional

from loguru import logger
from opentelemetry import trace
from pipecat.utils.tracing.langfuse_helpers import mark_trace_public

from api.db import db_client
from api.services.gen_ai import build_embedding_service
from api.services.pipecat.tracing_config import ensure_tracing

MAX_WEBSITE_RETRIEVAL_PASSAGES = 5
MAX_WEBSITE_RETRIEVAL_CHARS = 4000


async def get_agent_knowledge_document_uuids(
    organization_id: int,
    attached_document_uuids: Optional[List[str]] = None,
    shared_document_uuids: Optional[List[str]] = None,
) -> list[str]:
    """Merge workflow attachments with org-shared website sources safely."""
    shared = shared_document_uuids
    if shared is None:
        shared = await db_client.get_website_document_uuids_for_organization(organization_id)
    return list(dict.fromkeys([*(attached_document_uuids or []), *shared]))


def _website_text_matches(query: str, full_text: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """Return a few query-relevant website passages, never the whole crawl."""
    tokens = re.findall(r"[\w\u0900-\u097f]+", query.casefold())
    stop_words = {"the", "is", "a", "an", "what", "how", "when", "where", "who", "do", "does", "can", "you", "your", "and", "or", "of", "to", "in", "का", "की", "के", "है", "क्या", "में", "को", "और", "से"}
    query_terms = {token for token in tokens if len(token) > 1 and token not in stop_words}
    if not query_terms:
        query_terms = {token for token in tokens if len(token) > 1}
    if not query_terms:
        return []

    pages = re.split(r"(?=Source:\s+https://)", full_text)
    passages: list[dict[str, Any]] = []
    for page in pages:
        if not page.strip():
            continue
        lines = page.splitlines()
        source = lines[0].removeprefix("Source:").strip() if lines and lines[0].startswith("Source:") else "Website source"
        body = "\n".join(lines[1:]) if lines and lines[0].startswith("Source:") else page
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?।])\s+|\n+", body) if sentence.strip()]
        # Keep passages to roughly 1,000 characters for useful context while
        # bounding the total website material sent to the language model.
        current: list[str] = []
        current_size = 0
        for sentence in sentences:
            for start in range(0, len(sentence), 900):
                part = sentence[start : start + 900]
                if current and current_size + len(part) > 1000:
                    text = " ".join(current)
                    words = set(re.findall(r"[\w\u0900-\u097f]+", text.casefold()))
                    hits = query_terms & words
                    if hits:
                        passages.append({"text": text, "filename": source, "similarity": len(hits) / len(query_terms), "chunk_index": len(passages)})
                    current, current_size = [], 0
                current.append(part)
                current_size += len(part) + 1
        if current:
            text = " ".join(current)
            words = set(re.findall(r"[\w\u0900-\u097f]+", text.casefold()))
            hits = query_terms & words
            if hits:
                passages.append({"text": text, "filename": source, "similarity": len(hits) / len(query_terms), "chunk_index": len(passages)})
    passages.sort(key=lambda item: item["similarity"], reverse=True)
    return passages[:limit]


async def retrieve_from_knowledge_base(
    query: str,
    organization_id: int,
    document_uuids: Optional[List[str]] = None,
    limit: int = 3,
    embeddings_api_key: Optional[str] = None,
    embeddings_model: Optional[str] = None,
    embeddings_base_url: Optional[str] = None,
    embeddings_provider: Optional[str] = None,
    embeddings_endpoint: Optional[str] = None,
    embeddings_api_version: Optional[str] = None,
    correlation_id: Optional[str] = None,
    tracing_context=None,
) -> Dict[str, Any]:
    """Retrieve relevant information from the knowledge base using vector similarity search.

    Uses OpenAI text-embedding-3-small for embeddings by default. This provides
    high-quality 1536-dimensional embeddings for accurate retrieval.

    This function includes OpenTelemetry tracing for Langfuse observability.

    Args:
        query: The search query to find relevant information
        organization_id: Organization ID for scoping the search
        document_uuids: Optional list of document UUIDs to filter by
        limit: Maximum number of chunks to return (default: 3)
        embeddings_api_key: Optional API key for embedding service
        embeddings_model: Optional model ID for embedding service
        embeddings_base_url: Optional base URL for embedding service
        tracing_context: Optional OpenTelemetry context for tracing

    Returns:
        Dictionary containing:
        - chunks: List of relevant text chunks with metadata
        - query: The original query
        - total_results: Number of results returned
    """
    # Create span for retrieval operation if tracing is enabled
    if ensure_tracing():
        try:
            parent_context = tracing_context

            # Get tracer
            tracer = trace.get_tracer("pipecat")
        except Exception as e:
            logger.debug(f"Failed to setup tracing context: {e}")
            # Fall back to non-traced execution
            return await _perform_retrieval(
                query,
                organization_id,
                document_uuids,
                limit,
                embeddings_api_key,
                embeddings_model,
                embeddings_base_url,
                embeddings_provider,
                embeddings_endpoint,
                embeddings_api_version,
                correlation_id,
            )

        # Create span with parent context
        if parent_context:
            with tracer.start_as_current_span(
                "knowledge_base_retrieval", context=parent_context
            ) as span:
                try:
                    mark_trace_public(span)

                    # Add operation metadata
                    span.set_attribute(
                        "gen_ai.operation.name", "knowledge_base_retrieval"
                    )
                    span.set_attribute("retrieval.query", query)
                    span.set_attribute("retrieval.limit", limit)
                    span.set_attribute("retrieval.organization_id", organization_id)

                    # Add document filter info
                    if document_uuids:
                        span.set_attribute(
                            "retrieval.document_count", len(document_uuids)
                        )
                        span.set_attribute(
                            "retrieval.document_uuids", json.dumps(document_uuids)
                        )

                    # Perform the actual retrieval
                    result = await _perform_retrieval(
                        query,
                        organization_id,
                        document_uuids,
                        limit,
                        embeddings_api_key,
                        embeddings_model,
                        embeddings_base_url,
                        embeddings_provider,
                        embeddings_endpoint,
                        embeddings_api_version,
                        correlation_id,
                    )

                    # Add result metadata to span
                    span.set_attribute(
                        "retrieval.results_count", result["total_results"]
                    )

                    if result.get("error"):
                        span.set_attribute("retrieval.error", result["error"])
                        span.set_status(
                            trace.Status(trace.StatusCode.ERROR, result["error"])
                        )
                    else:
                        # Add similarity scores
                        if result["chunks"]:
                            similarities = [
                                chunk["similarity"] for chunk in result["chunks"]
                            ]
                            span.set_attribute(
                                "retrieval.avg_similarity",
                                round(sum(similarities) / len(similarities), 4),
                            )
                            span.set_attribute(
                                "retrieval.max_similarity", max(similarities)
                            )
                            span.set_attribute(
                                "retrieval.min_similarity", min(similarities)
                            )

                        # Add retrieved documents info
                        filenames = list(
                            set(chunk["filename"] for chunk in result["chunks"])
                        )
                        span.set_attribute(
                            "retrieval.source_files", json.dumps(filenames)
                        )

                        # Add output as JSON for Langfuse
                        output_data = {
                            "query": query,
                            "chunks_retrieved": len(result["chunks"]),
                            "chunks": [
                                {
                                    "text": chunk["text"][:200] + "..."
                                    if len(chunk["text"]) > 200
                                    else chunk["text"],
                                    "filename": chunk["filename"],
                                    "similarity": chunk["similarity"],
                                }
                                for chunk in result["chunks"]
                            ],
                        }
                        span.set_attribute("output", json.dumps(output_data))

                    return result

                except Exception as e:
                    logger.error(f"Error in traced retrieval: {e}")
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
        else:
            # No parent context - perform retrieval without tracing
            logger.debug(
                "No parent context available for knowledge base retrieval tracing"
            )
            return await _perform_retrieval(
                query,
                organization_id,
                document_uuids,
                limit,
                embeddings_api_key,
                embeddings_model,
                embeddings_base_url,
                embeddings_provider,
                embeddings_endpoint,
                embeddings_api_version,
                correlation_id,
            )
    else:
        # Tracing is disabled - perform retrieval without tracing
        return await _perform_retrieval(
            query,
            organization_id,
            document_uuids,
            limit,
            embeddings_api_key,
            embeddings_model,
            embeddings_base_url,
            embeddings_provider,
            embeddings_endpoint,
            embeddings_api_version,
            correlation_id,
        )


async def _perform_retrieval(
    query: str,
    organization_id: int,
    document_uuids: Optional[List[str]],
    limit: int,
    embeddings_api_key: Optional[str] = None,
    embeddings_model: Optional[str] = None,
    embeddings_base_url: Optional[str] = None,
    embeddings_provider: Optional[str] = None,
    embeddings_endpoint: Optional[str] = None,
    embeddings_api_version: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal function to perform the actual retrieval operation.

    Separated from tracing logic for cleaner code organization.
    Handles both chunked (vector search) and full_document (full text) modes.
    """
    try:
        chunks = []
        website_chunks: list[dict[str, Any]] = []

        # Check for full_document mode documents and return their full text
        if document_uuids:
            full_text_docs = await db_client.get_full_text_documents(
                organization_id=organization_id,
                document_uuids=document_uuids,
            )
            for doc in full_text_docs:
                if doc.full_text:
                    if (doc.custom_metadata or {}).get("website_source_uuid"):
                        website_chunks.extend(_website_text_matches(query, doc.full_text, limit=3))
                    else:
                        chunks.append(
                            {
                                "text": doc.full_text,
                                "filename": doc.filename,
                                "similarity": 1.0,
                                "chunk_index": 0,
                            }
                        )

            # Filter out full_document UUIDs so vector search only hits chunked docs
            full_doc_uuids = {doc.document_uuid for doc in full_text_docs}
            chunked_uuids = [u for u in document_uuids if u not in full_doc_uuids]
        else:
            chunked_uuids = document_uuids

        # Perform vector similarity search on chunked documents
        if chunked_uuids is None or len(chunked_uuids) > 0:
            if not embeddings_api_key:
                raise ValueError(
                    "Embeddings API key not configured. Please set your API key in "
                    "Model Configurations > Embedding."
                )

            # Search runs inside a workflow run: reuse the run's MPS correlation
            # id. The Kodewaves-managed path forwards it via request metadata.
            embedding_service = await build_embedding_service(
                db_client=db_client,
                organization_id=organization_id,
                provider=embeddings_provider,
                api_key=embeddings_api_key,
                model=embeddings_model,
                base_url=embeddings_base_url,
                endpoint=embeddings_endpoint,
                api_version=embeddings_api_version,
                correlation_id=correlation_id,
            )

            results = await embedding_service.search_similar_chunks(
                query=query,
                organization_id=organization_id,
                limit=limit,
                document_uuids=chunked_uuids if chunked_uuids else None,
            )

            for result in results:
                chunk_info = {
                    "text": result.get("contextualized_text")
                    or result.get("chunk_text"),
                    "filename": result.get("filename"),
                    "similarity": round(result.get("similarity", 0), 4),
                    "chunk_index": result.get("chunk_index"),
                }
                chunks.append(chunk_info)

        # The workflow engine may attach many organization-wide website
        # sources. Apply one global context budget across all of them rather
        # than allowing each source to contribute its own top-k allowance.
        website_chunks.sort(key=lambda item: item["similarity"], reverse=True)
        website_budget = MAX_WEBSITE_RETRIEVAL_CHARS
        for passage in website_chunks[:MAX_WEBSITE_RETRIEVAL_PASSAGES]:
            if website_budget <= 0:
                break
            text = passage["text"][:website_budget]
            if text:
                chunks.append({**passage, "text": text})
                website_budget -= len(text)

        logger.info(
            f"Knowledge base retrieval: query='{query}', "
            f"results={len(chunks)}, "
            f"document_filter={document_uuids}"
        )

        return {
            "chunks": chunks,
            "query": query,
            "total_results": len(chunks),
        }

    except Exception as e:
        logger.error(f"Error retrieving from knowledge base: {e}")
        return {
            "error": str(e),
            "chunks": [],
            "query": query,
            "total_results": 0,
        }


def get_knowledge_base_tool(
    document_uuids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get knowledge base retrieval tool definition for LLM function calling.

    Args:
        document_uuids: Optional list of document UUIDs to include in description

    Returns:
        Tool definition compatible with LLM function calling
    """
    # Build description based on whether specific documents are filtered
    if document_uuids and len(document_uuids) > 0:
        description = (
            "Retrieve relevant information from the knowledge base documents available to this organization. "
            "Use this tool when you need to look up facts, policies, procedures, or any information "
            "that might be stored in the available documents, including workflow attachments and "
            f"organization-shared website sources ({len(document_uuids)} document(s) available)."
        )
    else:
        description = (
            "Retrieve relevant information from the knowledge base. "
            "Use this tool when you need to look up facts, policies, procedures, or any information "
            "that might be stored in the knowledge base documents."
        )

    return {
        "type": "function",
        "function": {
            "name": "retrieve_from_knowledge_base",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query to find relevant information. "
                            "Be specific and use natural language. "
                            "Example: 'What is the refund policy for canceled orders?'"
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    }
