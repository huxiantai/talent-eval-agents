# 多 Agent 人才评估与推荐系统

课程贯穿项目的统一代码根目录

## 当前目录

| 路径 | 用途 |
|---|---|
| `backend/` | FastAPI 后端、uv 环境、依赖锁、解析器、数据模型与测试 |
| `database/init.sql` | PostgreSQL 完整建表 SQL |
| `database/migrations/005_chunking.sql` | 第 4 课到第 5 课的唯一幂等增量迁移 |
| `database/migrations/007_milvus_evidence_index.sql` | 第 6 课 Milvus 索引任务表的幂等增量迁移 |
| `frontend/` | React 前端 |
| `docker-compose.yml` | 默认启动 PostgreSQL、MinIO、Redis；`app` profile 启动 backend、worker、frontend |

## 产品定位

前端是多 Agent 人才评估与推荐系统的统一应用壳层，人才档案模块包含员工花名册和档案资料库。花名册维护结构化员工数据，提供新建员工和每页 10 人分页。档案资料库通过知识库下拉框切换文件集合，文件表按每页 10 条分页，上传后自动排入解析、切片和 Milvus 索引链路，同时支持批量删除材料与关联数据。文件详情展示原文件、解析结果、索引记录、切片预览与基础元数据。档案资料库页面内置证据召回测试，可输入查询并附带候选人、材料类型和权限范围过滤项，直接查看匹配 Chunk、相似度分数和来源材料

## 运行模式

本项目只维护一套中间件环境：PostgreSQL、Redis、MinIO 始终由 Docker Compose 托管。开发模式和发布模式都共用这三类基础服务。

所有 Docker Compose 命令统一使用项目名参数 `-p talent-eval-agents-course`。

### 开发模式

开发模式的目标是保留前后端热更新，同时继续复用 Compose 内的中间件。

1. 启动基础设施

```bash
docker compose -p talent-eval-agents-course up -d postgres redis minio
```

2. 启动 MinerU 本地服务

```bash
uv sync --project backend/mineru-runtime
uv run --project backend/mineru-runtime mineru-api --host 127.0.0.1 --port 18001
```

3. 启动后端 API

```bash
cd backend
uv sync --dev
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 18080
```

4. 启动本地 worker

```bash
cd backend
uv run python -m app.worker
```

5. 启动前端开发服务器

```bash
cd frontend
npm install
npm run dev
```

开发模式下的更新规则：

- 改前端页面：Vite 自动热更新，不需要重启 Docker
- 改后端 API：`uvicorn --reload` 自动重载，不需要重建镜像
- 改 worker、解析流水线或队列消费逻辑：手动重启本地 `uv run python -m app.worker`
- 改数据库结构：对已有数据库执行 migration；只有新建数据库卷时才会读取 `database/init.sql`

### 发布模式

发布模式用于测试环境、演示环境和生产口径的容器化运行。backend、worker、frontend 会和中间件一起由 Compose 托管。

```bash
docker compose -p talent-eval-agents-course --profile app up -d --build
```

发布模式下的更新规则：

- 改前端代码：`docker compose -p talent-eval-agents-course --profile app up -d --build frontend`
- 改后端代码：`docker compose -p talent-eval-agents-course --profile app up -d --build backend worker`
- 前后端都改了：`docker compose -p talent-eval-agents-course --profile app up -d --build`
- 只改了环境变量、挂载文件或容器运行参数，没有改镜像内容：`docker compose -p talent-eval-agents-course --profile app restart backend worker frontend`

`docker restart` 或 `docker compose restart` 只会重启旧容器，不会重新构建镜像，也不会把你本地新改的源码带进去。所以发布模式下只要改了代码，就必须用 `up -d --build`，不能只用 `restart`。


## 人才档案接口

