"""Pydantic schemas for prompt preview and test endpoints.

Validates: Requirements 4.1, 4.2
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from backend.app.schemas.moderation import ModerationResponse


class PromptPreviewRequest(BaseModel):
    """Request body for POST /api/admin/prompt/preview."""

    rule_ids: list[uuid.UUID] = Field(description="要组合的规则 ID 列表")
    text: str | None = Field(default=None, description="测试文本内容")
    image_url: str | None = Field(default=None, description="测试图片 URL")


class PromptPreviewResponse(BaseModel):
    """Response body for POST /api/admin/prompt/preview."""

    prompt: str = Field(description="组装后的最终提示词")


class PromptTestRequest(BaseModel):
    """Request body for POST /api/admin/prompt/test."""

    rule_ids: list[uuid.UUID] = Field(description="要组合的规则 ID 列表")
    text: str | None = Field(default=None, description="测试文本内容")
    image_url: str | None = Field(default=None, description="测试图片 URL")
