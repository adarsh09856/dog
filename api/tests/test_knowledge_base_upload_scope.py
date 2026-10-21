from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from fastapi import HTTPException
from api.routes import knowledge_base as route
from api.schemas.knowledge_base import DocumentUploadRequestSchema, ProcessDocumentRequestSchema

UUID='24aad50f-8520-4c18-a61e-2a3a93bad275'
USER=NS(id=9,selected_organization_id=7,provider_id='synthetic')


@pytest.mark.asyncio
@pytest.mark.parametrize('key',[
    f'knowledge_base/8/{UUID}/menu.txt',
    f'knowledge_base/7/{UUID}/../menu.txt',
    f'knowledge_base/7/{UUID}/folder/menu.txt',
    f'knowledge_base/7/{UUID}/..',
    f'knowledge_base/7/00000000-0000-0000-0000-000000000000/menu.txt',
])
async def test_processing_rejects_foreign_or_mismatched_storage_object(monkeypatch,key):
    create=AsyncMock();monkeypatch.setattr(route.db_client,'create_document',create)
    with pytest.raises(HTTPException) as error:
        await route.process_document(ProcessDocumentRequestSchema(document_uuid=UUID,s3_key=key),USER)
    assert error.value.status_code==404
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('name',['../menu.txt','folder/menu.txt',r'folder\menu.txt','..',' '])
async def test_upload_rejects_paths_before_signing_storage_url(monkeypatch,name):
    sign=AsyncMock();monkeypatch.setattr(route.storage_fs,'aget_presigned_put_url',sign)
    with pytest.raises(HTTPException) as error:
        await route.get_upload_url(DocumentUploadRequestSchema(filename=name,mime_type='text/plain'),USER)
    assert error.value.status_code==400
    sign.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_failure_does_not_leave_document_permanently_pending(monkeypatch):
    monkeypatch.setattr(route.db_client,'create_document',AsyncMock(return_value=NS(id=42)))
    monkeypatch.setattr(route,'enqueue_document_processing',AsyncMock(side_effect=ConnectionError()))
    update=AsyncMock();monkeypatch.setattr(route.db_client,'update_document_status',update)
    with pytest.raises(HTTPException) as error:
        await route.process_document(ProcessDocumentRequestSchema(document_uuid=UUID,s3_key=f'knowledge_base/7/{UUID}/menu.txt'),USER)
    assert error.value.status_code==503
    assert update.await_args.args == (42,'failed')


@pytest.mark.asyncio
@pytest.mark.parametrize('document',[
    NS(organization_id=8,custom_metadata={'s3_key':'foreign'}),
    NS(organization_id=7,custom_metadata={'s3_key':'expected'}),
])
async def test_background_job_checks_ownership_before_reading_or_mutating(monkeypatch,document):
    from api.tasks import knowledge_base_processing as worker
    monkeypatch.setattr(worker.db_client,'get_document_by_id',AsyncMock(return_value=document))
    update=AsyncMock();download=AsyncMock()
    monkeypatch.setattr(worker.db_client,'update_document_status',update)
    monkeypatch.setattr(worker.storage_fs,'adownload_file',download)
    await worker.process_knowledge_base_document({},42,'foreign',7,'synthetic')
    update.assert_not_awaited();download.assert_not_awaited()
