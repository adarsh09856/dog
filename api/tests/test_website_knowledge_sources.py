from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.services import website_knowledge_crawler as crawler


def test_ssrf_rejects_mixed_public_and_private_dns(monkeypatch):
    monkeypatch.setattr(
        crawler.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (2, 1, 6, "", ("1.1.1.1", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(crawler.CrawlError, match="non-public"):
        crawler._vetted_addresses("public.example")


def test_connection_uses_the_vetted_ip_even_if_dns_would_rebind(monkeypatch):
    calls = []
    answers = iter([[(2, 1, 6, "", ("1.1.1.1", 443))], [(2, 1, 6, "", ("127.0.0.1", 443))]])
    monkeypatch.setattr(crawler.socket, "getaddrinfo", lambda *_args, **_kwargs: next(answers))
    vetted_ip = crawler._vetted_addresses("public.example")[0]
    assert vetted_ip == "1.1.1.1"

    class Context:
        def wrap_socket(self, sock, *, server_hostname):
            assert server_hostname == "public.example"
            return "pinned-tls-socket"

    monkeypatch.setattr(crawler.socket, "create_connection", lambda address, _timeout: calls.append(address) or "raw-socket")
    conn = crawler._PinnedHTTPSConnection("public.example", vetted_ip, 1)
    conn._context = Context()
    conn.connect()
    assert calls == [("1.1.1.1", 443)]
    assert conn.sock == "pinned-tls-socket"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:pass@example.com",
        "https://127.0.0.1/",
        "https://example.com:8443/",
        "https://intranet.local/",
    ],
)
def test_origin_validation_rejects_unsafe_urls(url):
    with pytest.raises(crawler.CrawlError):
        crawler.canonical_origin(url)


def test_same_origin_redirect_policy_rejects_cross_origin(monkeypatch):
    monkeypatch.setattr(
        crawler,
        "_read_response",
        lambda *_args, **_kwargs: (302, {"location": "https://attacker.example/"}, b""),
    )
    with pytest.raises(crawler.CrawlError, match="Cross-origin"):
        crawler._safe_fetch(
            "https://example.com/", crawler._origin("https://example.com/"),
            max_bytes=100, deadline=10**20,
        )


def test_response_size_cap_is_enforced(monkeypatch):
    class Response:
        status = 200

        def getheaders(self):
            return [("Content-Length", "101")]

    class Connection:
        def __init__(self, *_args, **_kwargs): pass
        def request(self, *_args, **_kwargs): pass
        def getresponse(self): return Response()
        def close(self): pass

    monkeypatch.setattr(crawler, "_vetted_addresses", lambda _host: ["1.1.1.1"])
    monkeypatch.setattr(crawler, "_PinnedHTTPSConnection", Connection)
    with pytest.raises(crawler.CrawlError, match="size limit"):
        crawler._read_response("https://example.com/", max_bytes=100, deadline=10**20)


def test_parser_removes_active_and_form_content_without_void_input_hiding_rest():
    parser = crawler._TextAndLinks()
    parser.feed("<main>Visible before<input name='x'><script>secret()</script><form>form secret</form><p>Visible after</p></main>")
    text = " ".join(" ".join(parser.parts).split())
    assert "Visible before" in text
    assert "Visible after" in text
    assert "secret" not in text


@pytest.mark.parametrize(
    "robots",
    [
        "User-agent: *\nDisallow: /wild\nUser-agent: KodewavesKnowledgeBot\nDisallow: /bot\n",
        "User-agent: KodewavesKnowledgeBot\nDisallow: /bot\nUser-agent: *\nDisallow: /wild\n",
    ],
)
def test_robots_prefers_matching_bot_group_regardless_of_group_order(robots):
    blocked, _sitemaps, _delays = crawler._robots_rules(robots)
    assert blocked == ["/bot"]


def test_crawl_obeys_robots_and_follows_bounded_sitemap_indexes(monkeypatch):
    calls: list[str] = []

    def response(url, _origin, *, max_bytes, deadline):
        calls.append(url)
        if url.endswith("/robots.txt"):
            body = b"User-agent: *\nDisallow: /private\nSitemap: https://example.com/sitemap-index.xml\n"
            return url, 200, {"content-type": "text/plain"}, body
        if url.endswith("sitemap-index.xml"):
            body = b"<sitemapindex><sitemap><loc>https://example.com/sitemap-a.xml</loc></sitemap></sitemapindex>"
            return url, 200, {"content-type": "application/xml"}, body
        if url.endswith("sitemap-a.xml"):
            body = b"<urlset><url><loc>https://example.com/public</loc></url><url><loc>https://example.com/private/secret</loc></url></urlset>"
            return url, 200, {"content-type": "application/xml"}, body
        if url.endswith("/private/secret"):
            pytest.fail("robots-disallowed URL was fetched")
        if url.endswith("/public"):
            return url, 200, {"content-type": "text/plain", "etag": '"v1"'}, b"public page text"
        if url.endswith("/"):
            return url, 200, {"content-type": "text/html"}, b"<a href='/private/secret'>private</a><a href='/public?utm_source=test'>public</a>"
        raise AssertionError(url)

    monkeypatch.setattr(crawler, "_safe_fetch", response)
    result = crawler.crawl_website("https://example.com/", max_pages=4)
    assert "public page text" in result.text
    assert result.etag == '"v1"'
    assert not any("private/secret" in url for url in calls)
    assert not any("utm_source" in url for url in calls)
    assert any(url.endswith("sitemap-a.xml") for url in calls)


def test_crawl_respects_page_and_depth_limits(monkeypatch):
    calls: list[str] = []

    def response(url, _origin, *, max_bytes, deadline):
        calls.append(url)
        if url.endswith("/robots.txt") or url.endswith("/sitemap.xml"):
            return url, 404, {"content-type": "text/plain"}, b""
        path = crawler.urlsplit(url).path
        level = 0 if path == "/" else int(path.strip("/"))
        body = f"<a href='/{level + 1}'>next</a> level {level}".encode()
        return url, 200, {"content-type": "text/html"}, body

    monkeypatch.setattr(crawler, "_safe_fetch", response)
    result = crawler.crawl_website("https://example.com/", max_pages=20)
    assert result.page_count == crawler.MAX_CRAWL_DEPTH + 1
    assert not any(url.endswith("/5") for url in calls)
    assert crawler.crawl_website("https://example.com/", max_pages=2).page_count == 2


def test_sitemap_rejects_utf16_dtd_before_xml_parser(monkeypatch):
    calls: list[str] = []
    unsafe_sitemap = "<!DOCTYPE urlset [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><urlset/>".encode("utf-16")

    def response(url, _origin, *, max_bytes, deadline):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return url, 200, {"content-type": "text/plain"}, b"User-agent: *\nSitemap: https://example.com/sitemap.xml\n"
        if url.endswith("sitemap.xml"):
            return url, 200, {"content-type": "application/xml"}, unsafe_sitemap
        pytest.fail("unsafe sitemap must stop before crawling site pages")

    monkeypatch.setattr(crawler, "_safe_fetch", response)
    with pytest.raises(crawler.CrawlError, match="UTF-8"):
        crawler.crawl_website("https://example.com/", max_pages=2)
    assert calls == ["https://example.com/robots.txt", "https://example.com/sitemap.xml"]


@pytest.mark.asyncio
async def test_website_routes_scope_list_pause_and_delete_to_selected_org(monkeypatch):
    from api.routes import knowledge_base_website as routes

    observed = {}
    source = SimpleNamespace(
        source_uuid="source-1", origin="https://example.com/", status="ready", is_active=True,
        available_to_all_agents=True,
        refresh_interval_hours=24, max_pages=50, last_refresh_started_at=None,
        last_refreshed_at=None, next_refresh_at=None, last_error=None, etag=None,
        content_hash=None, version=1, organization_id=28, document_id=None,
    )

    async def list_sources(org_id):
        observed["list_org"] = org_id
        return [source]

    async def update_source(source_uuid, org_id, **values):
        observed["update"] = (source_uuid, org_id, values)
        for key, value in values.items(): setattr(source, key, value)
        return source

    async def pause_source(source_uuid, org_id):
        observed["pause"] = (source_uuid, org_id)
        if source.status == "deleted": return None
        source.status = "paused"
        source.next_refresh_at = None
        return source

    async def deactivate(source_uuid, org_id):
        observed["delete"] = (source_uuid, org_id)
        source.is_active = False
        source.status = "deleted"
        return source

    async def resume_source(source_uuid, org_id):
        observed["resume"] = (source_uuid, org_id)
        if source.status == "deleted" or not source.is_active: return None
        source.status = "pending"
        return source

    monkeypatch.setattr(routes.db_client, "list_website_sources", list_sources)
    monkeypatch.setattr(routes.db_client, "update_website_source", update_source)
    monkeypatch.setattr(routes.db_client, "pause_website_source", pause_source)
    monkeypatch.setattr(routes.db_client, "resume_website_source", resume_source)
    monkeypatch.setattr(routes.db_client, "deactivate_website_source", deactivate)
    monkeypatch.setattr(routes, "enqueue_job", lambda *_args: asyncio.sleep(0))
    user = SimpleNamespace(selected_organization_id=28)
    listed = await routes.list_website_sources(user=user)
    assert observed["list_org"] == 28 and listed.sources[0].source_uuid == "source-1"
    await routes.pause_website_source("source-1", user=user)
    assert observed["pause"] == ("source-1", 28)
    assert source.is_active is True
    await routes.resume_website_source("source-1", user=user)
    assert observed["resume"] == ("source-1", 28)
    await routes.delete_website_source("source-1", user=user)
    assert observed["delete"] == ("source-1", 28)
    with pytest.raises(Exception) as paused_after_delete:
        await routes.pause_website_source("source-1", user=user)
    assert getattr(paused_after_delete.value, "status_code", None) == 404
    with pytest.raises(Exception) as resumed_after_delete:
        await routes.resume_website_source("source-1", user=user)
    assert getattr(resumed_after_delete.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_add_source_persists_org_wide_agent_availability(monkeypatch):
    from api.routes import knowledge_base_website as routes
    from api.schemas.website_knowledge import WebsiteSourceCreate

    observed = {}
    source = SimpleNamespace(
        source_uuid="source-2", origin="https://example.com/", status="pending", is_active=True,
        available_to_all_agents=True, refresh_interval_hours=24, max_pages=10,
        last_refresh_started_at=None, last_refreshed_at=None, next_refresh_at=None,
        last_error=None, etag=None, content_hash=None, version=0, organization_id=31,
        document_id=None,
    )
    async def create_source(**values):
        observed.update(values)
        return source
    async def queue_job(*args): observed["job"] = args
    async def thread_runner(func, *args):
        observed["dns_offloaded"] = func is routes._vetted_addresses
        return func(*args)
    monkeypatch.setattr(routes, "canonical_origin", lambda value: "https://example.com/")
    monkeypatch.setattr(routes, "_vetted_addresses", lambda _host: ["93.184.216.34"])
    monkeypatch.setattr(routes.asyncio, "to_thread", thread_runner)
    monkeypatch.setattr(routes.db_client, "create_website_source", create_source)
    monkeypatch.setattr(routes, "enqueue_job", queue_job)
    result = await routes.add_website_source(
        WebsiteSourceCreate(url="https://example.com", max_pages=10),
        user=SimpleNamespace(selected_organization_id=31, id=12),
    )
    assert observed["organization_id"] == 31
    assert observed["available_to_all_agents"] is True
    assert observed["dns_offloaded"] is True
    assert result.available_to_all_agents is True
    assert observed["job"][1:] == ("source-2", 31)


@pytest.mark.asyncio
async def test_failed_refresh_preserves_last_indexed_content(monkeypatch):
    from api.tasks import website_knowledge

    old_doc = SimpleNamespace(id=7, organization_id=28, is_active=True, full_text="last good searchable text")
    source = SimpleNamespace(
        source_uuid="source-1", organization_id=28, is_active=True, origin="https://example.com/",
        max_pages=10, refresh_interval_hours=24, created_by=9, document_id=7,
        content_hash="old-hash", etag='"old"', status="ready",
    )
    updates = []

    class DB:
        async def claim_website_source_refresh(self, *_args): return source
        async def get_document_by_id(self, *_args): return old_doc
        async def get_website_source(self, *_args): return source
        async def update_website_source(self, *_args, **kwargs):
            updates.append(kwargs)
            for key, value in kwargs.items(): setattr(source, key, value)

    async def fail_crawl(*_args, **_kwargs):
        raise crawler.CrawlError("Website response exceeds the size limit")

    monkeypatch.setattr(website_knowledge, "db_client", DB())
    monkeypatch.setattr(website_knowledge.asyncio, "to_thread", fail_crawl)
    with pytest.raises(crawler.CrawlError):
        await website_knowledge.refresh_knowledge_base_website({}, "source-1", 28)
    assert old_doc.full_text == "last good searchable text"
    assert source.content_hash == "old-hash"
    assert source.etag == '"old"'
    assert source.status == "error"
    assert updates[-1]["next_refresh_at"] is not None


@pytest.mark.asyncio
async def test_scheduled_refresh_enqueues_org_scoped_work(monkeypatch):
    from api.tasks import website_knowledge

    source = SimpleNamespace(source_uuid="source-1", organization_id=28)
    async def due_sources(limit):
        assert limit == 100
        return [source]

    class Redis:
        def __init__(self): self.jobs = []
        async def enqueue_job(self, *args): self.jobs.append(args)

    redis = Redis()
    monkeypatch.setattr(website_knowledge.db_client, "get_due_website_sources", due_sources)
    result = await website_knowledge.sweep_website_knowledge_sources({"redis": redis})
    assert result == {"queued": 1}
    assert redis.jobs[0][1:] == ("source-1", 28)


@pytest.mark.asyncio
async def test_org_shared_site_source_reaches_agent_retrieval_without_manual_attachment(monkeypatch):
    from api.services.workflow.tools import knowledge_base

    observed = {}
    source_state = {"status": "ready"}

    class DB:
        async def get_website_document_uuids_for_organization(self, organization_id):
            observed["org"] = organization_id
            observed["status"] = source_state["status"]
            # Pausing only disables refresh. Delete removes the UUID from all
            # agent retrieval while keeping the source tenant scoped.
            return [] if source_state["status"] == "deleted" else ["website-doc-uuid"]

        async def get_full_text_documents(self, organization_id, document_uuids):
            observed["retrieval_org"] = organization_id
            observed["docs"] = document_uuids
            if not document_uuids:
                return []
            return [SimpleNamespace(
                full_text="Our return window is 30 days.",
                filename="website-source.md",
                document_uuid="website-doc-uuid",
                custom_metadata={"website_source_uuid": "source-1"},
            )]

    monkeypatch.setattr(knowledge_base, "db_client", DB())
    uuids = await knowledge_base.get_agent_knowledge_document_uuids(organization_id=28)
    result = await knowledge_base._perform_retrieval(
        query="What is the return window?",
        organization_id=28,
        document_uuids=uuids,
        limit=3,
    )
    assert observed["org"] == observed["retrieval_org"] == 28
    assert observed["docs"] == ["website-doc-uuid"]
    assert result["chunks"][0]["text"] == "Our return window is 30 days."

    source_state["status"] = "paused"
    paused_uuids = await knowledge_base.get_agent_knowledge_document_uuids(28)
    paused_result = await knowledge_base._perform_retrieval(
        query="What is the return window?", organization_id=28,
        document_uuids=paused_uuids, limit=3,
    )
    assert paused_result["chunks"][0]["text"] == "Our return window is 30 days."

    source_state["status"] = "deleted"
    deleted_uuids = await knowledge_base.get_agent_knowledge_document_uuids(28)
    deleted_result = await knowledge_base._perform_retrieval(
        query="What is the return window?", organization_id=28,
        document_uuids=deleted_uuids, limit=3,
    )
    assert deleted_uuids == []
    assert deleted_result["total_results"] == 0


def test_website_retrieval_sends_only_relevant_bounded_passages():
    from api.services.workflow.tools import knowledge_base

    site_text = (
        "Source: https://shop.example/returns\n"
        "Our return window is 30 days from delivery. Contact support to start a return.\n\n"
        "Source: https://shop.example/security\n"
        "The warehouse uses a monitored alarm system and a guarded loading dock."
    )
    passages = knowledge_base._website_text_matches("What is the return window?", site_text)
    assert len(passages) == 1
    assert "30 days" in passages[0]["text"]
    assert "guarded loading dock" not in passages[0]["text"]
    assert len(passages[0]["text"]) <= 1000


@pytest.mark.asyncio
async def test_multiple_website_sources_share_one_global_retrieval_budget(monkeypatch):
    from api.services.workflow.tools import knowledge_base

    documents = [
        SimpleNamespace(
            full_text=f"Source: https://example.com/{index}\nOur return window is 30 days. " + ("return window policy detail. " * 120),
            filename=f"site-{index}.md",
            document_uuid=f"doc-{index}",
            custom_metadata={"website_source_uuid": f"source-{index}"},
        )
        for index in range(5)
    ]

    class DB:
        async def get_website_document_uuids_for_organization(self, _org_id):
            return [doc.document_uuid for doc in documents]
        async def get_full_text_documents(self, organization_id, document_uuids):
            assert organization_id == 28
            return [doc for doc in documents if doc.document_uuid in document_uuids]

    monkeypatch.setattr(knowledge_base, "db_client", DB())
    uuids = await knowledge_base.get_agent_knowledge_document_uuids(28)
    result = await knowledge_base._perform_retrieval(
        query="return window", organization_id=28, document_uuids=uuids, limit=3
    )
    assert "error" not in result
    website_passages = result["chunks"]
    assert len(website_passages) <= knowledge_base.MAX_WEBSITE_RETRIEVAL_PASSAGES
    assert sum(len(item["text"]) for item in website_passages) <= knowledge_base.MAX_WEBSITE_RETRIEVAL_CHARS
    assert all("return window" in item["text"].lower() for item in website_passages)


@pytest.mark.asyncio
async def test_organization_website_source_query_is_capped_at_five():
    from api.db.knowledge_base_client import KnowledgeBaseClient, WEBSITE_SOURCE_LIMIT_PER_ORG

    captured = []

    class Scalars:
        def all(self):
            return ["doc-1", "doc-2", "doc-3", "doc-4", "doc-5"]

    class Result:
        def scalars(self):
            return Scalars()

    class Session:
        async def execute(self, query):
            captured.append(query)
            return Result()

    class SessionContext:
        async def __aenter__(self):
            return Session()
        async def __aexit__(self, *_args):
            return False

    client = object.__new__(KnowledgeBaseClient)
    client.async_session = lambda: SessionContext()

    source_ids = await client.get_website_document_uuids_for_organization(28)
    assert len(source_ids) <= WEBSITE_SOURCE_LIMIT_PER_ORG == 5
    assert captured[0]._limit_clause.value == WEBSITE_SOURCE_LIMIT_PER_ORG


@pytest.mark.asyncio
async def test_source_creation_rejects_org_over_the_active_source_limit():
    from api.db.knowledge_base_client import (
        KnowledgeBaseClient,
        WebsiteSourceLimitError,
    )

    class Session:
        async def execute(self, *_args, **_kwargs):
            return None
        async def scalar(self, *_args, **_kwargs):
            return 5

    class SessionContext:
        async def __aenter__(self):
            return Session()
        async def __aexit__(self, *_args):
            return False

    client = object.__new__(KnowledgeBaseClient)
    client.async_session = lambda: SessionContext()

    with pytest.raises(WebsiteSourceLimitError):
        await client.create_website_source(organization_id=28, created_by=1, origin="https://example.com")


@pytest.mark.asyncio
async def test_processor_does_not_publish_after_source_pause(monkeypatch, tmp_path):
    from api.tasks import knowledge_base_processing as processing

    document = SimpleNamespace(
        id=7, organization_id=28, is_active=True, custom_metadata={
            "s3_key": "knowledge_base/28/site.md", "website_source_uuid": "source-1",
        }, full_text="last searchable version", retrieval_mode="full_document",
    )
    calls = []

    class DB:
        def compute_file_hash(self, _path): return "new-hash"
        def get_mime_type(self, _path): return "text/markdown"
        async def get_document_by_id(self, _doc_id): return document
        async def get_document_by_hash(self, *_args): return None
        async def update_document_metadata(self, *_args, **_kwargs): pass
        async def update_document_status(self, _doc_id, state, **_kwargs): calls.append(("status", state))
        async def update_website_document_content_if_active(self, *_args): calls.append(("publish",)); return False
        async def update_website_source_for_document(self, *_args, **kwargs): calls.append(("source", kwargs["succeeded"]))
        async def update_document_full_text(self, *_args): pytest.fail("paused source must not replace indexed text")

    class Storage:
        async def adownload_file(self, _key, path):
            import pathlib
            pathlib.Path(path).write_text("new but paused", encoding="utf-8")
            return True

    async def allow_features(*_args): pass
    monkeypatch.setattr(processing, "db_client", DB())
    monkeypatch.setattr(processing, "storage_fs", Storage())
    monkeypatch.setattr(processing, "require_client_worker_features", allow_features)
    await processing.process_knowledge_base_document(
        {}, 7, "knowledge_base/28/site.md", 28, "owner-provider-id", retrieval_mode="full_document"
    )
    assert document.full_text == "last searchable version"
    assert ("publish",) in calls
    assert ("source", False) in calls


@pytest.mark.asyncio
async def test_indexing_failure_keeps_last_searchable_website_text(monkeypatch):
    from api.tasks import knowledge_base_processing as processing

    document = SimpleNamespace(
        id=9, organization_id=28, is_active=True,
        custom_metadata={"s3_key": "knowledge_base/28/site.md", "website_source_uuid": "source-9"},
        full_text="prior indexed policy", retrieval_mode="full_document",
    )
    calls = []

    class DB:
        def compute_file_hash(self, _path): return "new-hash"
        def get_mime_type(self, _path): return "text/markdown"
        async def get_document_by_id(self, _doc_id): return document
        async def get_document_by_hash(self, *_args): return None
        async def update_document_metadata(self, *_args, **_kwargs): pass
        async def update_document_status(self, _doc_id, state, **_kwargs): calls.append(("status", state))
        async def update_website_source_for_document(self, *_args, **kwargs): calls.append(("source", kwargs["succeeded"]))
        async def update_document_full_text(self, *_args): pytest.fail("website indexing must publish through its guarded path")

    class Storage:
        async def adownload_file(self, *_args): return False

    async def allow_features(*_args): pass
    monkeypatch.setattr(processing, "db_client", DB())
    monkeypatch.setattr(processing, "storage_fs", Storage())
    monkeypatch.setattr(processing, "require_client_worker_features", allow_features)
    with pytest.raises(Exception, match="Failed to download"):
        await processing.process_knowledge_base_document(
            {}, 9, "knowledge_base/28/site.md", 28, "owner-provider-id", retrieval_mode="full_document"
        )
    assert document.full_text == "prior indexed policy"
    assert ("source", False) in calls
