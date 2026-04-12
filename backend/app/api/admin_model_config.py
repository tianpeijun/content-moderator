"""Admin Model Config API router.

Provides endpoints for managing AI model configurations:
- GET /api/admin/model-config — list all model configs
- PUT /api/admin/model-config/{config_id} — update a model config

Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.models.model_config import ModelConfig
from backend.app.schemas.model_config import ModelConfigResponse, ModelConfigUpdate

router = APIRouter(
    prefix="/api/admin",
    dependencies=[Depends(verify_cognito_token)],
)


@router.get(
    "/model-config",
    response_model=list[ModelConfigResponse],
    summary="获取所有模型配置",
)
async def list_model_configs(
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> list[ModelConfigResponse]:
    """Return all model configurations."""
    stmt = select(ModelConfig).order_by(ModelConfig.updated_at.desc())
    configs = db.execute(stmt).scalars().all()
    return [ModelConfigResponse.model_validate(c) for c in configs]


@router.put(
    "/model-config/{config_id}",
    response_model=ModelConfigResponse,
    summary="更新模型配置",
)
async def update_model_config(
    config_id: uuid.UUID,
    body: ModelConfigUpdate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> ModelConfigResponse:
    """Update an existing model configuration."""
    config = db.execute(
        select(ModelConfig).where(ModelConfig.id == config_id)
    ).scalar_one_or_none()

    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model config '{config_id}' not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    db.commit()
    db.refresh(config)
    return ModelConfigResponse.model_validate(config)
