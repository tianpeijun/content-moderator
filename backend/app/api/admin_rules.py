"""Admin Rules CRUD API router.

Provides endpoints for managing moderation rules:
- GET/POST /api/admin/rules
- PUT/DELETE /api/admin/rules/{rule_id}
- GET /api/admin/rules/{rule_id}/versions

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.models.rule_versions import RuleVersion
from backend.app.models.rules import Rule
from backend.app.schemas.rules import (
    RuleCreate,
    RuleResponse,
    RuleUpdate,
    RuleVersionResponse,
)

router = APIRouter(
    prefix="/api/admin",
    dependencies=[Depends(verify_cognito_token)],
)


def _rule_snapshot(rule: Rule) -> dict[str, Any]:
    """Create a JSON-serializable snapshot of a rule's current state."""
    return {
        "id": str(rule.id),
        "name": rule.name,
        "type": rule.type,
        "business_type": rule.business_type,
        "prompt_template": rule.prompt_template,
        "variables": rule.variables,
        "action": rule.action,
        "priority": rule.priority,
        "enabled": rule.enabled,
    }


@router.get("/rules", response_model=list[RuleResponse], summary="获取规则列表")
async def list_rules(
    type: str | None = Query(default=None, description="按类型筛选"),
    business_type: str | None = Query(default=None, description="按业务类型筛选"),
    enabled: bool | None = Query(default=None, description="按启用状态筛选"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> list[RuleResponse]:
    """List all rules with optional filtering."""
    stmt = select(Rule)
    if type is not None:
        stmt = stmt.where(Rule.type == type)
    if business_type is not None:
        stmt = stmt.where(Rule.business_type == business_type)
    if enabled is not None:
        stmt = stmt.where(Rule.enabled == enabled)
    stmt = stmt.order_by(Rule.priority.asc())

    rules = db.execute(stmt).scalars().all()
    return [RuleResponse.model_validate(r) for r in rules]


@router.post(
    "/rules",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建规则",
)
async def create_rule(
    body: RuleCreate,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> RuleResponse:
    """Create a new moderation rule."""
    rule = Rule(
        name=body.name,
        type=body.type,
        business_type=body.business_type,
        prompt_template=body.prompt_template,
        variables=body.variables,
        action=body.action,
        priority=body.priority,
        enabled=body.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return RuleResponse.model_validate(rule)


@router.put(
    "/rules/{rule_id}",
    response_model=RuleResponse,
    summary="更新规则",
)
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    db: Session = Depends(get_db),
    claims: dict = Depends(verify_cognito_token),
) -> RuleResponse:
    """Update an existing rule. Saves a version snapshot before applying changes."""
    rule = db.execute(
        select(Rule).where(Rule.id == rule_id)
    ).scalar_one_or_none()

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found",
        )

    # Determine next version number
    max_version_row = db.execute(
        select(RuleVersion.version)
        .where(RuleVersion.rule_id == rule_id)
        .order_by(RuleVersion.version.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_version = (max_version_row or 0) + 1

    # Snapshot current state before update
    snapshot = _rule_snapshot(rule)
    modified_by = claims.get("sub") or claims.get("username")

    # Build change summary from provided fields
    update_data = body.model_dump(exclude_unset=True)
    changed_fields = list(update_data.keys())
    change_summary = f"Updated fields: {', '.join(changed_fields)}" if changed_fields else None

    version = RuleVersion(
        rule_id=rule_id,
        version=next_version,
        snapshot=snapshot,
        modified_by=modified_by,
        change_summary=change_summary,
    )
    db.add(version)

    # Apply updates
    for field, value in update_data.items():
        setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    return RuleResponse.model_validate(rule)


@router.delete(
    "/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除规则",
    response_model=None,
)
async def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
):
    """Delete a rule by ID."""
    rule = db.execute(
        select(Rule).where(Rule.id == rule_id)
    ).scalar_one_or_none()

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found",
        )

    db.delete(rule)
    db.commit()


@router.get(
    "/rules/{rule_id}/versions",
    response_model=list[RuleVersionResponse],
    summary="查询规则版本历史",
)
async def list_rule_versions(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> list[RuleVersionResponse]:
    """List version history for a specific rule."""
    # Verify rule exists
    rule = db.execute(
        select(Rule).where(Rule.id == rule_id)
    ).scalar_one_or_none()

    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule '{rule_id}' not found",
        )

    versions = db.execute(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule_id)
        .order_by(RuleVersion.version.desc())
    ).scalars().all()

    return [RuleVersionResponse.model_validate(v) for v in versions]
