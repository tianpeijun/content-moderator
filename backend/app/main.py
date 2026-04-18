"""FastAPI application entry point."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum

from backend.app.api.admin_logs import router as admin_logs_router
from backend.app.api.admin_model_config import router as admin_model_config_router
from backend.app.api.admin_prompt import router as admin_prompt_router
from backend.app.api.admin_rules import router as admin_rules_router
from backend.app.api.admin_stats import router as admin_stats_router
from backend.app.api.admin_test import router as admin_test_router
from backend.app.api.admin_labels import router as admin_labels_router
from backend.app.api.moderation import router as moderation_router
from backend.app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    description="商城评论内容审核系统 API",
    version="1.0.0",
)

# Auto-create database tables on startup (safe for Lambda cold starts)
import logging as _logging

_logger = _logging.getLogger(__name__)
try:
    from backend.app.core.database import Base, engine, SessionLocal
    from backend.app.models import ModelConfig, Rule, RuleVersion, ModerationLog, TestSuite, TestRecord, LabelDefinition  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _logger.info("Database tables ensured")

    # Add new columns to existing tables (create_all doesn't alter existing tables)
    from sqlalchemy import text as sa_text
    _conn = engine.connect()
    try:
        # routing_type on model_config
        _conn.execute(sa_text("ALTER TABLE model_config ADD COLUMN IF NOT EXISTS routing_type VARCHAR(20) DEFAULT 'any' NOT NULL"))
        # text_label, image_label, language on moderation_logs
        _conn.execute(sa_text("ALTER TABLE moderation_logs ADD COLUMN IF NOT EXISTS text_label VARCHAR(50)"))
        _conn.execute(sa_text("ALTER TABLE moderation_logs ADD COLUMN IF NOT EXISTS image_label VARCHAR(50)"))
        _conn.execute(sa_text("ALTER TABLE moderation_logs ADD COLUMN IF NOT EXISTS language VARCHAR(10)"))
        _conn.commit()
        _logger.info("Schema migrations applied")
    except Exception as _mig_exc:
        _logger.warning("Schema migration skipped: %s", _mig_exc)
    finally:
        _conn.close()

    # Seed default model configs if table is empty
    _db = SessionLocal()
    try:
        if _db.query(ModelConfig).count() == 0:
            _db.add_all([
                ModelConfig(
                    model_id="anthropic.claude-3-sonnet-20240229-v1:0",
                    model_name="Claude 3 Sonnet",
                    temperature=0.0,
                    max_tokens=4096,
                    is_primary=True,
                    is_fallback=False,
                    fallback_result="review",
                    cost_per_1k_input=0.003,
                    cost_per_1k_output=0.015,
                ),
                ModelConfig(
                    model_id="anthropic.claude-3-haiku-20240307-v1:0",
                    model_name="Claude 3 Haiku",
                    temperature=0.0,
                    max_tokens=4096,
                    is_primary=False,
                    is_fallback=True,
                    fallback_result="review",
                    cost_per_1k_input=0.00025,
                    cost_per_1k_output=0.00125,
                ),
                ModelConfig(
                    model_id="amazon.nova-lite-v1:0",
                    model_name="Amazon Nova Lite",
                    temperature=0.0,
                    max_tokens=4096,
                    is_primary=False,
                    is_fallback=False,
                    cost_per_1k_input=0.00006,
                    cost_per_1k_output=0.00024,
                ),
            ])
            _db.commit()
            _logger.info("Seeded default model configs")

        # Add new models if they don't exist yet
        _existing_model_ids = {c.model_id for c in _db.query(ModelConfig).all()}
        _new_models = []
        if "qwen.qwen3-32b-v1:0" not in _existing_model_ids:
            _new_models.append(ModelConfig(
                model_id="qwen.qwen3-32b-v1:0",
                model_name="Qwen3 32B",
                temperature=0.0,
                max_tokens=4096,
                is_primary=False,
                is_fallback=False,
                routing_type="text_only",
                cost_per_1k_input=0.00035,
                cost_per_1k_output=0.0015,
            ))
        if "amazon.nova-2-lite-v1:0" not in _existing_model_ids:
            _new_models.append(ModelConfig(
                model_id="amazon.nova-2-lite-v1:0",
                model_name="Nova 2 Lite",
                temperature=0.0,
                max_tokens=4096,
                is_primary=False,
                is_fallback=False,
                routing_type="text_only",
                cost_per_1k_input=0.00004,
                cost_per_1k_output=0.00016,
            ))
        if _new_models:
            _db.add_all(_new_models)
            _db.commit()
            _logger.info("Added %d new model configs", len(_new_models))
    finally:
        _db.close()

    # Seed default label definitions if table is empty
    _db2 = SessionLocal()
    try:
        if _db2.query(LabelDefinition).count() == 0:
            _default_labels = [
                # Text labels (9)
                LabelDefinition(label_key="safe", label_type="text", display_name="正常/安全内容", description="正常安全的评论内容", action="pass", enabled=True, sort_order=0),
                LabelDefinition(label_key="spam", label_type="text", display_name="垃圾广告", description="垃圾广告/引流/推广内容", action="reject", enabled=True, sort_order=1),
                LabelDefinition(label_key="toxic", label_type="text", display_name="辱骂/人身攻击", description="辱骂/人身攻击/脏话", action="reject", enabled=True, sort_order=2),
                LabelDefinition(label_key="hate_speech", label_type="text", display_name="仇恨/歧视", description="仇恨/歧视/种族主义", action="reject", enabled=True, sort_order=3),
                LabelDefinition(label_key="privacy_leak", label_type="text", display_name="隐私泄露", description="泄露个人隐私信息", action="reject", enabled=True, sort_order=4),
                LabelDefinition(label_key="political", label_type="text", display_name="政治敏感", description="政治敏感内容", action="reject", enabled=True, sort_order=5),
                LabelDefinition(label_key="self_harm", label_type="text", display_name="自残/自杀暗示", description="自残/自杀暗示内容", action="reject_warn", enabled=True, sort_order=6),
                LabelDefinition(label_key="illegal_trade", label_type="text", display_name="违法交易", description="违法交易暗示", action="reject", enabled=True, sort_order=7),
                LabelDefinition(label_key="misleading", label_type="text", display_name="虚假宣传", description="虚假宣传/误导性信息", action="reject", enabled=True, sort_order=8),
                # Image labels (10)
                LabelDefinition(label_key="none", label_type="image", display_name="无", description="无图片或安全图片", action="pass", enabled=True, sort_order=0),
                LabelDefinition(label_key="pornography", label_type="image", display_name="涉黄内容", description="涉黄/色情内容", action="reject", enabled=True, sort_order=1),
                LabelDefinition(label_key="gambling", label_type="image", display_name="涉赌内容", description="涉赌内容", action="reject", enabled=True, sort_order=2),
                LabelDefinition(label_key="drugs", label_type="image", display_name="涉毒内容", description="涉毒内容", action="reject", enabled=True, sort_order=3),
                LabelDefinition(label_key="violence", label_type="image", display_name="暴力/血腥", description="暴力/血腥内容", action="reject", enabled=True, sort_order=4),
                LabelDefinition(label_key="terrorism", label_type="image", display_name="恐怖主义", description="恐怖主义符号", action="reject", enabled=True, sort_order=5),
                LabelDefinition(label_key="qr_code_spam", label_type="image", display_name="二维码引流", description="二维码引流", action="reject", enabled=True, sort_order=6),
                LabelDefinition(label_key="contact_info", label_type="image", display_name="联系方式水印", description="图片水印联系方式", action="reject", enabled=True, sort_order=7),
                LabelDefinition(label_key="ad_overlay", label_type="image", display_name="广告覆盖图", description="广告覆盖图", action="reject", enabled=True, sort_order=8),
                LabelDefinition(label_key="minor_exploitation", label_type="image", display_name="未成年人保护", description="未成年人保护相关", action="reject_report", enabled=True, sort_order=9),
            ]
            _db2.add_all(_default_labels)
            _db2.commit()
            _logger.info("Seeded default label definitions")
    finally:
        _db2.close()
except Exception as _exc:
    _logger.warning("Could not auto-create tables: %s", _exc)

# CORS — allow CloudFront frontend to call API Gateway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert Pydantic validation errors (422) to 400 Bad Request.

    This covers the case where text and image_url are both empty,
    which the ModerationRequest model_validator raises as a ValueError.
    """
    errors = []
    for err in exc.errors():
        clean = {k: v for k, v in err.items() if k != "ctx"}
        # Convert loc tuple to list for JSON serialization
        if "loc" in clean:
            clean["loc"] = list(clean["loc"])
        errors.append(clean)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": errors},
    )


# Register routers
app.include_router(moderation_router)
app.include_router(admin_rules_router)
app.include_router(admin_prompt_router)
app.include_router(admin_logs_router)
app.include_router(admin_test_router)
app.include_router(admin_model_config_router)
app.include_router(admin_stats_router)
app.include_router(admin_labels_router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


# AWS Lambda handler
handler = Mangum(app, lifespan="off")
