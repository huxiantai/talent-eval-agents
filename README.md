# 多 Agent 人才评估与推荐系统

课程贯穿项目的统一代码根目录

## 当前目录

| 路径 | 用途 |
|---|---|
| `backend/` | FastAPI 后端、uv 环境、依赖锁、解析器、数据模型与测试 |
| `database/init.sql` | PostgreSQL 完整建表 SQL |
| `database/migrations/005_chunking.sql` | 第 5 课 Chunk、标注与评估表的幂等增量迁移 |
| `database/migrations/006_chunk_source_locators.sql` | 为已有 Chunk 表增加统一来源定位字段 |
| `database/migrations/007_milvus_evidence_index.sql` | 第 6 课 Milvus 索引任务表的幂等增量迁移 |
| `frontend/` | React 前端 |
| `docker-compose.yml` | PostgreSQL、MinIO、Redis 等基础服务 |

## 产品定位

前端是多 Agent 人才评估与推荐系统的统一应用壳层，人才档案模块包含员工花名册和档案资料库。花名册维护结构化员工数据，提供新建员工和每页 10 人分页。档案资料库通过知识库下拉框切换文件集合，文件表按每页 10 条分页。文件详情展示原文件、解析结果、切片预览与基础元数据。切片预览支持策略参数、Parent-Child 关系、来源元素、人工边界标注、问题证据标注和离线质量指标

## 人才档案接口

| 接口 | 用途 |
|---|---|
| `GET /api/employees` | 查询员工花名册及关联材料数量 |
| `POST /api/employees` | 新建结构化员工档案 |
| `GET /api/knowledge-bases` | 查询档案知识库及文件数量 |
| `POST /api/knowledge-bases` | 创建档案知识库 |
| `GET /api/documents` | 查询知识库文件 |
| `POST /api/documents` | 上传文件并关联员工与知识库 |
| `GET /api/documents/{id}` | 查询原文件、基础元数据、解析任务与 Markdown 产物 |
| `POST /api/documents/{id}/parse` | 创建异步解析任务 |
| `GET /api/documents/{id}/chunks` | 查询最新一次成功切片及 Parent-Child 关系 |
| `POST /api/documents/{id}/chunks` | 按固定、递归、Markdown、语义或问答策略生成切片 |
| `POST /api/documents/{id}/chunk-annotations` | 保存人工业务边界与问题证据标注 |
| `GET /api/documents/{id}/chunk-evaluation` | 计算内容覆盖、Boundary F1、证据完整率与分散度 |
| `POST /api/documents/{id}/evidence-index` | 创建当前文档版本的异步 Milvus 索引任务 |
| `POST /api/evidence/search` | 按租户、权限范围和业务条件检索人才证据 |
| `POST /api/index-jobs/{id}/retry` | 为失败的 Milvus 索引任务创建新的幂等重试任务 |

## Chunk 模块

| 路径 | 用途 |
|---|---|
| `backend/app/chunking.py` | 固定、递归、Markdown 层级、中文语义与面试问答分片 |
| `backend/app/chunk_service.py` | Markdown 与来源元素对齐、多级 Parent 树持久化和评估编排 |
| `backend/app/chunk_evaluation.py` | 内容覆盖、边界和问题证据指标计算 |
| `backend/app/model_provider.py` | 阿里云百炼 Chat 与 Embedding 模型工厂 |

语义分片读取仓库根目录 `.env` 中的 `DASHSCOPE_API_KEY`、`CHAT_MODEL` 与 `EMBEDDING_MODEL`。`.env` 已被 Git 忽略，`.env.example` 只保留非敏感占位配置

自动模式固定使用 Markdown 层级分片，不根据材料类型切换算法。非面试材料在解析阶段统一生成多级 Markdown，MinerU 的 `content_list.json` 只补充页码和来源元素

DOCX 使用 `python-docx` 保留标题样式与表格，PPTX 保留 Slide、Shape 与 bbox，PDF 和图片统一通过 MinerU 保留标题、页码与 bbox，原生 Markdown 使用字符区间，语音转录使用时间区间

不同格式的定位对象统一写入 `document_chunks.source_locators`

已有数据库应用第 5 课增量迁移

