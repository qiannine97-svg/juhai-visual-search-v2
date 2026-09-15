import io
import zipfile

import server


def fake_fetch_binary(url, referer=None, timeout=14):
    return b"fake-image:" + url.encode("utf-8"), "image/jpeg"


server.fetch_binary = fake_fetch_binary

items = [
    {
        "taskId": "S01",
        "order": 1,
        "query": "说话 口播 人物",
        "title": "第一张",
        "source": "测试",
        "page": "https://example.com/1",
        "image": "https://example.com/1.jpg",
        "segment": "今儿咱说个事儿",
    },
    {
        "taskId": "S02",
        "order": 2,
        "query": "不好意思 尴尬 表情",
        "title": "第二张",
        "source": "测试",
        "page": "https://example.com/2",
        "image": "https://example.com/2.jpg",
        "segment": "说出来丢人",
    },
]

body = server.make_export_zip(items)
with zipfile.ZipFile(io.BytesIO(body)) as archive:
    names = archive.namelist()
    assert names[0].startswith("images/001_S01_"), names
    assert names[1].startswith("images/002_S02_"), names
    assert "素材清单.csv" in names, names

print("导出自检通过：图片 zip 按段落顺序命名。")
