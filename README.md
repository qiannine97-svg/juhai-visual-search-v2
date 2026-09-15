# 聚海画面素材搜索器v2

聚海云科旗下的画面素材搜索工具。输入长文案后，自动按段落提取画面关键词，并聚合图片搜索结果。

## 本地运行

```bash
python server.py
```

然后打开：

```text
http://localhost:4174/
```

## 部署

云端平台使用 `Procfile` 启动：

```text
web: python server.py
```

服务会自动读取平台提供的 `PORT` 环境变量。
