# MinerU 本地解析运行时

该目录是复杂 PDF 与扫描件的本地私有解析运行时，环境文件位于后端目录内部

```bash
uv sync --project backend/mineru-runtime
uv run --project backend/mineru-runtime mineru-api --host 127.0.0.1 --port 18001
```

首次解析会从配置的模型源下载模型，CPU 环境使用 pipeline 后端
