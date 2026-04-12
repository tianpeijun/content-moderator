"""Pydantic schemas for admin audit log endpoints.

Validates: Requirements 5.1, 5.2, 5.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LogListItem(BaseModel):
    """Summary item returned in paginated log list."""

    id: uuid.UUID = Field(description="日志ID")
    task_id: str = Field(description="审核任务ID")
    status: str = Field(description="任务状态")
    result: str | None = Field(default=None, description="审核结果")
    text_label: str | None = Field(default=None, description="文案标签")
    image_label: str | None = Field(default=None, description="图片标签")
    business_type: str | None = Field(default=None, description="业务类型")
    created_at: datetime = Field(description="创建时间")
    processing_time_ms: int | None = Field(default=None, description="处理耗时(ms)")

    model_config = {"from_attributes": True}


class LogDetail(BaseModel):
    """Full log detail including input content, prompt, and model response."""

    id: uuid.UUID = Field(description="日志ID")
    task_id: str = Field(description="审核任务ID")
    status: str = Field(description="任务状态")
    input_text: str | None = Field(default=None, description="原始评论文本")
    input_image_url: str | None = Field(default=None, description="原始图片URL")
    business_type: str | None = Field(default=None, description="业务类型")
    final_prompt: str | None = Field(default=None, description="最终组装的提示词")
    model_response: str | None = Field(default=None, description="AI模型原始响应")
    result: str | None = Field(default=None, description="审核结果")
    text_label: str | None = Field(default=None, description="文案标签")
    image_label: str | None = Field(default=None, description="图片标签")
    confidence: float | None = Field(default=None, description="置信度")
    matched_rules: Any | None = Field(default=None, description="命中规则列表")
    processing_time_ms: int | None = Field(default=None, description="处理耗时(ms)")
    degraded: bool = Field(description="是否降级处理")
    model_id: str | None = Field(default=None, description="使用的模型ID")
    created_at: datetime = Field(description="创建时间")

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class LogListResponse(BaseModel):
    """Paginated response for log list."""

    items: list[LogListItem] = Field(description="日志列表")
    total: int = Field(description="总数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")


class LogExportResponse(BaseModel):
    """Response for log export (simplified JSON export)."""

    items: list[LogDetail] = Field(description="导出的日志列表")
    total: int = Field(description="总数")
