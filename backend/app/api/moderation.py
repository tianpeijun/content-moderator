"""Moderation API router — POST /api/v1/moderate & GET /api/v1/moderate/{task_id}."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_api_key
from backend.app.core.database import get_db
from backend.app.models.model_config import ModelConfig
from backend.app.models.moderation_logs import ModerationLog
from backend.app.schemas.moderation import (
    MatchedRule,
    ModerationRequest,
    ModerationResponse,
)
from backend.app.services.image_fetcher import ImageFetcher
from backend.app.services.model_invoker import ModelInvoker, ModelSettings
from backend.app.services.rule_engine import ModerationContent, RuleEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Shared service instances
_rule_engine = RuleEngine()
_image_fetcher = ImageFetcher()
_model_invoker = ModelInvoker()


def _build_model_settings(db: Session) -> ModelSettings:
    """Load primary and fallback model config from DB and return a ModelSettings."""
    primary = db.execute(
        select(ModelConfig).where(ModelConfig.is_primary.is_(True))
    ).scalar_one_or_none()

    if primary is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No primary model configured",
        )

    fallback = db.execute(
        select(ModelConfig).where(ModelConfig.is_fallback.is_(True))
    ).scalar_one_or_none()

    return ModelSettings(
        model_id=primary.model_id,
        temperature=primary.temperature,
        max_tokens=primary.max_tokens,
        fallback_model_id=fallback.model_id if fallback else None,
        fallback_temperature=fallback.temperature if fallback else 0.0,
        fallback_max_tokens=fallback.max_tokens if fallback else 1024,
        fallback_result=primary.fallback_result or "review",
    )


@router.post(
    "/moderate",
    response_model=ModerationResponse,
    status_code=status.HTTP_200_OK,
    summary="提交内容审核",
)
async def moderate_content(
    request: ModerationRequest,
    db: Session = Depends(get_db),
) -> ModerationResponse:
    """Submit content for moderation.

    Orchestrates: RuleEngine → ImageFetcher → ModelInvoker, persists the
    result to *moderation_logs*, and returns the moderation response.

    Validates: Requirements 1.1, 1.2, 1.3, 1.5, 5.4
    """
    start_ts = time.monotonic()
    task_id = str(uuid.uuid4())

    try:
        # 1. Load active rules
        rules = _rule_engine.get_active_rules(db, request.business_type)

        # 2. Load enabled labels for dynamic prompt injection
        labels = _rule_engine.get_enabled_labels(db)

        # 3. Assemble prompt with dynamic labels
        content = ModerationContent(text=request.text, image_url=request.image_url)
        prompt = _rule_engine.assemble_prompt(rules, content, labels=labels)

        # 4. Fetch image bytes if image_url provided
        images: list[bytes] | None = None
        if request.image_url and request.image_url.strip():
            image_bytes = await _image_fetcher.fetch(request.image_url.strip())
            images = [image_bytes]

        # 5. Build model settings from DB config
        settings = _build_model_settings(db)

        # 6. Invoke model with fallback
        model_resp = await _model_invoker.invoke_with_fallback(prompt, images, settings)

        elapsed_ms = int((time.monotonic() - start_ts) * 1000)

        # 7. Build matched rules list
        matched = []
        for r in model_resp.matched_rules:
            if isinstance(r, dict):
                matched.append(MatchedRule(
                    rule_id=str(r.get("rule_id", "")),
                    rule_name=str(r.get("rule_name", "")),
                    action=str(r.get("action", "")),
                ))
            # Skip non-dict entries (model sometimes returns strings)

        # 8. Persist moderation log
        log = ModerationLog(
            task_id=task_id,
            status="completed",
            input_text=request.text,
            input_image_url=request.image_url,
            business_type=request.business_type,
            final_prompt=prompt,
            model_response=model_resp.raw_response,
            result=model_resp.result,
            text_label=model_resp.text_label,
            image_label=model_resp.image_label,
            confidence=model_resp.confidence,
            matched_rules=[m.model_dump() for m in matched],
            processing_time_ms=elapsed_ms,
            degraded=model_resp.degraded,
            model_id=model_resp.model_id,
            language=model_resp.language if model_resp.language else None,
        )
        db.add(log)
        db.commit()

        return ModerationResponse(
            task_id=task_id,
            status="completed",
            result=model_resp.result,
            text_label=model_resp.text_label,
            image_label=model_resp.image_label,
            confidence=model_resp.confidence,
            matched_rules=matched,
            degraded=model_resp.degraded,
            processing_time_ms=elapsed_ms,
            language=model_resp.language if model_resp.language else None,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Moderation failed for task %s", task_id)
        # Persist a failed log entry
        elapsed_ms = int((time.monotonic() - start_ts) * 1000)
        try:
            fail_log = ModerationLog(
                task_id=task_id,
                status="failed",
                input_text=request.text,
                input_image_url=request.image_url,
                business_type=request.business_type,
                processing_time_ms=elapsed_ms,
                degraded=False,
            )
            db.add(fail_log)
            db.commit()
        except Exception:
            logger.exception("Failed to persist error log for task %s", task_id)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal moderation error",
        )


@router.get(
    "/moderate/{task_id}",
    response_model=ModerationResponse,
    status_code=status.HTTP_200_OK,
    summary="查询审核结果",
)
async def get_moderation_result(
    task_id: str,
    db: Session = Depends(get_db),
) -> ModerationResponse:
    """Query the status and result of a moderation task.

    Validates: Requirements 2.1, 2.2, 2.3
    """
    log = db.execute(
        select(ModerationLog).where(ModerationLog.task_id == task_id)
    ).scalar_one_or_none()

    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moderation task '{task_id}' not found",
        )

    # Build matched_rules from stored JSONB
    matched: list[MatchedRule] = []
    if log.matched_rules:
        matched = [
            MatchedRule(
                rule_id=str(r.get("rule_id", "")),
                rule_name=str(r.get("rule_name", "")),
                action=str(r.get("action", "")),
            )
            for r in log.matched_rules
        ]

    return ModerationResponse(
        task_id=log.task_id,
        status=log.status,
        result=log.result if log.status == "completed" else None,
        text_label=log.text_label if log.status == "completed" else None,
        image_label=log.image_label if log.status == "completed" else None,
        confidence=log.confidence if log.status == "completed" else None,
        matched_rules=matched if log.status == "completed" else [],
        degraded=log.degraded,
        processing_time_ms=log.processing_time_ms if log.status == "completed" else None,
        language=log.language if log.status == "completed" else None,
    )
