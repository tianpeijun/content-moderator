"""Pydantic schemas for label definitions CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LabelDefinitionCreate(BaseModel):
    """Schema for creating a new label definition."""

    label_key: str = Field(..., max_length=50, description="标签唯一标识")
    label_type: str = Field(..., max_length=10, description="标签类型: text / image")
    display_name: str = Field(..., max_length=100, description="显示名称")
    description: str | None = Field(default=None, description="标签详细描述")
    action: str = Field(..., max_length=20, description="处置动作: pass / reject / reject_warn / reject_report")
    enabled: bool = Field(default=True, description="启用状态")
    sort_order: int = Field(default=0, description="排序序号")


class LabelDefinitionUpdate(BaseModel):
    """Schema for updating a label definition. All fields optional."""

    label_key: str | None = Field(default=None, max_length=50)
    label_type: str | None = Field(default=None, max_length=10)
    display_name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    action: str | None = Field(default=None, max_length=20)
    enabled: bool | None = None
    sort_order: int | None = None


class LabelDefinitionResponse(BaseModel):
    """Schema for label definition response."""

    id: uuid.UUID
    label_key: str
    label_type: str
    display_name: str
    description: str | None = None
    action: str
    enabled: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LabelDefinitionList(BaseModel):
    """Paginated list of label definitions."""

    items: list[LabelDefinitionResponse]
    total: int
