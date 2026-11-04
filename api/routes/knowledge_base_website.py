"""Authenticated organization-scoped website knowledge source endpoints."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from urllib.parse import urlsplit

from api.db import db_client
from api.db.knowledge_base_client import WEBSITE_SOURCE_LIMIT_PER_ORG, WebsiteSourceLimitError
from api.schemas.website_knowledge import WebsiteSourceCreate, WebsiteSourceList, WebsiteSourceResponse
from api.services.auth.depends import get_user
from api.services.website_knowledge_crawler import CrawlError, _vetted_addresses, canonical_origin
from api.tasks.arq import enqueue_job
from api.tasks.function_names import FunctionNames

router = APIRouter(prefix="/knowledge-base/website-sources", tags=["knowledge-base"])


async def _response(source) -> WebsiteSourceResponse:
    document_uuid = None
    if source.document_id:
        document = await db_client.get_document_by_id(source.document_id)
        if document and document.organization_id == source.organization_id:
            document_uuid = document.document_uuid
    return WebsiteSourceResponse(
        source_uuid=source.source_uuid,
        url=source.origin,
        status=source.status,
        is_active=source.is_active,
        available_to_all_agents=source.available_to_all_agents,
        refresh_interval_hours=source.refresh_interval_hours,
        max_pages=source.max_pages,
        last_refresh_started_at=source.last_refresh_started_at,
        last_refreshed_at=source.last_refreshed_at,
        next_refresh_at=source.next_refresh_at,
        last_error=source.last_error,
        etag=source.etag,
        content_hash=source.content_hash,
        version=source.version,
        document_uuid=document_uuid,
    )


@router.post("", response_model=WebsiteSourceResponse, status_code=status.HTTP_202_ACCEPTED)
async def add_website_source(request: WebsiteSourceCreate, user=Depends(get_user)):
    try:
        origin = canonical_origin(request.url)
        await asyncio.to_thread(_vetted_addresses, urlsplit(origin).hostname)
    except (CrawlError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        source = await db_client.create_website_source(
            organization_id=user.selected_organization_id,
            created_by=user.id,
            origin=origin,
            refresh_interval_hours=request.refresh_interval_hours,
            max_pages=request.max_pages,
            available_to_all_agents=request.available_to_all_agents,
            status="pending",
        )
    except WebsiteSourceLimitError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"An organization can have at most {WEBSITE_SOURCE_LIMIT_PER_ORG} active website sources",
        ) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="This website source already exists in your organization") from exc
    try:
        await enqueue_job(FunctionNames.REFRESH_KNOWLEDGE_BASE_WEBSITE, source.source_uuid, user.selected_organization_id)
    except Exception as exc:
        await db_client.update_website_source(source.source_uuid, user.selected_organization_id, status="error", last_error="Refresh could not be queued")
        raise HTTPException(status_code=503, detail="Website source was saved but refresh could not be queued") from exc
    source.status = "crawling"
    return await _response(source)


@router.get("", response_model=WebsiteSourceList)
async def list_website_sources(user=Depends(get_user)):
    sources = await db_client.list_website_sources(user.selected_organization_id)
    return WebsiteSourceList(sources=[await _response(source) for source in sources if source.status != "deleted"])


@router.post("/{source_uuid}/refresh", response_model=WebsiteSourceResponse, status_code=status.HTTP_202_ACCEPTED)
async def refresh_website_source(source_uuid: str, user=Depends(get_user)):
    source = await db_client.get_website_source(source_uuid, user.selected_organization_id)
    if source is None or not source.is_active or source.status == "paused":
        raise HTTPException(status_code=404, detail="Website source not found")
    try:
        await enqueue_job(FunctionNames.REFRESH_KNOWLEDGE_BASE_WEBSITE, source.source_uuid, user.selected_organization_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Refresh could not be queued") from exc
    return await _response(source)


@router.post("/{source_uuid}/pause", response_model=WebsiteSourceResponse)
async def pause_website_source(source_uuid: str, user=Depends(get_user)):
    source = await db_client.pause_website_source(source_uuid, user.selected_organization_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Website source not found")
    return await _response(source)


@router.post("/{source_uuid}/resume", response_model=WebsiteSourceResponse, status_code=status.HTTP_202_ACCEPTED)
async def resume_website_source(source_uuid: str, user=Depends(get_user)):
    source = await db_client.resume_website_source(source_uuid, user.selected_organization_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Website source not found")
    try:
        await enqueue_job(FunctionNames.REFRESH_KNOWLEDGE_BASE_WEBSITE, source.source_uuid, user.selected_organization_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Refresh could not be queued") from exc
    source.status = "crawling"
    return await _response(source)


@router.delete("/{source_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_source(source_uuid: str, user=Depends(get_user)):
    source = await db_client.deactivate_website_source(source_uuid, user.selected_organization_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Website source not found")
