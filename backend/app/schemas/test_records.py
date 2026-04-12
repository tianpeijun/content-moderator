"""Pydantic schemas for test record operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TestRecordResponse(BaseModel):
    """Response for a test record."""

    model_config = {"from_attributes": True, "protected_namespaces": ()}

    id: uuid.UUID = Field(description="测试记录ID")
    test_suite_id: uuid.UUID = Field(description="关联测试集ID")
    rule_ids: list[str] | None = Field(default=None, description="使用的规则ID列表")
    model_config_snapshot: dict[str, Any] | None = Field(
        default=None, description="模型配置快照"
    )
    status: str = Field(description="状态: pending/running/completed/failed")
    progress_current: int = Field(ge=0, description="当前完成数")
    progress_total: int = Field(ge=0, description="总数")
    report: dict[str, Any] | None = Field(default=None, description="测试报告")
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")


class TestRecordCompareRequest(BaseModel):
    """Request to compare two test records."""

    record_id_a: uuid.UUID = Field(description="测试记录A的ID")
    record_id_b: uuid.UUID = Field(description="测试记录B的ID")
