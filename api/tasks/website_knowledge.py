"""Bounded refresh and schedule sweep for tenant website knowledge sources."""

import asyncio
import os
import tempfile
from datetime import UTC, datetime, timedelta

import aiofiles
from loguru import logger

from api.db import db_client
from api.services.storage import storage_fs
from api.services.website_knowledge_crawler import (
    MAX_PROCESSED_TEXT_BYTES,
    CrawlError,
    crawl_website,
)
from api.tasks.function_names import FunctionNames


async def refresh_knowledge_base_website(ctx, source_uuid: str, organization_id: int):
    source = await db_client.claim_website_source_refresh(source_uuid, organization_id)
    if source is None or source is False:
        return
    document = await db_client.get_document_by_id(source.document_id) if source.document_id else None
    if document and (document.organization_id != organization_id or not document.is_active):
        await db_client.update_website_source(source_uuid, organization_id, status="error", last_error="The linked knowledge document is unavailable")
        return
    temp_path = None
    try:
        result = await asyncio.to_thread(crawl_website, source.origin, max_pages=source.max_pages)
        current_source = await db_client.get_website_source(source_uuid, organization_id)
        if current_source is None or not current_source.is_active or current_source.status == "paused":
            return {"status": "paused", "pages": 0}
        if result.content_hash == source.content_hash and document is not None:
            await db_client.finish_website_source_unchanged(
                source_uuid, organization_id, etag=result.etag
            )
            return {"status": "unchanged", "pages": result.page_count}

        safe_key_prefix = f"knowledge_base/{organization_id}/website-{source.source_uuid}"
        s3_key = f"{safe_key_prefix}/website.md"
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as temp_file:
            temp_path = temp_file.name
        async with aiofiles.open(temp_path, "w", encoding="utf-8", newline="\n") as output:
            await output.write(result.text)
        size = os.path.getsize(temp_path)
        if size > MAX_PROCESSED_TEXT_BYTES:
            raise CrawlError("Processed website text exceeds the knowledge base limit")
        if not await storage_fs.aupload_file(temp_path, s3_key):
            raise RuntimeError("Website content could not be stored")

        if document is None:
            document = await db_client.create_document(
                organization_id=organization_id,
                created_by=source.created_by,
                filename=f"website-{source.source_uuid}.md",
                file_size_bytes=size,
                file_hash=result.content_hash,
                mime_type="text/markdown",
                source_url=source.origin,
                custom_metadata={"s3_key": s3_key, "website_source_uuid": source.source_uuid},
                retrieval_mode="full_document",
            )
            await db_client.update_website_source(
                source_uuid, organization_id, document_id=document.id
            )
        else:
            updated_document = await db_client.update_website_document_snapshot(
                document.id, organization_id, file_size_bytes=size, file_hash=result.content_hash
            )
            if updated_document is None:
                raise CrawlError("The linked knowledge document was removed")

        may_index = await db_client.begin_website_source_indexing(
            source_uuid,
            organization_id,
            etag=result.etag,
            content_hash=result.content_hash,
        )
        if not may_index:
            return {"status": "paused", "pages": 0}
        current_source = await db_client.get_website_source(source_uuid, organization_id)
        if current_source is None or not current_source.is_active or current_source.status == "paused":
            return {"status": "paused", "pages": 0}
        provider_id = await db_client.get_user_provider_id(source.created_by)
        if not provider_id:
            raise RuntimeError("Website source owner is unavailable")
        await ctx["redis"].enqueue_job(
            FunctionNames.PROCESS_KNOWLEDGE_BASE_DOCUMENT,
            document.id,
            s3_key,
            organization_id,
            provider_id,
            128,
            "full_document",
        )
        return {"status": "indexing", "pages": result.page_count}
    except Exception as exc:
        # Errors describe protocol/state only; never log crawled content.
        message = str(exc) if isinstance(exc, CrawlError) else "Website refresh failed during fetch, storage, or indexing setup"
        logger.warning("Website source refresh failed for source_uuid={} org={}: {}", source_uuid, organization_id, message)
        current_source = await db_client.get_website_source(source_uuid, organization_id)
        if current_source and current_source.is_active and current_source.status != "paused":
            await db_client.update_website_source(
                source_uuid,
                organization_id,
                status="error",
                last_error=message[:500],
                next_refresh_at=datetime.now(UTC) + timedelta(minutes=15),
                pending_etag=None,
                pending_content_hash=None,
            )
        raise
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.warning("Could not clean up temporary website crawl file")


async def sweep_website_knowledge_sources(ctx):
    sources = await db_client.get_due_website_sources(limit=100)
    queued = 0
    for source in sources:
        try:
            await ctx["redis"].enqueue_job(
                FunctionNames.REFRESH_KNOWLEDGE_BASE_WEBSITE,
                source.source_uuid,
                source.organization_id,
            )
            queued += 1
        except Exception:
            logger.exception("Could not enqueue due website knowledge refresh")
    return {"queued": queued}
