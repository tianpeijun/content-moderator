"""Admin Prompt Preview & Test API router.

Provides endpoints for previewing assembled prompts and testing them
against an AI model:
- POST /api/admin/prompt/preview
- POST /api/admin/prompt/test

Validates: Requirements 4.1, 4.2
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.models.model_config import ModelConfig
from backend.app.models.rules import Rule
from backend.app.schemas.admin_prompt import (
    PromptPreviewRequest,
    PromptPreviewResponse,
    PromptTestRequest,
)
from backend.app.schemas.moderation import MatchedRule, ModerationResponse
from backend.app.services.image_fetcher import ImageFetcher
from backend.app.services.model_invoker import ModelInvoker, ModelSettings
from backend.app.services.rule_engine import ModerationContent, RuleEngine

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/prompt",
    dependencies=[Depends(verify_cognito_token)],
)

# Shared service instances
_rule_engine = RuleEngine()
_image_fetcher = ImageFetcher()
_model_invoker = ModelInvoker()


def _load_rules_by_ids(db: Session, rule_ids: list[uuid.UUID]) -> list[Rule]:
    """Load rules by IDs and return them sorted by priority ascending."""
    if not rule_ids:
        return []
    stmt = (
        select(Rule)
        .where(Rule.id.in_(rule_ids))
        .order_by(Rule.priority.asc())
    )
    return list(db.execute(stmt).scalars().all())


def _build_model_settings(db: Session) -> ModelSettings:
    """Load primary and fallback model config from DB."""
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
    "/preview",
    response_model=PromptPreviewResponse,
    summary="提示词预览",
)
async def prompt_preview(
    body: PromptPreviewRequest,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> PromptPreviewResponse:
    """Assemble and return the final prompt from selected rules.

    Validates: Requirement 4.1
    """
    rules = _load_rules_by_ids(db, body.rule_ids)
    content = ModerationContent(text=body.text, image_url=body.image_url)
    prompt = _rule_engine.assemble_prompt(rules, content)
    return PromptPreviewResponse(prompt=prompt)


@router.post(
    "/test",
    response_model=ModerationResponse,
    summary="提示词测试",
)
async def prompt_test(
    body: PromptTestRequest,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> ModerationResponse:
    """Assemble prompt, invoke AI model, and return moderation result.

    Validates: Requirement 4.2
    """
    start_ts = time.monotonic()
    task_id = str(uuid.uuid4())

    try:
        # 1. Load rules
        rules = _load_rules_by_ids(db, body.rule_ids)

        # 2. Assemble prompt
        content = ModerationContent(text=body.text, image_url=body.image_url)
        prompt = _rule_engine.assemble_prompt(rules, content)

        # 3. Fetch image if provided
        images: list[bytes] | None = None
        if body.image_url and body.image_url.strip():
            image_bytes = await _image_fetcher.fetch(body.image_url.strip())
            images = [image_bytes]

        # 4. Build model settings
        settings = _build_model_settings(db)

        # 5. Invoke model
        model_resp = await _model_invoker.invoke_with_fallback(
            prompt, images, settings
        )

        elapsed_ms = int((time.monotonic() - start_ts) * 1000)

        matched = [
            MatchedRule(
                rule_id=str(r.get("rule_id", "")),
                rule_name=str(r.get("rule_name", "")),
                action=str(r.get("action", "")),
            )
            for r in model_resp.matched_rules
        ]

        return ModerationResponse(
            task_id=task_id,
            status="completed",
            result=model_resp.result,
            confidence=model_resp.confidence,
            matched_rules=matched,
            degraded=model_resp.degraded,
            processing_time_ms=elapsed_ms,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Prompt test failed for task %s", task_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Prompt test failed",
        )
