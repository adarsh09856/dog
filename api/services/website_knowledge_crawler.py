"""SSRF-resistant, bounded crawler for organization website knowledge sources."""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

MAX_PAGE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024
MAX_PROCESSED_TEXT_BYTES = 512 * 1024
MAX_CRAWL_SECONDS = 75
MAX_REDIRECTS = 2
MAX_CRAWL_PAGES = 100
MAX_CRAWL_DEPTH = 4
USER_AGENT = "KodewavesKnowledgeBot/1.0 (+https://kodewaves.in/bot)"


class CrawlError(ValueError):
    """A rejected URL, unsafe network response, or bounded crawl failure."""


@dataclass(frozen=True)
class CrawlResult:
    text: str
    page_count: int
    content_hash: str
    etag: str | None


def canonical_origin(value: str) -> str:
    """Validate and normalize an HTTPS origin URL (path is allowed as a start)."""
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise CrawlError("Only HTTPS website URLs are supported")
    if parsed.username is not None or parsed.password is not None:
        raise CrawlError("Credentials in website URLs are not allowed")
    if parsed.port not in (None, 443):
        raise CrawlError("Website sources must use HTTPS port 443")
    if parsed.fragment:
        raise CrawlError("URL fragments are not supported")
    host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal", ".localhost")):
        raise CrawlError("Local and internal hostnames are not allowed")
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise CrawlError("IP-address website URLs are not allowed")
    path = parsed.path or "/"
    return urlunsplit(("https", host, path, "", ""))


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    return parsed.scheme.lower(), (parsed.hostname or "").lower().rstrip("."), parsed.port or 443


