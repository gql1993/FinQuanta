"""
Collect public WeChat articles for event-study research.

This script is intentionally conservative: it only fetches public pages that are
available without login/captcha and uses a small request interval. If WeChat or
Sogou returns a verification page, the script records the blocker and stops.

Examples:
    python scripts/crawl_wechat_account.py --sogou-query "券商中国 股票" --pages 3
    python scripts/crawl_wechat_account.py --article-url-file data_cache/wechat_urls.txt
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


DEFAULT_OUTPUT = Path("data_cache/wechat_broker_china_articles.csv")
DEFAULT_STOCK_LIST = Path("data_cache/stock_list.csv")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
VERIFY_HINTS = ("验证码", "请输入验证码", "用户验证", "异常访问", "antispider", "请输入图片中的验证码")


@dataclass
class Article:
    source: str
    url: str
    title: str = ""
    publish_time: str = ""
    author: str = ""
    account_name: str = ""
    summary: str = ""
    content: str = ""
    stock_codes: str = ""
    stock_names: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = "ok"
    error: str = ""


class ContentTextParser(HTMLParser):
    """Small stdlib HTML-to-text parser for WeChat article content."""

    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._depth = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "div" and attr.get("id") == "js_content":
            self._capture = True
            self._depth = 1
            return
        if self._capture:
            self._depth += 1
            if tag in {"p", "br", "section"}:
                self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self._capture:
            return
        if tag in {"p", "section", "div"}:
            self._chunks.append("\n")
        self._depth -= 1
        if self._depth <= 0:
            self._capture = False

    def handle_data(self, data: str) -> None:
        if self._capture:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def text(self) -> str:
        joined = " ".join(self._chunks)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r"\n\s*\n+", "\n", joined)
        return html.unescape(joined).strip()


def fetch_url(url: str, *, timeout: int = 20) -> str:
    req = urllib.request.Request(
        sanitize_url(url),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def sanitize_url(url: str) -> str:
    """Quote unsafe characters that sometimes appear in Sogou result links."""
    parts = urllib.parse.urlsplit(url.strip())
    path = urllib.parse.quote(parts.path, safe="/:@")
    query = urllib.parse.quote(parts.query, safe="=&%:/?._-+")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


def is_verification_page(text: str) -> bool:
    lower = text.lower()
    return any(hint.lower() in lower for hint in VERIFY_HINTS)


def extract_js_string(page: str, names: Iterable[str]) -> str:
    for name in names:
        patterns = (
            rf"var\s+{re.escape(name)}\s*=\s*'((?:\\'|[^'])*)'",
            rf'var\s+{re.escape(name)}\s*=\s*"((?:\\"|[^"])*)"',
            rf"{re.escape(name)}\s*:\s*'((?:\\'|[^'])*)'",
            rf'{re.escape(name)}\s*:\s*"((?:\\"|[^"])*)"',
        )
        for pattern in patterns:
            match = re.search(pattern, page)
            if match:
                value = match.group(1).replace(r"\/", "/")
                try:
                    return json.loads(f'"{value}"')
                except json.JSONDecodeError:
                    return html.unescape(value.encode("utf-8").decode("unicode_escape", errors="ignore"))
    return ""


def extract_meta(page: str, names: Iterable[str]) -> str:
    for name in names:
        pattern = (
            r'<meta\s+[^>]*(?:property|name)=["\']'
            + re.escape(name)
            + r'["\'][^>]*content=["\']([^"\']*)["\'][^>]*>'
        )
        match = re.search(pattern, page, re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def normalize_publish_time(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.isdigit():
        timestamp = int(value)
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    return value


def parse_article(url: str, page: str, source: str) -> Article:
    parser = ContentTextParser()
    parser.feed(page)
    content = parser.text()
    title = extract_js_string(page, ("msg_title", "title")) or extract_meta(page, ("og:title", "twitter:title"))
    author = extract_js_string(page, ("author", "msg_author"))
    account = extract_js_string(page, ("nickname", "profile_nickname")) or extract_meta(page, ("og:article:author",))
    summary = extract_js_string(page, ("msg_desc", "desc")) or extract_meta(page, ("description", "og:description"))
    publish_time = normalize_publish_time(extract_js_string(page, ("publish_time", "ct")))
    return Article(
        source=source,
        url=url,
        title=title.strip(),
        publish_time=publish_time,
        author=author.strip(),
        account_name=account.strip(),
        summary=summary.strip(),
        content=content,
    )


def read_stock_list(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    stocks: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = str(row.get("code", "")).strip().zfill(6)
            name = str(row.get("name", "")).strip()
            if re.fullmatch(r"\d{6}", code) and name:
                stocks[code] = name
    return stocks


def annotate_stocks(article: Article, stocks: dict[str, str]) -> None:
    text = f"{article.title}\n{article.summary}\n{article.content}"
    codes = set(re.findall(r"(?<!\d)(?:00|30|60|68)\d{4}(?!\d)", text))
    names = set()
    for code, name in stocks.items():
        if name and len(name) >= 2 and name in text:
            codes.add(code)
            names.add(name)
    for code in codes:
        if code in stocks:
            names.add(stocks[code])
    article.stock_codes = ",".join(sorted(codes))
    article.stock_names = ",".join(sorted(names))


def extract_sogou_article_urls(page: str) -> list[str]:
    urls: list[str] = []
    for value in re.findall(r'href=["\']([^"\']+)["\']', page):
        value = html.unescape(value)
        if value.startswith("/link?"):
            value = "https://weixin.sogou.com" + value
        if "mp.weixin.qq.com" in value or "weixin.sogou.com/link?" in value:
            urls.append(value)
    return dedupe(urls)


def resolve_sogou_link(url: str) -> str:
    if "weixin.sogou.com/link?" not in url:
        return url
    try:
        req = urllib.request.Request(sanitize_url(url), headers={"User-Agent": USER_AGENT})
        opener = urllib.request.build_opener(NoRedirectHandler)
        opener.open(req, timeout=15)
    except urllib.error.HTTPError as exc:
        location = exc.headers.get("Location", "")
        if location:
            return location
    except Exception:
        pass
    return url


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def sogou_search_urls(query: str, pages: int, sleep_seconds: float) -> list[str]:
    urls: list[str] = []
    encoded = urllib.parse.quote(query)
    for page_no in range(1, pages + 1):
        url = f"https://weixin.sogou.com/weixin?type=2&query={encoded}&page={page_no}&ie=utf8"
        text = fetch_url(url)
        if is_verification_page(text):
            raise RuntimeError("Sogou returned a verification page; stop and retry later or use --article-url-file.")
        urls.extend(resolve_sogou_link(u) for u in extract_sogou_article_urls(text))
        time.sleep(sleep_seconds)
    return dedupe(urls)


def read_url_file(path: Path) -> list[str]:
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return dedupe(urls)


def dedupe(items: Iterable[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def write_articles(path: Path, rows: list[Article]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(asdict(Article(source="", url="")).keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def collect_articles(urls: list[str], stocks: dict[str, str], sleep_seconds: float) -> list[Article]:
    rows: list[Article] = []
    for idx, url in enumerate(urls, start=1):
        print(f"[{idx}/{len(urls)}] fetching {url}", file=sys.stderr)
        try:
            page = fetch_url(url)
            if is_verification_page(page):
                rows.append(Article(source="wechat", url=url, status="blocked", error="verification page"))
                break
            article = parse_article(url, page, source="wechat")
            annotate_stocks(article, stocks)
            rows.append(article)
        except Exception as exc:
            rows.append(Article(source="wechat", url=url, status="error", error=str(exc)))
        time.sleep(sleep_seconds)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl public WeChat articles for 券商中国 event research.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sogou-query", help='Sogou Weixin search query, e.g. "券商中国 股票"')
    source.add_argument("--article-url-file", type=Path, help="Text file with one public WeChat article URL per line")
    parser.add_argument("--pages", type=int, default=3, help="Sogou search pages to scan")
    parser.add_argument("--sleep-seconds", type=float, default=3.0, help="Delay between requests")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output CSV path")
    parser.add_argument("--stock-list", type=Path, default=DEFAULT_STOCK_LIST, help="A-share stock list CSV")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stocks = read_stock_list(args.stock_list)
    try:
        if args.article_url_file:
            urls = read_url_file(args.article_url_file)
        else:
            urls = sogou_search_urls(args.sogou_query, args.pages, args.sleep_seconds)
    except Exception as exc:
        print(f"failed to collect article URLs: {exc}", file=sys.stderr)
        return 2

    if not urls:
        print("no article URLs found", file=sys.stderr)
        return 1

    rows = collect_articles(urls, stocks, args.sleep_seconds)
    write_articles(args.output, rows)
    ok = sum(1 for row in rows if row.status == "ok")
    print(f"saved {len(rows)} rows ({ok} ok) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
