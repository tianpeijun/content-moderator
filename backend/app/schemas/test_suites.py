"""Pydantic schemas for test suite operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TestSuiteUploadResponse(BaseModel):
    """Response after uploading a test suite."""

    id: uuid.UUID = Field(description="测试集ID")
    name: str = Field(description="测试集名称")
    total_cases: int = Field(ge=0, description="用例总数")
    created_at: datetime = Field(description="创建时间")

    model_config = {"from_attributes": True}


class TestSuiteProgressResponse(BaseModel):
    """Response for test suite execution progress."""

    test_record_id: uuid.UUID = Field(description="测试记录ID")
    status: str = Field(description="状态: pending/running/completed/failed")
    progress_current: int = Field(ge=0, description="当前完成数")
    progress_total: int = Field(ge=0, description="总数")


class TestReportResponse(BaseModel):
    """Response for a completed test report."""

    test_record_id: uuid.UUID = Field(description="测试记录ID")
    test_suite_id: uuid.UUID = Field(description="测试集ID")
    status: str = Field(description="状态")
    accuracy: float | None = Field(default=None, description="准确率")
    recall: float | None = Field(default=None, description="召回率")
    f1_score: float | None = Field(default=None, description="F1 分数")
    confusion_matrix: dict[str, int] | None = Field(
        default=None, description="混淆矩阵 {TP, FP, TN, FN}"
    )
    error_cases: list[dict[str, Any]] | None = Field(
        default=None, description="错误案例列表"
    )
    rule_hit_distribution: dict[str, int] | None = Field(
        default=None, description="规则命中分布"
    )
    started_at: datetime | None = Field(default=None, description="开始时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
