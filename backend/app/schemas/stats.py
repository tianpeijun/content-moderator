"""Pydantic schemas for statistics responses."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VolumeDataPoint(BaseModel):
    """Single data point in volume trend."""

    period: str = Field(description="时间段标签，如 2024-01-01")
    total: int = Field(ge=0, description="审核总量")
    pass_count: int = Field(ge=0, description="通过数")
    reject_count: int = Field(ge=0, description="拒绝数")
    review_count: int = Field(ge=0, description="人工复审数")
    flag_count: int = Field(ge=0, description="标记数")


class VolumeStatsResponse(BaseModel):
    """Response for audit volume trend statistics."""

    granularity: str = Field(description="粒度: day/week/month")
    data: list[VolumeDataPoint] = Field(default_factory=list, description="趋势数据")


class RuleHitItem(BaseModel):
    """Single rule hit stat."""

    rule_id: str = Field(description="规则ID")
    rule_name: str = Field(description="规则名称")
    hit_count: int = Field(ge=0, description="命中次数")
    hit_rate: float = Field(ge=0.0, le=1.0, description="命中率")


class RuleHitsResponse(BaseModel):
    """Response for rule hit rate statistics."""

    total_moderation_count: int = Field(ge=0, description="审核总量")
    rules: list[RuleHitItem] = Field(default_factory=list, description="规则命中统计")


class CostDataPoint(BaseModel):
    """Single data point in cost statistics."""

    model_config = {"protected_namespaces": ()}

    period: str = Field(description="时间段标签")
    model_id: str = Field(description="模型ID")
    call_count: int = Field(ge=0, description="调用次数")
    estimated_cost: float = Field(ge=0.0, description="估算成本")


class CostStatsResponse(BaseModel):
    """Response for model invocation cost statistics."""

    data: list[CostDataPoint] = Field(default_factory=list, description="成本数据")
    total_cost: float = Field(ge=0.0, description="总成本")


# ---------------------------------------------------------------------------
# Label & Language distribution (Requirement 15.1, 15.2, 15.3)
# ---------------------------------------------------------------------------


class LabelDistributionItem(BaseModel):
    """Single item in a label distribution."""

    label: str = Field(description="标签值")
    display_name: str = Field(description="标签显示名称")
    count: int = Field(ge=0, description="命中数量")


class LabelDistributionResponse(BaseModel):
    """Response for label distribution statistics."""

    items: list[LabelDistributionItem] = Field(default_factory=list, description="标签分布数据")
    total: int = Field(ge=0, description="总数")


class LanguageDistributionItem(BaseModel):
    """Single item in a language distribution."""

    language: str = Field(description="语言代码 (ISO 639-1)")
    count: int = Field(ge=0, description="审核数量")


class LanguageDistributionResponse(BaseModel):
    """Response for language distribution statistics."""

    items: list[LanguageDistributionItem] = Field(default_factory=list, description="语言分布数据")
    total: int = Field(ge=0, description="总数")
