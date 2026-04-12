"""Pydantic schemas for rule CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RuleCreate(BaseModel):
    """Schema for creating a new rule."""

    name: str = Field(min_length=1, max_length=200, description="规则名称")
    type: Literal["text", "image", "both"] = Field(description="类型: text/image/both")
    business_type: str | None = Field(default=None, max_length=100, description="适用业务类型")
    prompt_template: str = Field(min_length=1, description="提示词模板，支持 {{variable}}")
    variables: dict[str, Any] | None = Field(default=None, description="变量配置")
    action: Literal["reject", "review", "flag"] = Field(description="触发动作: reject/review/flag")
    priority: int = Field(ge=0, description="优先级，数值越小越优先")
    enabled: bool = Field(default=True, description="启用状态")


class RuleUpdate(BaseModel):
    """Schema for updating an existing rule. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=200, description="规则名称")
    type: Literal["text", "image", "both"] | None = Field(default=None, description="类型")
    business_type: str | None = Field(default=None, max_length=100, description="适用业务类型")
    prompt_template: str | None = Field(default=None, min_length=1, description="提示词模板")
    variables: dict[str, Any] | None = Field(default=None, description="变量配置")
    action: Literal["reject", "review", "flag"] | None = Field(default=None, description="触发动作")
    priority: int | None = Field(default=None, ge=0, description="优先级")
    enabled: bool | None = Field(default=None, description="启用状态")


class RuleResponse(BaseModel):
    """Schema for rule response."""

    id: uuid.UUID = Field(description="规则ID")
    name: str = Field(description="规则名称")
    type: str = Field(description="类型: text/image/both")
    business_type: str | None = Field(default=None, description="适用业务类型")
    prompt_template: str = Field(description="提示词模板")
    variables: dict[str, Any] | None = Field(default=None, description="变量配置")
    action: str = Field(description="触发动作: reject/review/flag")
    priority: int = Field(description="优先级")
    enabled: bool = Field(description="启用状态")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")

    model_config = {"from_attributes": True}


class RuleVersionResponse(BaseModel):
    """Schema for rule version history entry."""

    id: uuid.UUID = Field(description="版本ID")
    rule_id: uuid.UUID = Field(description="关联规则ID")
    version: int = Field(description="版本号")
    snapshot: dict[str, Any] = Field(description="规则完整快照")
    modified_by: str | None = Field(default=None, description="修改人")
    modified_at: datetime = Field(description="修改时间")
    change_summary: str | None = Field(default=None, description="修改摘要")

    model_config = {"from_attributes": True}