```bash
docker compose -p talent-eval-agents-course exec -T postgres \
  psql -U talent -d talent_docs -v ON_ERROR_STOP=1 -f /dev/stdin \
  < database/migrations/005_chunking.sql

docker compose -p talent-eval-agents-course exec -T postgres \
  psql -U talent -d talent_docs -v ON_ERROR_STOP=1 -f /dev/stdin \
  < database/migrations/006_chunk_source_locators.sql
```

## Milvus 证据索引

Milvus 作为独立向量检索服务，PostgreSQL 继续保存文档、版本、Chunk 和索引任务状态

| 路径 | 用途 |
|---|---|
| `backend/app/milvus_store.py` | Collection Schema、HNSW、Upsert、标量过滤、搜索与按版本删除 |
| `backend/app/evidence_index_service.py` | Chunk 向量化、Evidence Record 映射、索引任务执行与状态更新 |
| `backend/scripts/verify_milvus.py` | 使用确定性向量验证 Collection、Upsert、权限过滤和 HNSW 搜索 |
| `backend/tests/test_milvus_store.py` | Milvus 存储适配器的行为回归测试 |
| `backend/tests/test_evidence_index_service.py` | Chunk 到 Evidence Record 的转换与索引编排测试 |

开发环境使用 Milvus Standalone 2.6.17、etcd 和已有 MinIO

- 宿主机 Milvus gRPC 端口为 `19531`

- 宿为 Milvus 健康检查端口为 `19091`

- 容器内 backend 与 worker 通过 `http://milvus:19530` 访问

已有数据库应用第 6 课增量迁移

```bash
docker compose -p talent-eval-agents-course exec -T postgres \
  psql -U talent -d talent_docs -v ON_ERROR_STOP=1 -f /dev/stdin \
  < database/migrations/007_milvus_evidence_index.sql
```

启动服务并执行 Milvus 独立验收

```bash
docker compose -p talent-eval-agents-course up -d
cd backend
uv run python -m scripts.verify_milvus
```

验收脚本的实际运行结果

```json
{"collection": "lesson6_verification_v1", "upserted": 2, "matched": 1, "top_candidate": "C001", "top_score": 1.0, "permission_scope": "hr_private"}
```

Collection 默认使用 1024 维向量、COSINE 距离和 HNSW 索引

- `M=16`

- `efConstruction=128`

- 查询默认 `ef=80`

- 常规查询默认使用 Bounded consistency

- 写后读验收使用 Strong consistency


## 后端验证

```bash
cd backend
uv sync --dev
uv run pytest tests -q
```

当前第 6 课回归结果为 `71 passed`

## 服务日志

backend 与 worker 使用统一 Python 日志配置，控制台日志同时写入 `backend/logs/`

```text
backend/logs/backend-YYYY-MM-DD.log
backend/logs/backend-error-YYYY-MM-DD.log
backend/logs/worker-YYYY-MM-DD.log
backend/logs/worker-error-YYYY-MM-DD.log
```

普通日志记录 HTTP 请求、员工与知识库写入、文件上传、MinIO 读写、解析任务、产物和 Worker 消费过程。ERROR 及以上日志额外写入对应服务的独立 error 文件。服务跨越零点运行时自动切换到新的日期文件

本地运行默认使用 `backend/logs/`。Compose 为 backend 和 worker 配置 `LOG_DIR=/app/logs` 与 `TZ=Asia/Shanghai`，并将宿主机 `./backend/logs` 挂载到两个容器的 `/app/logs`

## 基础服务

本项目使用独立 Compose 项目名 `talent-eval-agents-course`，并采用避让后的宿主机端口

```bash
cd frontend
npm install
npm run build
cd ..
docker compose -p talent-eval-agents-course up -d
docker compose -p talent-eval-agents-course ps
```

前端采用 React、TypeScript 与 Vite。Docker 使用 Node.js 多阶段构建前端产物，再由 Nginx 托管 `dist`

宿主机端口为 PostgreSQL 15432、Redis 16379、MinIO 19000、MinIO Console 19001、Milvus 19531、Milvus 健康检查 19091、后端 18080、前端 15173

后端容器通过 `S3_ENDPOINT_URL=http://minio:9000` 访问 MinIO，通过 `S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000` 生成浏览器可访问的预签名 URL

## MinerU 本地服务

macOS 使用宿主机 uv 环境启动 MinerU，避免把内部材料发送给外部解析接口

```bash
uv sync --project backend/mineru-runtime
uv run --project backend/mineru-runtime mineru-api --host 127.0.0.1 --port 18001
```
