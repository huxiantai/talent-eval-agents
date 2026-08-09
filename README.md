# 多 Agent 人才评估与推荐系统

课程贯穿项目的统一代码根目录

## 当前目录

| 路径 | 用途 |
|---|---|
| `backend/` | FastAPI 后端、uv 环境、依赖锁、解析器、数据模型与测试 |
| `database/init.sql` | PostgreSQL 完整建表 SQL |
| `frontend/` | React 前端 |
| `docker-compose.yml` | PostgreSQL、MinIO、Redis 等基础服务 |

## 产品定位

前端是多 Agent 人才评估与推荐系统的统一应用壳层，人才档案模块包含员工花名册和档案资料库。花名册维护结构化员工数据，提供新建员工和每页 10 人分页。档案资料库通过知识库下拉框切换文件集合，文件表按每页 10 条分页。文件详情展示原文件、解析结果与基础元数据，切片预览保留空状态，第 5 课再实现切片数据

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


## 后端验证

```bash
cd backend
uv sync --dev
uv run pytest tests -q
```

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

宿主机端口为 PostgreSQL 15432、Redis 16379、MinIO 19000、MinIO Console 19001、后端 18080、前端 15173

后端容器通过 `S3_ENDPOINT_URL=http://minio:9000` 访问 MinIO，通过 `S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000` 生成浏览器可访问的预签名 URL

## MinerU 本地服务

macOS 使用宿主机 uv 环境启动 MinerU，避免把内部材料发送给外部解析接口

```bash
uv sync --project backend/mineru-runtime
uv run --project backend/mineru-runtime mineru-api --host 127.0.0.1 --port 18001
```
