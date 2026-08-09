# 后端服务

本目录是独立的 uv Python 项目，包含 FastAPI 应用、解析器、数据库模型和自动化测试

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
