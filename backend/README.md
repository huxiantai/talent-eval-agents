# 后端服务

本目录是独立的 uv Python 项目，包含 FastAPI 应用、解析器、Chunk 流水线、数据库模型和自动化测试

## 主要模块

| 模块 | 用途 |
|---|---|
| `app/chunking.py` | 固定、递归、Markdown、语义与面试问答切片 |
| `app/chunk_service.py` | Markdown 与来源元素对齐、Parent 树持久化和离线评估 |
| `app/chunk_evaluation.py` | 覆盖率、Boundary F1、证据完整率和分散度 |
| `app/model_provider.py` | 百炼 ChatOpenAI 与 DashScopeEmbeddings 配置 |

语义分片使用 `langchain_experimental.text_splitter.SemanticChunker`，中文句子通过 `(?<=[。！？.!?])\s*` 识别句界。百炼模型通过根目录 `.env` 配置

所有非面试材料在解析阶段统一转换为多级 Markdown，自动模式固定使用 Markdown 层级分片

Markdown 标题路径生成多级 Parent 树，正文 Chunk 关联最近一级 Parent，缺少分级标题时只生成独立 Child

解析产物统一为多级 Markdown 与 `content_list`，不同来源的定位对象统一聚合到 `source_locators`

- Markdown 使用字符区间
- DOCX 使用段落或表格序号
- PPTX 使用 Slide、Shape 与 bbox
- PDF 和图片使用 MinerU page 与 bbox
- 语音转录使用时间区间

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
