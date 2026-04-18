"""Pydantic schemas for model configuration."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ModelConfigResponse(BaseModel):
    """Response for model configuration."""

    id: uuid.UUID = Field(description="配置ID")
    model_id: str = Field(description="Bedrock 模型 ID")
    model_name: str = Field(description="显示名称")
    temperature: float = Field(description="温度参数")
    max_tokens: int = Field(description="最大输出长度")
    is_primary: bool = Field(description="是否为主模型")
    is_fallback: bool = Field(description="是否为备用模型")
    routing_type: str = Field(default="any", description="路由类型: text_only(纯文本专用) / multimodal(图文混合专用) / any(通用)")
    fallback_result: str | None = Field(default=None, description="降级默认结果")
    cost_per_1k_input: float = Field(description="每千 token 输入成本")
    cost_per_1k_output: float = Field(description="每千 token 输出成本")
    updated_at: datetime = Field(description="更新时间")

    model_config = {"from_attributes": True, "protected_namespaces": ()}


class ModelConfigUpdate(BaseModel):
    """Schema for updating model configuration. All fields optional."""

    model_config = {"protected_namespaces": ()}

    model_id: str | None = Field(default=None, description="Bedrock 模型 ID")
    model_name: str | None = Field(default=None, description="显示名称")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int | None = Field(default=None, ge=1, description="最大输出长度")
    is_primary: bool | None = Field(default=None, description="是否为主模型")
    is_fallback: bool | None = Field(default=None, description="是否为备用模型")
    routing_type: str | None = Field(default=None, description="路由类型: text_only / multimodal / any")
    fallback_result: str | None = Field(default=None, description="降级默认结果")
    cost_per_1k_input: float | None = Field(default=None, ge=0.0, description="每千 token 输入成本")
    cost_per_1k_output: float | None = Field(default=None, ge=0.0, description="每千 token 输出成本")
