"""Admin Labels CRUD API router.

Provides endpoints for managing label definitions:
- GET /api/admin/labels
- POST /api/admin/labels
- PUT /api/admin/labels/{label_id}
- DELETE /api/admin/labels/{label_id}

Validates: Requirements 14.1, 14.2
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.models.label_definitions import LabelDefinition
from backend.app.schemas.labels import (
    LabelDefinitionCreate,
    LabelDefinitionList,
    LabelDefinitionResponse,
    LabelDefinitionUpdate,
)

router = APIRouter(
    prefix="/api/admin",
    dependencies=[Depends(verify_cognito_token)],
)


@router.get("/labels", response_model=LabelDefinitionList, summary="获取标签列表")
async def list_labels(
    label_type: str | None = Query(default=None, description="按标签类型筛选: text / image"),
    enabled: bool | None = Query(default=None, description="按启用状态筛选"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LabelDefinitionList:
    """List label definitions with optional filtering."""
    stmt = select(LabelDefinition)
    count_stmt = select(sa_func.count()).select_from(LabelDefinition)

    if label_type is not None:
        stmt = stmt.where(LabelDefinition.label_type == label_type)
        count_stmt = count_stmt.where(LabelDefinition.label_type == label_type)
    if enabled is not None:
        stmt = stmt.where(LabelDefinition.enabled == enabled)
        count_stmt = count_stmt.where(LabelDefinition.enabled == enabled)

    stmt = stmt.order_by(LabelDefinition.label_type.asc(), LabelDefinition.sort_order.asc())

    labels = db.execute(stmt).scalars().all()
    total = db.execute(count_stmt).scalar_one()

    return LabelDefinitionList(
        items=[LabelDefinitionResponse.model_validate(lb) for lb in labels],
        total=total,
    )


@router.post(
    "/labels",
    response_model=LabelDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建标签",
)
async def create_label(
    body: LabelDefinitionCreate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LabelDefinitionResponse:
    """Create a new label definition. Validates (label_key, label_type) uniqueness."""
    # Check uniqueness
    existing = db.execute(
        select(LabelDefinition).where(
            LabelDefinition.label_key == body.label_key,
            LabelDefinition.label_type == body.label_type,
        )
    ).scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Label with key '{body.label_key}' and type '{body.label_type}' already exists",
        )

    label = LabelDefinition(
        label_key=body.label_key,
        label_type=body.label_type,
        display_name=body.display_name,
        description=body.description,
        action=body.action,
        enabled=body.enabled,
        sort_order=body.sort_order,
    )
    db.add(label)
    db.commit()
    db.refresh(label)
    return LabelDefinitionResponse.model_validate(label)


@router.put(
    "/labels/{label_id}",
    response_model=LabelDefinitionResponse,
    summary="更新标签",
)
async def update_label(
    label_id: uuid.UUID,
    body: LabelDefinitionUpdate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LabelDefinitionResponse:
    """Update an existing label definition."""
    label = db.execute(
        select(LabelDefinition).where(LabelDefinition.id == label_id)
    ).scalar_one_or_none()

    if label is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Label '{label_id}' not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # If label_key or label_type is being changed, check uniqueness
    new_key = update_data.get("label_key", label.label_key)
    new_type = update_data.get("label_type", label.label_type)
    if new_key != label.label_key or new_type != label.label_type:
        existing = db.execute(
            select(LabelDefinition).where(
                LabelDefinition.label_key == new_key,
                LabelDefinition.label_type == new_type,
                LabelDefinition.id != label_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Label with key '{new_key}' and type '{new_type}' already exists",
            )

    for field, value in update_data.items():
        setattr(label, field, value)

    db.commit()
    db.refresh(label)
    return LabelDefinitionResponse.model_validate(label)


@router.delete(
    "/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除标签",
    response_model=None,
)
async def delete_label(
    label_id: uuid.UUID,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
):
    """Delete a label definition by ID."""
    label = db.execute(
        select(LabelDefinition).where(LabelDefinition.id == label_id)
    ).scalar_one_or_none()

    if label is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Label '{label_id}' not found",
        )

    db.delete(label)
    db.commit()