| 接口 | 用途 |
|---|---|
| `GET /api/employees` | 查询员工花名册及关联材料数量 |
| `POST /api/employees` | 新建结构化员工档案 |
| `GET /api/knowledge-bases` | 查询档案知识库及文件数量 |
| `POST /api/knowledge-bases` | 创建档案知识库 |
| `GET /api/documents` | 查询知识库文件 |
| `POST /api/documents` | 上传文件、关联员工与知识库，并自动创建解析任务 |
| `DELETE /api/documents` | 批量删除文档，同时删除原文件、解析产物、切片和 Milvus 向量 |
| `GET /api/documents/{id}` | 查询原文件、基础元数据、解析任务、索引任务与 Markdown 产物 |
| `POST /api/documents/{id}/parse` | 创建异步解析任务 |
| `GET /api/documents/{id}/chunks` | 查询最新一次成功切片及 Parent-Child 关系 |
| `POST /api/documents/{id}/chunks` | 按材料结构自动执行 Markdown 结构化切分或纯文本递归切分 |
| `POST /api/documents/{id}/evidence-index` | 为当前文档版本手动创建异步 Milvus 索引任务 |
| `POST /api/evidence/search` | 按租户、权限范围和业务条件检索人才证据，并返回来源材料与候选人上下文（纯向量） |
| `POST /api/evidence/hybrid-search` | 稠密 + BM25 双路召回、RRF 融合、Rerank 精排的证据检索 |
| `POST /api/index-jobs/{id}/retry` | 为失败的 Milvus 索引任务创建新的幂等重试任务 |

## Chunk 模块

| 路径 | 用途 |
|---|---|
| `backend/app/chunking.py` | Markdown 层级切分与递归兜底切分 |
| `backend/app/chunk_service.py` | 解析结果对齐、策略自动判断与 Parent-Child 持久化 |
| `backend/app/document_parsers.py` | DOCX/PPTX/Markdown/音频转录的归一化文本解析 |

第 5 课的代码口径是先统一把材料归一化成可切分文本，再由后端根据结构自动选择切分方式，不再让前端指定策略

默认规则如下

- Markdown、DOCX、PPTX、MinerU 解析后的 PDF 和图片：优先走 Markdown 结构化切分，再建立 Parent-Child
- 语音转录：只保留纯文本和时间区间，直接走递归切分
- DOCX：使用 `python-docx` 读取 OOXML 样式后转成 Markdown
- PPTX：使用 OOXML 解析幻灯片文本并转成 Markdown
- PDF 和图片：统一走 MinerU，保留标题层级、页码和 bbox
- 前端不暴露策略选择，只允许调整 `chunk_size` 和 `chunk_overlap`

所有 Chunk 使用 `markdown_start` 和 `markdown_end` 定位归一化 Markdown

PDF、图片、PPTX 和音频的辅助定位写入 `document_chunks.source_locators`

Markdown 和 DOCX 的 `source_locators` 为空数组

## 第 5 课数据库变更

`005_chunking.sql` 集中包含第 5 课的全部数据库变更

- 新增 `chunking_status` 枚举
- 新增 `chunk_strategy` 枚举
- 新增 `chunking_runs` 切片运行表
- 新增 `document_chunks` Chunk 表
- 新增切片运行、文档版本和候选人查询索引
- `document_chunks` 保存 Parent-Child、前后 Chunk 和标题路径
- `document_chunks` 新增 Markdown 起止偏移
- `document_chunks` 新增原文件辅助定位集合

### 从第 4 课迁移到第 5 课

先确保 PostgreSQL 已经通过同一个项目名启动：

```bash
docker compose -p talent-eval-agents-course up -d postgres
```

然后在代码仓库根目录执行一次以下命令

```bash
docker compose -p talent-eval-agents-course exec -T postgres \
  psql -U talent -d talent_docs -v ON_ERROR_STOP=1 -f /dev/stdin \
 < database/migrations/005_chunking.sql
```
迁移脚本使用 `IF NOT EXISTS` 与重复对象处理，可以在已执行旧版 `005` 的开发环境中再次执行。

全新环境由 `database/init.sql` 直接创建最新结构，不需要再执行增量迁移

## Milvus 证据索引

Milvus 作为独立向量检索服务，PostgreSQL 继续保存文档、版本、Chunk 和索引任务状态

| 路径 | 用途 |
|---|---|
| `backend/app/milvus_store.py` | Collection Schema、HNSW、Upsert、标量过滤、搜索与按版本删除 |
| `backend/app/evidence_index_service.py` | Chunk 向量化、Evidence Record 映射、索引任务执行与状态更新 |
| `backend/app/document_pipeline.py` | 上传后的自动解析、自动切片、自动索引编排与处理状态汇总 |
| `backend/app/document_cleanup.py` | 文档删除时的对象存储、PostgreSQL 和 Milvus 级联清理 |
| `backend/scripts/verify_milvus.py` | 使用确定性向量验证 Collection、Upsert、权限过滤和 HNSW 搜索 |
| `backend/tests/test_milvus_store.py` | Milvus 存储适配器的行为回归测试 |
| `backend/tests/test_evidence_index_service.py` | Chunk 到 Evidence Record 的转换与索引编排测试 |
| `backend/tests/test_document_pipeline.py` | 自动处理编排与任务入队测试 |
| `backend/tests/test_document_cleanup.py` | 材料删除时的跨存储级联清理测试 |

