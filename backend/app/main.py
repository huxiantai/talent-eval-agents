from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import router
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="人才文档解析 API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins.split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"service": "talent-document-api", "status": "ok"}

    app.include_router(router)
    return app


app = create_app()
