from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import hashlib
import pytest
from api.tasks import knowledge_base_processing as worker


@pytest.mark.asyncio
@pytest.mark.parametrize('extension',['txt','md','json'])
async def test_full_text_upload_keeps_unicode_local_and_avoids_external_processing(monkeypatch,extension):
    key=f'knowledge_base/7/doc/menu.{extension}'
    document=NS(id=42,organization_id=7,custom_metadata={'s3_key':key})
    text='नमस्ते. Appointment fee is ₹500.\n'
    async def download(storage_key,path): Path(path).write_bytes(text.encode('utf-8'));return True
    monkeypatch.setattr(worker.storage_fs,'adownload_file',download)
    monkeypatch.setattr(worker.db_client,'get_document_by_id',AsyncMock(return_value=document))
    monkeypatch.setattr(worker.db_client,'get_document_by_hash',AsyncMock(return_value=None))
    monkeypatch.setattr(worker.db_client,'compute_file_hash',lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest())
    monkeypatch.setattr(worker.db_client,'get_mime_type',lambda path:'text/plain')
    monkeypatch.setattr(worker.db_client,'update_document_metadata',AsyncMock())
    saved=AsyncMock();status=AsyncMock();external=AsyncMock()
    monkeypatch.setattr(worker.db_client,'update_document_full_text',saved)
    monkeypatch.setattr(worker.db_client,'update_document_status',status)
    monkeypatch.setattr(worker.mps_service_key_client,'process_document',external)
    await worker.process_knowledge_base_document({},42,key,7,'synthetic',retrieval_mode='full_document')
    saved.assert_awaited_once_with(42,text)
    assert status.await_args.args==(42,'completed')
    assert status.await_args.kwargs['docling_metadata']['processor']=='local_text'
    external.assert_not_awaited()
