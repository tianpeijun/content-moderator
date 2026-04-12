"""Admin Audit Logs API router.

Provides endpoints for querying and exporting moderation audit logs:
- GET  /api/admin/logs          — paginated list with filters
- GET  /api/admin/logs/{log_id} — full log detail
- POST /api/admin/logs/export   — export filtered logs as JSON

Validates: Requirements 5.1, 5.2, 5.3
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.models.moderation_logs import ModerationLog
from backend.app.schemas.admin_logs import (
    LogDetail,
    LogExportResponse,
    LogListItem,
    LogListResponse,
)

router = APIRouter(
    prefix="/api/admin",
    dependencies=[Depends(verify_cognito_token)],
)


def _apply_filters(
    stmt,
    start_date: datetime | None,
    end_date: datetime | None,
    result: str | None,
    business_type: str | None,
    text_label: str | None = None,
    image_label: str | None = None,
):
    """Apply common query filters to a SELECT statement."""
    if start_date is not None:
        stmt = stmt.where(ModerationLog.created_at >= start_date)
    if end_date is not None:
        stmt = stmt.where(ModerationLog.created_at <= end_date)
    if result is not None:
        stmt = stmt.where(ModerationLog.result == result)
    if business_type is not None:
        stmt = stmt.where(ModerationLog.business_type == business_type)
    if text_label is not None:
        stmt = stmt.where(ModerationLog.text_label == text_label)
    if image_label is not None:
        stmt = stmt.where(ModerationLog.image_label == image_label)
    return stmt


@router.get("/logs", response_model=LogListResponse, summary="审核日志列表")
async def list_logs(
    start_date: datetime | None = Query(default=None, description="开始时间 (ISO datetime)"),
    end_date: datetime | None = Query(default=None, description="结束时间 (ISO datetime)"),
    result: str | None = Query(default=None, description="审核结果 (pass/reject/review/flag)"),
    business_type: str | None = Query(default=None, description="业务类型"),
    text_label: str | None = Query(default=None, description="文案标签"),
    image_label: str | None = Query(default=None, description="图片标签"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LogListResponse:
    """Return a paginated list of moderation log summaries, sorted by created_at DESC."""
    # Count query
    count_stmt = select(func.count(ModerationLog.id))
    count_stmt = _apply_filters(count_stmt, start_date, end_date, result, business_type, text_label, image_label)
    total = db.execute(count_stmt).scalar_one()

    # Data query
    data_stmt = select(ModerationLog)
    data_stmt = _apply_filters(data_stmt, start_date, end_date, result, business_type, text_label, image_label)
    data_stmt = data_stmt.order_by(ModerationLog.created_at.desc())
    data_stmt = data_stmt.offset((page - 1) * page_size).limit(page_size)

    logs = db.execute(data_stmt).scalars().all()

    return LogListResponse(
        items=[LogListItem.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/logs/{log_id}", response_model=LogDetail, summary="审核日志详情")
async def get_log_detail(
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LogDetail:
    """Return full details for a single moderation log entry."""
    log = db.execute(
        select(ModerationLog).where(ModerationLog.id == log_id)
    ).scalar_one_or_none()

    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Log '{log_id}' not found",
        )

    return LogDetail.model_validate(log)


@router.post("/logs/export", response_model=LogExportResponse, summary="导出审核日志")
async def export_logs(
    start_date: datetime | None = Query(default=None, description="开始时间 (ISO datetime)"),
    end_date: datetime | None = Query(default=None, description="结束时间 (ISO datetime)"),
    result: str | None = Query(default=None, description="审核结果 (pass/reject/review/flag)"),
    business_type: str | None = Query(default=None, description="业务类型"),
    text_label: str | None = Query(default=None, description="文案标签"),
    image_label: str | None = Query(default=None, description="图片标签"),
    db: Session = Depends(get_db),
    _claims: dict = Depends(verify_cognito_token),
) -> LogExportResponse:
    """Export filtered logs as JSON (simplified export — real file export would use S3)."""
    data_stmt = select(ModerationLog)
    data_stmt = _apply_filters(data_stmt, start_date, end_date, result, business_type, text_label, image_label)
    data_stmt = data_stmt.order_by(ModerationLog.created_at.desc())

    logs = db.execute(data_stmt).scalars().all()

    return LogExportResponse(
        items=[LogDetail.model_validate(log) for log in logs],
        total=len(logs),
    )
