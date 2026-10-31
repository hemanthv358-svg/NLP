import ipaddress
import http.cookiejar
import random
import re
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from collections import deque
from html.parser import HTMLParser

from bs4 import BeautifulSoup

from backend.app.config import CHUNK_OVERLAP, CHUNK_SIZE, MAX_CRAWL_CHUNKS, MAX_CRAWL_PAGES, MAX_CRAWL_SECONDS


SKIPPED_EXTENSIONS = re.compile(
    r"\.(?:7z|avi|css|docx?|gif|gz|ico|jpe?g|js|json|m4a|mov|mp3|mp4|mpeg|pdf|png|pptx?|rar|svg|tar|wav|webm|webp|xlsx?|xml|zip)$",
    re.I,
)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/123 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 Version/17 Safari/605.1.15",
]


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.text = []
        self.title = []
        self.tables = []
        self._ignored_depth = 0
        self._in_title = False
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style", "svg", "noscript", "template"}:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg", "noscript", "template"} and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"td", "th"} and self._cell is not None:
            value = " ".join(self._cell).strip()
            self._row.append(value)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None

    def handle_data(self, data):
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self._in_title:
            self.title.append(cleaned)
        if self._cell is not None:
            self._cell.append(cleaned)
        if not self._ignored_depth:
            self.text.append(cleaned)


def canonical_site_key(url):
    parsed = urllib.parse.urlparse(str(url))
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Enter a complete public http:// or https:// URL.")
    return host.removeprefix("www.")


def _ensure_public_host(host):
    if host.lower().rstrip(".") == "localhost":
        raise ValueError("Local and private network addresses cannot be crawled.")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(item[4][0])
                for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as error:
            raise ValueError(f"The website host could not be resolved: {host}") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Local and private network addresses cannot be crawled.")


def validate_public_url(url, expected_site=None):
    parsed = urllib.parse.urlparse(str(url))
    site_key = canonical_site_key(url)
    if parsed.username or parsed.password:
        raise ValueError("URLs containing usernames or passwords are not supported.")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("The URL contains an invalid port.") from error
    if port not in {None, 80, 443}:
        raise ValueError("Only standard HTTP and HTTPS ports can be crawled.")
    if expected_site and site_key != expected_site:
        raise ValueError("The website redirected outside the selected site.")
    _ensure_public_host(parsed.hostname)
    return urllib.parse.urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", parsed.query, "")
    )


def normalize_url(base_url, href, site_key):
    url = urllib.parse.urljoin(base_url, href)
    parsed = urllib.parse.urlparse(url)
    try:
        if canonical_site_key(url) != site_key or parsed.port not in {None, 80, 443}:
            return None
    except ValueError:
        return None
    if parsed.username or parsed.password or SKIPPED_EXTENSIONS.search(parsed.path):
        return None
    return urllib.parse.urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", parsed.query, "")
    )


def chunk_text(text):
    paragraphs = [part.strip() for part in re.split(r"\n+|(?<=[.!?])\s+", text) if part.strip()]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current} {paragraph}".strip()
        if len(candidate) <= CHUNK_SIZE:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = f"{current[-CHUNK_OVERLAP:]} {paragraph}".strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if len(chunk) >= 180]


def table_documents(tables, url, title):
    documents = []
    for index, rows in enumerate(tables[:12], start=1):
        normalized_rows = [[str(cell).strip() for cell in row[:20]] for row in rows[:100]]
        content = "\n".join(" | ".join(row) for row in normalized_rows if any(row)).strip()
        if len(content) < 30:
            continue
        documents.append(
            {
                "url": url,
                "title": f"{title} · Table {index}",
                "content": content,
                "metadata": {"kind": "table", "rows": normalized_rows},
            }
        )
    return documents


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, site_key):
        super().__init__()
        self.site_key = site_key

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        safe_url = validate_public_url(new_url, self.site_key)
        return super().redirect_request(request, file_pointer, code, message, headers, safe_url)