开发环境使用 Milvus Standalone 2.6.17、etcd 和已有 MinIO

- 宿主机 Milvus gRPC 端口：`19531`
- 宿主机 Milvus 健康检查端口：`19091`
- 容器内 backend 与 worker 通过 `http://milvus:19530` 访问

先确保 PostgreSQL 已经通过同一个项目名启动：

```bash
docker compose -p talent-eval-agents-course up -d postgres
```

然后在代码仓库根目录执行：

```bash
docker compose -p talent-eval-agents-course exec -T postgres \
  psql -U talent -d talent_docs -v ON_ERROR_STOP=1 -f /dev/stdin \
  < database/migrations/007_milvus_evidence_index.sql
```

全新环境由 `database/init.sql` 直接创建最新结构，不需要再执行增量迁移

启动服务并执行 Milvus 独立验收：

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

## 混合检索与精排

Collection `talent_evidence_v2` 在稠密向量之外增加 BM25 稀疏向量，由 Milvus 原生 Function 在写入时从 `content` 自动生成，`content` 使用 `chinese`（jieba + cnalphanumonly）分析器分词

| 路径 | 用途 |
|---|---|
| `backend/app/reranker.py` | DashScope `gte-rerank-v2` 的 Cross-Encoder 精排封装 |
| `backend/app/hybrid_search_service.py` | 稠密 + BM25 召回、RRF 融合、Rerank 精排的编排 |
| `backend/scripts/verify_hybrid.py` | 对比纯向量、纯 BM25、混合召回和精排的召回与延迟 |
| `backend/scripts/import_markdown_reviews.py` | 上传 5 份项目复盘 Markdown 并走完解析、切片、索引 |
| `backend/tests/test_hybrid_search_service.py` | 混合检索编排与 Rerank 映射的回归测试 |

稠密召回使用 `text-embedding-v3` 生成 1024 维查询向量，BM25 召回直接传入查询原文，两路结果由 `RRFRanker(k=60)` 融合，最后用 `gte-rerank-v2` 对候选做 Cross-Encoder 精排

相关配置

- `RERANK_MODEL`：精排模型，默认 `gte-rerank-v2`

- `RERANK_TOP_N`：精排候选数，默认 20

- `MILVUS_COLLECTION`：证据集合，当前为 `talent_evidence_v2`

混合检索验收

```bash
cd backend
uv run python -m scripts.verify_hybrid "有 Flink 实时计算经验的数据平台工程师" 5
```

## 验证

```bash
cd backend
uv sync --dev
uv run pytest tests -q
```

当前回归结果以本次本地 `pytest` 结果为准

当前本地结果：`82 passed, 2 warnings`

## 服务日志

backend 与 worker 使用统一 Python 日志配置，控制台日志同时写入 `backend/logs/`

```text
backend/logs/backend-YYYY-MM-DD.log
backend/logs/backend-error-YYYY-MM-DD.log
backend/logs/worker-YYYY-MM-DD.log
backend/logs/worker-error-YYYY-MM-DD.log
```

普通日志记录 HTTP 请求、员工与知识库写入、文件上传、MinIO 读写、解析任务、产物和 Worker 消费过程。ERROR 及以上日志额外写入对应服务的独立 error 文件。服务跨越零点运行时自动切换到新的日期文件

本地运行默认使用 `backend/logs/`。发布模式下，Compose 为 backend 和 worker 配置 `LOG_DIR=/app/logs` 与 `TZ=Asia/Shanghai`，并将宿主机 `./backend/logs` 挂载到容器内

## 端口约定

- PostgreSQL：`15432`
- Redis：`16379`
- MinIO API：`19000`
- MinIO Console：`19001`
- Milvus gRPC：`19531`
- Milvus Health：`19091`
- Backend API：`18080`
- Frontend：`15173`