def _vetted_addresses(host: str) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CrawlError("Website hostname could not be resolved") from exc
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses:
        raise CrawlError("Website hostname has no address records")
    # Reject the whole host if *any* answer is non-public; don't pick a public
    # answer from a mixed public/private DNS response.
    for value in addresses:
        try:
            ip = ipaddress.ip_address(value.split("%", 1)[0])
        except ValueError as exc:
            raise CrawlError("Website hostname returned an invalid address") from exc
        if not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_unspecified:
            raise CrawlError("Website hostname resolved to a non-public address")
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an already-vetted IP while retaining TLS hostname checks."""

    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_address, 443), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class _TextAndLinks(HTMLParser):
    _DROP = {"script", "style", "noscript", "svg", "form", "button", "input", "textarea", "select", "option", "nav", "footer", "header"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._drop_stack: list[str] = []
        self.parts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        tag = tag.lower()
        if tag in self._DROP and tag not in {"input"}:
            self._drop_stack.append(tag)
        if not self._drop_stack and tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if not self._drop_stack and tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() in self._DROP and tag.lower() in self._drop_stack:
            self._drop_stack = self._drop_stack[:len(self._drop_stack) - 1 - self._drop_stack[::-1].index(tag.lower())]
        elif not self._drop_stack and tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if not self._drop_stack and data.strip():
            self.parts.append(data.strip())

    def handle_startendtag(self, tag: str, attrs):
        # Void tags such as input/img never have an end tag. Treat them as a
        # normal start only for link collection/formatting and immediately pop.
        tag = tag.lower()
        prior_depth = len(self._drop_stack)
        self.handle_starttag(tag, attrs)
        if tag in self._DROP and len(self._drop_stack) > prior_depth:
            self._drop_stack.pop()


def _read_response(url: str, *, max_bytes: int, deadline: float) -> tuple[int, dict[str, str], bytes]:
    parsed = urlsplit(url)
    if parsed.username is not None or parsed.password is not None or _origin(url)[0] != "https" or _origin(url)[2] != 443 or not parsed.hostname:
        raise CrawlError("Only HTTPS port 443 requests are allowed")
    if time.monotonic() >= deadline:
        raise CrawlError("Website crawl time limit exceeded")
    addresses = _vetted_addresses(parsed.hostname)
    conn = _PinnedHTTPSConnection(parsed.hostname, addresses[0], timeout=min(6, max(0.5, deadline - time.monotonic())))
    target = urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
    try:
        conn.request("GET", target, headers={"Host": parsed.hostname, "User-Agent": USER_AGENT, "Accept": "text/html, text/plain, application/xml, text/xml", "Accept-Encoding": "identity", "Connection": "close"})
        response = conn.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        if headers.get("content-encoding", "identity").lower() not in ("", "identity"):
            raise CrawlError("Compressed website responses are not supported")
        if int(headers.get("content-length", "0") or 0) > max_bytes:
            raise CrawlError("Website response exceeds the size limit")
        body = bytearray()
        while len(body) <= max_bytes:
            if time.monotonic() >= deadline:
                raise CrawlError("Website crawl time limit exceeded")
            block = response.read(min(65536, max_bytes + 1 - len(body)))
            if not block:
                break
            body.extend(block)
        if len(body) > max_bytes:
            raise CrawlError("Website response exceeds the size limit")
        return response.status, headers, bytes(body)
    except (OSError, http.client.HTTPException, ssl.SSLError) as exc:
        raise CrawlError("Website could not be fetched securely") from exc
    finally:
        conn.close()


def _safe_fetch(url: str, root_origin: tuple[str, str, int], *, max_bytes: int, deadline: float):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if _origin(current) != root_origin:
            raise CrawlError("Cross-origin redirects and links are not allowed")
        status, headers, body = _read_response(current, max_bytes=max_bytes, deadline=deadline)
        if status not in {301, 302, 303, 307, 308}:
            return current, status, headers, body
        location = headers.get("location")
        if not location:
            raise CrawlError("Website redirect has no destination")
        current = urljoin(current, location)
        if urlsplit(current).username is not None or urlsplit(current).password is not None:
            raise CrawlError("Redirect credentials are not allowed")
        if _origin(current) != root_origin:
            raise CrawlError("Cross-origin redirects are not allowed")
    raise CrawlError("Too many website redirects")


def _robots_rules(text: str) -> tuple[list[str], list[str], list[str]]:
    groups: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {"agents": [], "disallow": [], "delay": []}
    current_has_rules = False
    sitemaps: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current["agents"] and current_has_rules:
                groups.append(current)
                current = {"agents": [], "disallow": [], "delay": []}
                current_has_rules = False
            current["agents"].append(value.lower())
        elif key == "disallow" and value:
            if current["agents"]:
                current["disallow"].append(value)
                current_has_rules = True
        elif key == "sitemap" and value:
            sitemaps.append(value)
        elif key == "crawl-delay" and value:
            try:
                if current["agents"]:
                    current["delay"].append(str(min(30.0, max(0.0, float(value)))))
                    current_has_rules = True
            except ValueError:
                pass
    if current["agents"]:
        groups.append(current)
    bot_groups = [g for g in groups if any("kodewavesknowledgebot" in agent for agent in g["agents"] if agent != "*")]
    selected = bot_groups or [g for g in groups if "*" in g["agents"]]
    disallow = [rule for group in selected for rule in group["disallow"]]
    delays = [delay for group in selected for delay in group["delay"]]
    return disallow, list(dict.fromkeys(sitemaps)), delays


def crawl_website(origin: str, *, max_pages: int = 50) -> CrawlResult:
    """Fetch a bounded sitemap/link crawl; no document content is logged."""
    start = canonical_origin(origin)
    root_origin = _origin(start)
    page_limit = min(MAX_CRAWL_PAGES, max(1, int(max_pages)))
    deadline = time.monotonic() + MAX_CRAWL_SECONDS
    network_bytes = 0
    robots_url = urlunsplit(("https", root_origin[1], "/robots.txt", "", ""))
    _, robots_status, robots_headers, robots_body = _safe_fetch(robots_url, root_origin, max_bytes=128 * 1024, deadline=deadline)
    network_bytes += len(robots_body)
    blocked, sitemap_urls, crawl_delays = ([], [], [])
    if robots_status == 200:
        if "text/plain" not in robots_headers.get("content-type", "").lower():
            raise CrawlError("Website robots.txt has an unsupported content type")
        blocked, sitemap_urls, crawl_delays = _robots_rules(robots_body.decode("utf-8", "replace"))
    elif robots_status not in (404, 410):
        raise CrawlError("Website robots policy could not be confirmed")
    delay = float(crawl_delays[0]) if crawl_delays else 0.0
    if not sitemap_urls:
        sitemap_urls = [urlunsplit(("https", root_origin[1], "/sitemap.xml", "", ""))]

    def permitted(url: str) -> bool:
        path = urlsplit(url).path or "/"
        for rule in blocked:
            if rule.endswith("$"):
                pattern = "^" + re.escape(rule[:-1]).replace(r"\*", ".*") + "$"
                if re.search(pattern, path):
                    return False
            else:
                pattern = "^" + re.escape(rule).replace(r"\*", ".*")
                if re.search(pattern, path):
                    return False
        return True

    queue: deque[tuple[str, int]] = deque()
    if permitted(start):
        queue.append((start, 0))
    sitemap_queue = deque(sitemap_urls[:5])
    seen_sitemaps: set[str] = set()
    while sitemap_queue and len(seen_sitemaps) < 10 and len(queue) < page_limit:
        sitemap = sitemap_queue.popleft()
        if sitemap in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap)
        if _origin(sitemap) == root_origin:
            try:
                _, status, headers, body = _safe_fetch(sitemap, root_origin, max_bytes=256 * 1024, deadline=deadline)
                network_bytes += len(body)
                if network_bytes > MAX_TOTAL_BYTES:
                    raise CrawlError("Website crawl exceeds the total size limit")
                if status == 200 and ("xml" in headers.get("content-type", "").lower() or body.lstrip().startswith(b"<?xml")):
                    try:
                        sitemap_text = body.decode("utf-8-sig", "strict")
                    except UnicodeDecodeError as exc:
                        raise CrawlError("Sitemap must use UTF-8 encoding") from exc
                    if "\x00" in sitemap_text or re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", sitemap_text, re.IGNORECASE):
                        raise CrawlError("Sitemap declarations are not allowed")
                    # We have already decoded as UTF-8 and rejected DTDs;
                    # remove the optional declaration before passing Unicode
                    # to ElementTree (which rejects declarations on str input).
                    sitemap_text = re.sub(r"^\s*<\?xml[^?]*\?>", "", sitemap_text, count=1, flags=re.IGNORECASE)
                    try:
                        root = ET.fromstring(sitemap_text)
                    except ET.ParseError:
                        continue
                    is_index = root.tag.rsplit("}", 1)[-1].lower() == "sitemapindex"
                    for node in root.iter():
                        if node.tag.rsplit("}", 1)[-1].lower() == "loc" and node.text:
                            loc = urljoin(sitemap, node.text.strip())
                            loc_parts = urlsplit(loc)
                            if loc_parts.username is not None or loc_parts.password is not None:
                                continue
                            if _origin(loc) == root_origin and permitted(loc):
                                if is_index:
                                    if len(sitemap_queue) < 10:
                                        sitemap_queue.append(loc)
                                    continue
                                queue.append((loc, 0))
                                if len(queue) >= page_limit:
                                    break
            except ET.ParseError:
                continue

    seen: set[str] = set()
    pages: list[tuple[str, str]] = []
    total_bytes = 0
    fetched_pages = 0
    last_etag = None
    while queue and fetched_pages < page_limit:
        if time.monotonic() >= deadline:
            raise CrawlError("Website crawl time limit exceeded")
        url, depth = queue.popleft()
        parsed = urlsplit(url)
        normalized = urlunsplit(("https", root_origin[1], parsed.path or "/", "", ""))
        if normalized in seen or not permitted(normalized) or depth > MAX_CRAWL_DEPTH:
            continue
        seen.add(normalized)
        if delay and pages:
            time.sleep(min(delay, max(0, deadline - time.monotonic())))
        remaining_bytes = MAX_TOTAL_BYTES - network_bytes
        if remaining_bytes <= 0:
            raise CrawlError("Website crawl exceeds the total size limit")
        _, status, headers, body = _safe_fetch(normalized, root_origin, max_bytes=min(MAX_PAGE_BYTES, remaining_bytes), deadline=deadline)
        fetched_pages += 1
        network_bytes += len(body)
        if network_bytes > MAX_TOTAL_BYTES:
            raise CrawlError("Website crawl exceeds the total size limit")
        if status != 200:
            continue
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"text/html", "text/plain"}:
            continue
        total_bytes += len(body)
        if total_bytes > MAX_TOTAL_BYTES:
            raise CrawlError("Website crawl exceeds the total size limit")
        last_etag = headers.get("etag") or last_etag
        decoded = body.decode("utf-8-sig", "replace")
        if content_type == "text/plain":
            text = decoded
        else:
            parser = _TextAndLinks()
            parser.feed(decoded)
            text = " ".join(" ".join(parser.parts).split())
            for link in parser.links:
                candidate = urljoin(normalized, link)
                candidate_parts = urlsplit(candidate)
                if candidate_parts.username is not None or candidate_parts.password is not None:
                    continue
                if _origin(candidate) == root_origin and len(seen) + len(queue) < page_limit * 3:
                    if candidate_parts.scheme == "https" and candidate_parts.port in (None, 443) and permitted(candidate):
                        queue.append((urlunsplit(("https", root_origin[1], candidate_parts.path or "/", "", "")), depth + 1))
        if text.strip():
            pages.append((normalized, text[:200_000]))
    if not pages:
        raise CrawlError("No readable pages were found on this website")
    import hashlib
    content = "\n\n".join(f"Source: {url}\n{text}" for url, text in pages)
    if len(content.encode("utf-8")) > MAX_PROCESSED_TEXT_BYTES:
        raise CrawlError("Processed website text exceeds the knowledge base limit")
    return CrawlResult(content, len(pages), hashlib.sha256(content.encode("utf-8")).hexdigest(), last_etag)
