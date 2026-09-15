from concurrent.futures import ThreadPoolExecutor
import csv
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from html import unescape
import io
import json
import mimetypes
import os
import re
import socket
import sys
import urllib.parse
import urllib.request
import zipfile


ROOT = os.path.dirname(os.path.abspath(__file__))
MAX_EXPORT_ITEMS = 160
MAX_IMAGE_BYTES = 12 * 1024 * 1024
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


def safe_filename(value):
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", str(value or ""), flags=re.UNICODE).strip("_")
    return value[:32] or "image"


def extension_for(url, content_type):
    path = urllib.parse.urlparse(url).path
    ext = os.path.splitext(path)[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if ext == ".jpeg" else ext
    guessed = mimetypes.guess_extension(content_type or "")
    if guessed in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if guessed == ".jpeg" else guessed
    return ".jpg"


def fetch_binary(url, referer=None, timeout=14):
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image too large")
        return raw, resp.headers.get_content_type()


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


def download_export_item(payload):
    index, item = payload
    urls = [item.get("image"), item.get("thumb")]
    for url in urls:
        if not valid_url(url):
            continue
        try:
            raw, content_type = fetch_binary(url, referer=item.get("page"))
            name = "{:03d}_{}_{}{}".format(
                index,
                safe_filename(item.get("taskId") or item.get("query")),
                safe_filename(item.get("query")),
                extension_for(url, content_type),
            )
            return {"ok": True, "item": item, "name": name, "raw": raw}
        except Exception:
            continue
    return {"ok": False, "item": item, "name": "", "raw": b""}


def make_export_zip(items):
    items = items[:MAX_EXPORT_ITEMS]
    jobs = [(index, item) for index, item in enumerate(items, 1)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(download_export_item, jobs))

    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["序号", "文件名", "段落编号", "搜索词", "标题", "来源", "来源页面", "对应段落"])

    memory = io.BytesIO()
    with zipfile.ZipFile(memory, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        failed = []
        for index, result in enumerate(results, 1):
            item = result["item"]
            filename = result["name"]
            if result["ok"]:
                archive.writestr(f"images/{filename}", result["raw"])
            else:
                failed.append(f"{index:03d} {item.get('query') or ''}")
            writer.writerow(
                [
                    f"{index:03d}",
                    filename,
                    item.get("taskId", ""),
                    item.get("query", ""),
                    item.get("title", ""),
                    item.get("source", ""),
                    item.get("page", ""),
                    item.get("segment", ""),
                ]
            )
        archive.writestr("素材清单.csv", "\ufeff" + csv_buffer.getvalue())
        if failed:
            archive.writestr("下载失败.txt", "\n".join(failed))

    memory.seek(0)
    return memory.getvalue()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/search":
            self.handle_search(parsed)
            return
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/export":
            self.handle_export()
            return
        self.send_error(404)

    def handle_search(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        query = (params.get("q") or [""])[0].strip()
        page = int((params.get("page") or ["0"])[0] or 0)
        count = min(max(int((params.get("count") or ["40"])[0] or 40), 10), 60)
        if not query:
            self.write_json({"items": []})
            return
        self.write_json({"items": search_all(query, page, count)})

    def handle_export(self):
        try:
            length = min(int(self.headers.get("Content-Length", "0") or 0), 2_000_000)
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body or "{}")
            items = data.get("items") or []
            if not isinstance(items, list) or not items:
                self.write_json({"error": "no items"}, status=400)
                return
            body = make_export_zip(items)
        except Exception:
            self.write_json({"error": "export failed"}, status=500)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Disposition", 'attachment; filename="juhai-jianying-images.zip"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def write_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
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
