from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html import unescape
import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request


ROOT = os.path.dirname(os.path.abspath(__file__))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}


def fetch(url, referer=None, timeout=10):
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")


def clean_title(value):
    value = unescape(re.sub(r"<[^>]+>", "", str(value or "")))
    return re.sub(r"\s+", " ", value).strip()[:120]


def valid_url(value):
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def baidu_images(query, page, count):
    pn = max(page, 0) * count
    params = urllib.parse.urlencode(
        {
            "tn": "resultjson_com",
            "ipn": "rj",
            "ct": "201326592",
            "fp": "result",
            "queryWord": query,
            "word": query,
            "pn": str(pn),
            "rn": str(count),
        }
    )
    text = fetch(
        f"https://image.baidu.com/search/acjson?{params}",
        referer="https://image.baidu.com/",
        timeout=12,
    )
    data = json.loads(text.lstrip("\ufeff"))
    items = []
    for row in data.get("data", []):
        thumb = row.get("thumbURL") or row.get("middleURL")
        image = row.get("objURL") or row.get("middleURL") or thumb
        replace = row.get("replaceUrl") or [{}]
        replace_url = replace[0].get("ObjURL") if isinstance(replace, list) and replace else ""
        page_url = row.get("fromURL") or replace_url or image
        if not valid_url(thumb):
            continue
        items.append(
            {
                "id": "baidu-" + str(row.get("di") or row.get("cs") or thumb),
                "source": "百度图片",
                "title": clean_title(row.get("fromPageTitleEnc") or row.get("fromPageTitle") or query),
                "thumb": thumb,
                "image": image if valid_url(image) else thumb,
                "page": page_url if valid_url(page_url) else image,
            }
        )
    return items


def bing_images(query, page, count):
    first = max(page, 0) * count
    params = urllib.parse.urlencode({"q": query, "first": str(first), "count": str(count), "adlt": "off"})
    html = fetch(f"https://www.bing.com/images/async?{params}", timeout=12)
    items = []
    for raw in re.findall(r'm="([^"]+)"', html):
        try:
            data = json.loads(unescape(raw))
        except json.JSONDecodeError:
            continue
        thumb = data.get("turl")
        image = data.get("murl") or thumb
        page_url = data.get("purl") or image
        if not valid_url(thumb):
            continue
        items.append(
            {
                "id": "bing-" + str(data.get("md5") or thumb),
                "source": "必应图片",
                "title": clean_title(data.get("t") or query),
                "thumb": thumb,
                "image": image if valid_url(image) else thumb,
                "page": page_url if valid_url(page_url) else image,
            }
        )
    return items


def search_all(query, page, count):
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(baidu_images, query, page, count), pool.submit(bing_images, query, page, count)]
        items = []
        for future in futures:
            try:
                items.extend(future.result())
            except Exception:
                pass

    seen = set()
    unique = []
    for item in items:
        key = item["image"] or item["thumb"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[: count * 2]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/search":
            self.handle_search(parsed)
            return
        super().do_GET()

    def handle_search(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        query = (params.get("q") or [""])[0].strip()
        page = int((params.get("page") or ["0"])[0] or 0)
        count = min(max(int((params.get("count") or ["40"])[0] or 40), 10), 60)
        if not query:
            self.write_json({"items": []})
            return
        self.write_json({"items": search_all(query, page, count)})

    def write_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    cloud_port = os.environ.get("PORT")
    port = int(cloud_port or (sys.argv[1] if len(sys.argv) > 1 else 4174))
    host = "0.0.0.0" if cloud_port else "127.0.0.1"
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError:
        if cloud_port:
            raise
        with socket.socket() as sock:
            sock.bind((host, 0))
            port = sock.getsockname()[1]
        httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://localhost:{port}/"
    try:
        with open(os.path.join(ROOT, "server-url.txt"), "w", encoding="utf-8") as file:
            file.write(url + "\n")
    except OSError:
        pass
    print(url, flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
