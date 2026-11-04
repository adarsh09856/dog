"""Database client for managing knowledge base documents and chunks."""

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from loguru import logger
from sqlalchemy import delete, desc, func, select, text, update
from sqlalchemy.orm import selectinload

from api.db.base_client import BaseDBClient
from api.db.models import (
    KnowledgeBaseChunkModel,
    KnowledgeBaseDocumentModel,
    KnowledgeBaseWebsiteSourceModel,
    UserModel,
)


WEBSITE_SOURCE_LIMIT_PER_ORG = 5
WEBSITE_SOURCE_ORG_LOCK_KEY = 1263941715


class WebsiteSourceLimitError(Exception):
    """Raised when an organization already has the maximum active sources."""


class KnowledgeBaseClient(BaseDBClient):
    """Client for managing knowledge base documents and vector embeddings."""

    async def create_website_source(self, **values) -> KnowledgeBaseWebsiteSourceModel:
        async with self.async_session() as session:
            # Serialize source creation per organization so concurrent API calls
            # cannot exceed the retrieval scan ceiling.
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:organization_id, :lock_key)"),
                {
                    "organization_id": values["organization_id"],
                    "lock_key": WEBSITE_SOURCE_ORG_LOCK_KEY,
                },
            )
            active_count = await session.scalar(
                select(func.count(KnowledgeBaseWebsiteSourceModel.id)).where(
                    KnowledgeBaseWebsiteSourceModel.organization_id == values["organization_id"],
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                )
            )
            if active_count >= WEBSITE_SOURCE_LIMIT_PER_ORG:
                raise WebsiteSourceLimitError
            source = KnowledgeBaseWebsiteSourceModel(**values)
            session.add(source)
            await session.commit()
            await session.refresh(source)
            return source

    async def list_website_sources(self, organization_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(KnowledgeBaseWebsiteSourceModel.organization_id == organization_id)
                .order_by(desc(KnowledgeBaseWebsiteSourceModel.created_at))
            )
            return list(result.scalars().all())

    async def get_website_source(self, source_uuid: str, organization_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel).where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                )
            )
            return result.scalar_one_or_none()

    async def update_website_source(self, source_uuid: str, organization_id: int, **values):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel).where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                )
            )
            source = result.scalar_one_or_none()
            if source is None:
                return None
            for key, value in values.items():
                setattr(source, key, value)
            await session.commit()
            await session.refresh(source)
            return source

    async def update_website_source_for_document(self, document_id: int, *, succeeded: bool, error: str | None = None):
        """Complete/fail the source refresh after the KB document processor exits."""
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel).where(
                    KnowledgeBaseWebsiteSourceModel.document_id == document_id,
                )
            )
            source = result.scalar_one_or_none()
            if source is None:
                return
            now = func.now()
            if not source.is_active or source.status in ("paused", "deleted"):
                source.status = "deleted" if source.status == "deleted" else "paused"
                source.pending_etag = None
                source.pending_content_hash = None
                await session.commit()
                return
            source.status = "ready" if succeeded else "error"
            source.last_error = None if succeeded else (error or "Website content could not be indexed")[:500]
            if succeeded:
                completed_at = datetime.now(UTC)
                source.last_refreshed_at = completed_at
                source.next_refresh_at = completed_at + timedelta(hours=source.refresh_interval_hours)
                source.etag = source.pending_etag or source.etag
                source.content_hash = source.pending_content_hash or source.content_hash
                source.version = source.version + 1
            elif source.is_active:
                source.next_refresh_at = datetime.now(UTC) + timedelta(minutes=15)
            source.pending_etag = None
            source.pending_content_hash = None
            await session.commit()

    async def get_website_document_uuids_for_organization(self, organization_id: int) -> list[str]:
        """Return live website knowledge made available to every org agent."""
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseDocumentModel.document_uuid)
                .join(
                    KnowledgeBaseWebsiteSourceModel,
                    KnowledgeBaseWebsiteSourceModel.document_id == KnowledgeBaseDocumentModel.id,
                )
                .where(
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.status != "deleted",
                    KnowledgeBaseWebsiteSourceModel.available_to_all_agents.is_(True),
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active.is_(True),
                    KnowledgeBaseDocumentModel.full_text.is_not(None),
                )
                .order_by(desc(KnowledgeBaseWebsiteSourceModel.created_at))
                .limit(WEBSITE_SOURCE_LIMIT_PER_ORG)
            )
            return list(result.scalars().all())

    async def update_website_document_content_if_active(
        self, document_id: int, organization_id: int, full_text: str
    ) -> bool:
        """Atomically publish refreshed text only while its source remains active."""
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.document_id == document_id,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.status != "paused",
                )
                .with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return False
            document = await session.get(KnowledgeBaseDocumentModel, document_id)
            if document is None or document.organization_id != organization_id or not document.is_active:
                return False
            document.full_text = full_text
            await session.commit()
            return True

    async def claim_website_source_refresh(self, source_uuid: str, organization_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.status != "paused",
                )
                .with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return None
            stale_before = datetime.now(UTC) - timedelta(minutes=15)
            if source.status in ("crawling", "indexing") and source.last_refresh_started_at and source.last_refresh_started_at > stale_before:
                return False
            source.status = "crawling"
            source.last_refresh_started_at = datetime.now(UTC)
            source.last_error = None
            await session.commit()
            await session.refresh(source)
            return source

    async def get_due_website_sources(self, limit: int = 100):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.next_refresh_at <= func.now(),
                    KnowledgeBaseWebsiteSourceModel.status.notin_(("crawling", "indexing")),
                    KnowledgeBaseWebsiteSourceModel.status != "paused",
                )
                .order_by(KnowledgeBaseWebsiteSourceModel.next_refresh_at)
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_user_provider_id(self, user_id: int) -> str | None:
        async with self.async_session() as session:
            return await session.scalar(select(UserModel.provider_id).where(UserModel.id == user_id))

    async def update_website_document_snapshot(self, document_id: int, organization_id: int, *, file_size_bytes: int, file_hash: str):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseDocumentModel).where(
                    KnowledgeBaseDocumentModel.id == document_id,
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active.is_(True),
                )
            )
            document = result.scalar_one_or_none()
            if document is None:
                return None
            document.file_size_bytes = file_size_bytes
            document.file_hash = file_hash
            document.mime_type = "text/markdown"
            document.processing_status = "pending"
            document.processing_error = None
            await session.commit()
            await session.refresh(document)
            return document

    async def deactivate_website_source(self, source_uuid: str, organization_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel).where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                ).with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return None
            source.is_active = False
            source.status = "deleted"
            source.next_refresh_at = None
            if source.document_id:
                document = await session.get(KnowledgeBaseDocumentModel, source.document_id)
                if document:
                    document.is_active = False
                    document.archived_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(source)
            return source

    async def pause_website_source(self, source_uuid: str, organization_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.status != "deleted",
                )
                .with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return None
            source.status = "paused"
            source.next_refresh_at = None
            await session.commit()
            await session.refresh(source)
            return source

    async def resume_website_source(self, source_uuid: str, organization_id: int):
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.status != "deleted",
                )
                .with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return None
            if source.document_id:
                document = await session.get(KnowledgeBaseDocumentModel, source.document_id)
                if document is None or not document.is_active or document.organization_id != organization_id:
                    return None
            source.status = "pending"
            source.next_refresh_at = None
            await session.commit()
            await session.refresh(source)
            return source

    async def begin_website_source_indexing(
        self, source_uuid: str, organization_id: int, *, etag: str | None, content_hash: str
    ) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.status != "paused",
                    KnowledgeBaseWebsiteSourceModel.status != "deleted",
                )
                .with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return False
            source.status = "indexing"
            source.pending_etag = etag
            source.pending_content_hash = content_hash
            source.last_error = None
            await session.commit()
            return True

    async def finish_website_source_unchanged(
        self, source_uuid: str, organization_id: int, *, etag: str | None
    ) -> bool:
        async with self.async_session() as session:
            result = await session.execute(
                select(KnowledgeBaseWebsiteSourceModel)
                .where(
                    KnowledgeBaseWebsiteSourceModel.source_uuid == source_uuid,
                    KnowledgeBaseWebsiteSourceModel.organization_id == organization_id,
                    KnowledgeBaseWebsiteSourceModel.is_active.is_(True),
                    KnowledgeBaseWebsiteSourceModel.status != "paused",
                    KnowledgeBaseWebsiteSourceModel.status != "deleted",
                )
                .with_for_update()
            )
            source = result.scalar_one_or_none()
            if source is None:
                return False
            now = datetime.now(UTC)
            source.status = "ready"
            source.last_error = None
            source.last_refreshed_at = now
            source.next_refresh_at = now + timedelta(hours=source.refresh_interval_hours)
            source.etag = etag or source.etag
            await session.commit()
            return True

    async def create_document(
        self,
        organization_id: int,
        created_by: int,
        filename: str,
        file_size_bytes: int,
        file_hash: str,
        mime_type: str,
        source_url: Optional[str] = None,
        custom_metadata: Optional[dict] = None,
        docling_metadata: Optional[dict] = None,
        document_uuid: Optional[str] = None,
        retrieval_mode: str = "chunked",
    ) -> KnowledgeBaseDocumentModel:
        """Create a new knowledge base document record.

        Args:
            organization_id: ID of the organization
            created_by: ID of the user uploading the document
            filename: Name of the file
            file_size_bytes: Size of the file in bytes
            file_hash: SHA-256 hash of the file
            mime_type: MIME type of the file
            source_url: Optional URL if document was fetched from web
            custom_metadata: Optional custom metadata dictionary
            docling_metadata: Optional docling processing metadata
            document_uuid: Optional UUID to use (if not provided, one will be generated)

        Returns:
            The created KnowledgeBaseDocumentModel
        """
        async with self.async_session() as session:
            document = KnowledgeBaseDocumentModel(
                organization_id=organization_id,
                created_by=created_by,
                filename=filename,
                file_size_bytes=file_size_bytes,
                file_hash=file_hash,
                mime_type=mime_type,
                source_url=source_url,
                custom_metadata=custom_metadata or {},
                docling_metadata=docling_metadata or {},
                processing_status="pending",
                total_chunks=0,
                retrieval_mode=retrieval_mode,
            )

            # Use provided UUID or let the model generate one
            if document_uuid:
                document.document_uuid = document_uuid

            session.add(document)
            await session.commit()
            await session.refresh(document)

            logger.info(
                f"Created document '{filename}' ({document.document_uuid}) "
                f"for organization {organization_id}"
            )
            return document

    async def get_document_by_id(
        self,
        document_id: int,
    ) -> Optional[KnowledgeBaseDocumentModel]:
        """Get a document by its database ID.

        Args:
            document_id: The database ID of the document

        Returns:
            KnowledgeBaseDocumentModel if found, None otherwise
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.id == document_id
            )

            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_document_by_uuid(
        self,
        document_uuid: str,
        organization_id: int,
    ) -> Optional[KnowledgeBaseDocumentModel]:
        """Get a document by its UUID, scoped to organization.

        Args:
            document_uuid: The unique document UUID
            organization_id: ID of the organization

        Returns:
            KnowledgeBaseDocumentModel if found, None otherwise
        """
        async with self.async_session() as session:
            query = (
                select(KnowledgeBaseDocumentModel)
                .where(
                    KnowledgeBaseDocumentModel.document_uuid == document_uuid,
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active == True,
                )
                .options(selectinload(KnowledgeBaseDocumentModel.created_by_user))
            )

            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_document_by_hash(
        self,
        file_hash: str,
        organization_id: int,
    ) -> Optional[KnowledgeBaseDocumentModel]:
        """Check if a document with the same hash already exists.

        Returns the first matching document if multiple exist (can happen with duplicates).

        Args:
            file_hash: SHA-256 hash of the file
            organization_id: ID of the organization

        Returns:
            KnowledgeBaseDocumentModel if found, None otherwise
        """
        async with self.async_session() as session:
            query = (
                select(KnowledgeBaseDocumentModel)
                .where(
                    KnowledgeBaseDocumentModel.file_hash == file_hash,
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active == True,
                )
                .order_by(KnowledgeBaseDocumentModel.created_at.asc())
                .limit(1)
            )

            result = await session.execute(query)
            return result.scalars().first()

    async def get_documents_for_organization(
        self,
        organization_id: int,
        processing_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        search: Optional[str] = None,
    ) -> List[KnowledgeBaseDocumentModel]:
        """Get all documents for an organization.

        Args:
            organization_id: ID of the organization
            processing_status: Optional filter by status
            limit: Maximum number of documents to return
            offset: Number of documents to skip

        Returns:
            List of KnowledgeBaseDocumentModel instances
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.organization_id == organization_id,
                KnowledgeBaseDocumentModel.is_active == True,
            )

            if processing_status:
                query = query.where(
                    KnowledgeBaseDocumentModel.processing_status == processing_status
                )
            normalized_search = (search or "").strip()
            if normalized_search:
                query = query.where(
                    KnowledgeBaseDocumentModel.filename.ilike(f"%{normalized_search}%")
                )

            query = (
                query.order_by(
                    desc(KnowledgeBaseDocumentModel.created_at),
                    desc(KnowledgeBaseDocumentModel.id),
                )
                .limit(limit)
                .offset(offset)
            )

            result = await session.execute(query)
            return list(result.scalars().all())

    async def count_documents_for_organization(
        self,
        organization_id: int,
        processing_status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> int:
        """Count active organization documents using the list's filters."""
        filters = [
            KnowledgeBaseDocumentModel.organization_id == organization_id,
            KnowledgeBaseDocumentModel.is_active == True,
        ]
        if processing_status:
            filters.append(KnowledgeBaseDocumentModel.processing_status == processing_status)
        normalized_search = (search or "").strip()
        if normalized_search:
            filters.append(KnowledgeBaseDocumentModel.filename.ilike(f"%{normalized_search}%"))
        async with self.async_session() as session:
            count = await session.scalar(
                select(func.count(KnowledgeBaseDocumentModel.id)).where(*filters)
            )
            return int(count or 0)

    async def update_document_metadata(
        self,
        document_id: int,
        file_size_bytes: Optional[int] = None,
        file_hash: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> Optional[KnowledgeBaseDocumentModel]:
        """Update document file metadata.

        Args:
            document_id: ID of the document
            file_size_bytes: Optional file size in bytes
            file_hash: Optional SHA-256 hash of the file
            mime_type: Optional MIME type

        Returns:
            Updated KnowledgeBaseDocumentModel
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.id == document_id
            )
            result = await session.execute(query)
            document = result.scalar_one_or_none()

            if not document:
                return None

            if file_size_bytes is not None:
                document.file_size_bytes = file_size_bytes
            if file_hash is not None:
                document.file_hash = file_hash
            if mime_type is not None:
                document.mime_type = mime_type

            await session.commit()
            await session.refresh(document)

            logger.info(f"Updated document {document_id} metadata")
            return document

    async def update_document_status(
        self,
        document_id: int,
        status: str,
        error_message: Optional[str] = None,
        total_chunks: Optional[int] = None,
        docling_metadata: Optional[dict] = None,
    ) -> Optional[KnowledgeBaseDocumentModel]:
        """Update document processing status.

        Args:
            document_id: ID of the document
            status: New status (pending, processing, completed, failed)
            error_message: Optional error message if status is failed
            total_chunks: Optional total number of chunks
            docling_metadata: Optional docling metadata

        Returns:
            Updated KnowledgeBaseDocumentModel
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.id == document_id
            )
            result = await session.execute(query)
            document = result.scalar_one_or_none()

            if not document:
                return None

            document.processing_status = status
            if error_message:
                document.processing_error = error_message
            if total_chunks is not None:
                document.total_chunks = total_chunks
            if docling_metadata:
                document.docling_metadata = docling_metadata

            await session.commit()
            await session.refresh(document)

            logger.info(f"Updated document {document_id} status to {status}")
            return document

    async def create_chunks_batch(
        self,
        chunks: List[KnowledgeBaseChunkModel],
    ) -> List[KnowledgeBaseChunkModel]:
        """Create multiple chunks in a batch.

        Args:
            chunks: List of KnowledgeBaseChunkModel instances

        Returns:
            List of created chunks with IDs
        """
        async with self.async_session() as session:
            session.add_all(chunks)
            await session.commit()

            for chunk in chunks:
                await session.refresh(chunk)

            logger.info(f"Created {len(chunks)} chunks")
            return chunks

    async def replace_chunks_for_document(
        self,
        document_id: int,
        organization_id: int,
        chunks: List[KnowledgeBaseChunkModel],
    ) -> List[KnowledgeBaseChunkModel]:
        """Replace all chunks for a document with a new precomputed batch."""
        async with self.async_session() as session:
            await session.execute(
                delete(KnowledgeBaseChunkModel).where(
                    KnowledgeBaseChunkModel.document_id == document_id,
                    KnowledgeBaseChunkModel.organization_id == organization_id,
                )
            )
            session.add_all(chunks)
            await session.commit()

            for chunk in chunks:
                await session.refresh(chunk)

            logger.info(
                f"Replaced chunks for document {document_id}: {len(chunks)} chunks"
            )
            return chunks

    async def get_chunks_for_document(
        self,
        document_id: int,
        organization_id: int,
    ) -> List[KnowledgeBaseChunkModel]:
        """Get all chunks for a document.

        Args:
            document_id: ID of the document
            organization_id: ID of the organization (for authorization)

        Returns:
            List of KnowledgeBaseChunkModel instances
        """
        async with self.async_session() as session:
            query = (
                select(KnowledgeBaseChunkModel)
                .where(
                    KnowledgeBaseChunkModel.document_id == document_id,
                    KnowledgeBaseChunkModel.organization_id == organization_id,
                )
                .order_by(KnowledgeBaseChunkModel.chunk_index)
            )

            result = await session.execute(query)
            return list(result.scalars().all())

    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        organization_id: int,
        limit: int = 5,
        document_ids: Optional[List[int]] = None,
        document_uuids: Optional[List[str]] = None,
        embedding_model: Optional[str] = None,
    ) -> List[dict]:
        """Search for similar chunks using vector similarity.

        Returns top-k most similar chunks without any similarity threshold filtering.
        Filtering and reranking should be done at the application layer.

        Args:
            query_embedding: The query embedding vector
            organization_id: Organization ID for scoping
            limit: Maximum number of results to return
            document_ids: Optional list of document IDs to filter by
            document_uuids: Optional list of document UUIDs to filter by
            embedding_model: Optional embedding model to filter by (for dimension compatibility)

        Returns:
            List of dictionaries with chunk data and similarity scores, ordered by similarity (highest first)
        """
        async with self.async_session() as session:
            # Get the raw connection to execute directly with asyncpg
            # This avoids parameter binding issues with text() and asyncpg
            connection = await session.connection()
            raw_connection = await connection.get_raw_connection()

            # Build WHERE clause conditions (no similarity threshold)
            where_conditions = [
                "c.organization_id = $2",
                "d.is_active = true",
            ]
            params = [
                None,
                organization_id,
                limit,
            ]  # $1 will be embedding_str, $3 is limit
            param_index = 4  # Next available parameter index

            # Add document_ids filter if provided
            if document_ids:
                placeholders = ", ".join(
                    f"${param_index + i}" for i in range(len(document_ids))
                )
                where_conditions.append(f"c.document_id IN ({placeholders})")
                params.extend(document_ids)
                param_index += len(document_ids)

            # Add document_uuids filter if provided
            if document_uuids:
                placeholders = ", ".join(
                    f"${param_index + i}" for i in range(len(document_uuids))
                )
                where_conditions.append(f"d.document_uuid IN ({placeholders})")
                params.extend(document_uuids)
                param_index += len(document_uuids)

            # Add embedding_model filter if provided (for dimension compatibility)
            if embedding_model:
                where_conditions.append(f"c.embedding_model = ${param_index}")
                params.append(embedding_model)
                param_index += 1

            # Build the complete SQL query
            where_clause = " AND ".join(where_conditions)
            query_sql = f"""
                SELECT
                    c.id,
                    c.document_id,
                    c.chunk_text,
                    c.contextualized_text,
                    c.chunk_metadata,
                    c.chunk_index,
                    d.filename,
                    d.document_uuid,
                    1 - (c.embedding <=> $1::vector) as similarity
                FROM knowledge_base_chunks c
                JOIN knowledge_base_documents d ON c.document_id = d.id
                WHERE {where_clause}
                ORDER BY c.embedding <=> $1::vector
                LIMIT $3
            """

            # Convert embedding to string format for PostgreSQL vector type
            embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
            params[0] = embedding_str  # Set $1

            # Execute query directly with asyncpg
            rows = await raw_connection.driver_connection.fetch(
                query_sql,
                *params,
            )

            # Convert asyncpg records to dictionaries
            return [dict(row) for row in rows]

    async def update_document_full_text(
        self,
        document_id: int,
        full_text: str,
    ) -> None:
        """Store full document text for full_document retrieval mode.

        Args:
            document_id: ID of the document
            full_text: The full extracted text content
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.id == document_id
            )
            result = await session.execute(query)
            document = result.scalar_one_or_none()
            if document:
                document.full_text = full_text
                await session.commit()
                logger.info(
                    f"Stored full text for document {document_id} ({len(full_text)} chars)"
                )

    async def get_full_text_documents(
        self,
        organization_id: int,
        document_uuids: List[str],
    ) -> List[KnowledgeBaseDocumentModel]:
        """Get full_document mode documents by their UUIDs.

        Args:
            organization_id: Organization ID for scoping
            document_uuids: List of document UUIDs to fetch

        Returns:
            List of documents with retrieval_mode='full_document' and full_text set

        Filters on ``full_text`` rather than ``processing_status``: processing
        only overwrites ``full_text`` on success, so a document being
        re-indexed after an edit (or whose re-index failed) keeps serving its
        last good text instead of dropping out of retrieval.
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.organization_id == organization_id,
                KnowledgeBaseDocumentModel.document_uuid.in_(document_uuids),
                KnowledgeBaseDocumentModel.retrieval_mode == "full_document",
                KnowledgeBaseDocumentModel.is_active == True,
                KnowledgeBaseDocumentModel.full_text.is_not(None),
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def claim_document_for_content_update(
        self,
        document_uuid: str,
        organization_id: int,
        expected_file_hash: str,
        file_hash: str,
        file_size_bytes: int,
    ) -> KnowledgeBaseDocumentModel | None:
        """Atomically mark an idle document ``pending`` for new content.

        Matches only while the document is still at ``expected_file_hash`` and
        no processing job is queued or running, so two concurrent saves cannot
        both win and a save cannot race a job still reading the old file.
        Returns None when that guard fails.
        """
        async with self.async_session() as session:
            result = await session.execute(
                update(KnowledgeBaseDocumentModel)
                .where(
                    KnowledgeBaseDocumentModel.document_uuid == document_uuid,
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active == True,
                    KnowledgeBaseDocumentModel.file_hash == expected_file_hash,
                    KnowledgeBaseDocumentModel.processing_status.not_in(
                        ("pending", "processing")
                    ),
                )
                .values(
                    processing_status="pending",
                    processing_error=None,
                    file_hash=file_hash,
                    file_size_bytes=file_size_bytes,
                )
                .returning(KnowledgeBaseDocumentModel)
                .execution_options(synchronize_session=False)
            )
            document = result.scalar_one_or_none()
            await session.commit()
            if document is not None:
                await session.refresh(document)
            return document

    async def restore_document_after_failed_content_update(
        self,
        document_id: int,
        organization_id: int,
        processing_status: str,
        processing_error: str | None,
        file_hash: str,
        file_size_bytes: int | None,
    ) -> None:
        """Undo ``claim_document_for_content_update`` when the new file never
        reached storage, putting back the pre-claim status and file metadata."""
        async with self.async_session() as session:
            await session.execute(
                update(KnowledgeBaseDocumentModel)
                .where(
                    KnowledgeBaseDocumentModel.id == document_id,
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                )
                .values(
                    processing_status=processing_status,
                    processing_error=processing_error,
                    file_hash=file_hash,
                    file_size_bytes=file_size_bytes,
                )
            )
            await session.commit()

    async def delete_document(
        self,
        document_uuid: str,
        organization_id: int,
    ) -> bool:
        """Soft delete a document by setting is_active to False.

        This will also cascade delete all chunks via the database foreign key.

        Args:
            document_uuid: The unique document UUID
            organization_id: ID of the organization (for authorization)

        Returns:
            True if document was deleted, False if not found
        """
        async with self.async_session() as session:
            query = select(KnowledgeBaseDocumentModel).where(
                KnowledgeBaseDocumentModel.document_uuid == document_uuid,
                KnowledgeBaseDocumentModel.organization_id == organization_id,
            )

            result = await session.execute(query)
            document = result.scalar_one_or_none()

            if not document:
                return False

            document.is_active = False
            await session.commit()

            logger.info(
                f"Deleted document {document_uuid} for organization {organization_id}"
            )
            return True

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Compute SHA-256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            SHA-256 hash as hex string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def get_mime_type(file_path: str) -> str:
        """Get MIME type based on file extension.

        Args:
            file_path: Path to the file

        Returns:
            MIME type string
        """
        extension = Path(file_path).suffix.lower()
        mime_types = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".txt": "text/plain",
            ".json": "application/json",
            ".html": "text/html",
            ".md": "text/markdown",
        }
        return mime_types.get(extension, "application/octet-stream")
