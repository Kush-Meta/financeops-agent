"""FinanceOps Agent API entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import DATA_DIR, get_settings
from app.core.database import SessionLocal, init_db
from app.core.logging import setup_logging
from app.models import Account


def _ensure_seeded() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        count = db.query(Account).count()
        if count == 0:
            from app.scripts.seed import seed
            from app.adapters.persist import import_real_public_data
            from app.services.audit import register_audit_immutability

            seed(db)
            try:
                import_real_public_data(db)
            except FileNotFoundError:
                pass
            register_audit_immutability()
        else:
            from app.services.audit import register_audit_immutability

            register_audit_immutability()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    Path(settings.documents_dir).mkdir(parents=True, exist_ok=True)
    _ensure_seeded()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI-powered finance operations: reconciliation, variance, anomalies, audit.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix=settings.api_prefix)
    return app


app = create_app()
