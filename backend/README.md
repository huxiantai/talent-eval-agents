# 后端服务

本目录是独立的 uv Python 项目，包含 FastAPI 应用、解析器、Chunk 流水线、Milvus 证据索引、数据库模型和自动化测试

## 主要模块

| 模块 | 用途 |
|---|---|
| `app/chunking.py` | Markdown 层级切分与递归兜底切分 |
| `app/chunk_service.py` | 解析结果对齐、策略自动判断与 Parent-Child 持久化 |
| `app/document_parsers.py` | DOCX、PPTX、Markdown 和音频转录的归一化文本解析 |
| `app/milvus_store.py` | Milvus Collection Schema、索引、Upsert、过滤和检索 |
| `app/evidence_index_service.py` | Chunk 向量化、索引任务执行与证据记录映射 |
| `app/model_provider.py` | 百炼 Chat 与 Embedding 模型配置 |

## 环境初始化

```bash
uv sync --dev
```

## 运行测试

```bash
uv run pytest tests -q
```

## 启动 API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 18080
```