def crawl_with_browser(start_url, site_key, max_pages, progress=None):
    from playwright.sync_api import sync_playwright

    queue = deque([start_url])
    visited = set()
    documents = []
    errors = []
    checked_hosts = {}
    started_at = time.monotonic()

    def handle_route(route):
        parsed = urllib.parse.urlparse(route.request.url)
        if parsed.scheme in {"data", "blob"}:
            route.continue_()
            return
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            route.abort()
            return
        host = parsed.hostname.lower()
        if host not in checked_hosts:
            try:
                _ensure_public_host(host)
                checked_hosts[host] = True
            except ValueError:
                checked_hosts[host] = False
        route.continue_() if checked_hosts[host] else route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            ignore_https_errors=True,
            user_agent=random.choice(USER_AGENTS),
        )
        context.route("**/*", handle_route)
        page = context.new_page()
        while queue and len(visited) < max_pages and len(documents) < MAX_CRAWL_CHUNKS:
            if time.monotonic() - started_at > MAX_CRAWL_SECONDS:
                errors.append("Crawl stopped at the configured time limit.")
                break
            if visited:
                time.sleep(random.uniform(2, 5))
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            if progress:
                progress(len(visited), max_pages, url)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                for _ in range(3):
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(700)
                final_url = normalize_url(url, page.url, site_key)
                if not final_url:
                    raise ValueError("The page redirected outside the selected site.")
                title = page.title().strip() or urllib.parse.urlparse(final_url).path.strip("/") or site_key
                text = re.sub(r"\s+", " ", page.locator("body").inner_text(timeout=8_000)).strip()
                links = page.locator("a").evaluate_all("nodes => nodes.map(node => node.href)")
                tables = page.locator("table").evaluate_all(
                    "nodes => nodes.map(table => Array.from(table.rows).map(row => "
                    "Array.from(row.cells).map(cell => cell.innerText.trim())))"
                )
            except Exception as error:
                errors.append(f"{url}: {error}")
                continue
            for index, chunk in enumerate(chunk_text(text), start=1):
                documents.append(
                    {
                        "url": final_url,
                        "title": f"{title} · Part {index}",
                        "content": chunk,
                        "metadata": {"kind": "text", "word_count": len(chunk.split())},
                    }
                )
            documents.extend(table_documents(tables, final_url, title))
            for href in links:
                normalized = normalize_url(final_url, href, site_key)
                if normalized and normalized not in visited and normalized not in queue:
                    queue.append(normalized)
        browser.close()
    return documents, len(visited), errors


def crawl_with_http(start_url, max_pages=MAX_CRAWL_PAGES, progress=None):
    start_url = validate_public_url(start_url)
    site_key = canonical_site_key(start_url)
    queue = deque([start_url])
    visited = set()
    documents = []
    errors = []
    started_at = time.monotonic()
    ssl_context = ssl.create_default_context()
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        SafeRedirectHandler(site_key), urllib.request.HTTPSHandler(context=ssl_context), urllib.request.HTTPCookieProcessor(cookie_jar)
    )
    robots = urllib.robotparser.RobotFileParser(urllib.parse.urljoin(start_url, "/robots.txt"))
    try:
        robots.read()
    except OSError:
        robots = None
    while queue and len(visited) < max_pages and len(documents) < MAX_CRAWL_CHUNKS:
        if time.monotonic() - started_at > MAX_CRAWL_SECONDS:
            errors.append("Crawl stopped at the configured time limit.")
            break
        if visited:
            time.sleep(random.uniform(2, 5))
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        if robots and not robots.can_fetch("LocalWebResearchAssistant", url):
            errors.append(f"{url}: blocked by robots.txt")
            continue
        if progress:
            progress(len(visited), max_pages, url)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS)},
        )
        try:
            with opener.open(request, timeout=18) as response:
                final_url = validate_public_url(response.geturl(), site_key)
                if response.headers.get_content_type() != "text/html":
                    continue
                html = response.read(2_500_000).decode(
                    response.headers.get_content_charset() or "utf-8", errors="ignore"
                )
        except (OSError, ValueError, urllib.error.URLError) as error:
            errors.append(f"{url}: {error}")
            continue
        soup = BeautifulSoup(html, "html.parser")
        for element in soup(["script", "style", "svg", "noscript", "template"]):
            element.decompose()
        title = (soup.title.get_text(" ", strip=True) if soup.title else "") or urllib.parse.urlparse(final_url).path.strip("/") or site_key
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True)).strip()
        for index, chunk in enumerate(chunk_text(text), start=1):
            documents.append(
                {
                    "url": final_url,
                    "title": f"{title} · Part {index}",
                    "content": chunk,
                    "metadata": {"kind": "text", "word_count": len(chunk.split())},
                }
            )
        tables = [[[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])] for row in table.find_all("tr")] for table in soup.find_all("table")]
        documents.extend(table_documents(tables, final_url, title))
        for href in [anchor.get("href") for anchor in soup.find_all("a", href=True)]:
            normalized = normalize_url(final_url, href, site_key)
            if normalized and normalized not in visited and normalized not in queue:
                queue.append(normalized)
    return documents, len(visited), errors


def crawl_website(start_url, max_pages=MAX_CRAWL_PAGES, progress=None):
    start_url = validate_public_url(start_url)
    site_key = canonical_site_key(start_url)
    robots = urllib.robotparser.RobotFileParser(urllib.parse.urljoin(start_url, "/robots.txt"))
    try:
        robots.read()
        if not robots.can_fetch("LocalWebResearchAssistant", start_url):
            raise ValueError("The selected URL is disallowed by robots.txt.")
    except urllib.error.URLError:
        pass
    browser_errors = []
    try:
        documents, page_count, browser_errors = crawl_with_browser(
            start_url, site_key, max_pages, progress
        )
        if documents:
            return documents, page_count, browser_errors
    except Exception as error:
        browser_errors = [f"Browser crawler unavailable: {error}"]
    documents, page_count, http_errors = crawl_with_http(start_url, max_pages, progress)
    return documents, page_count, browser_errors + http_errors
