"""Pydantic schemas for content moderation request/response."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class ModerationRequest(BaseModel):
    """Content moderation request.

    At least one of text or image_url must be non-empty.
    """

    text: str | None = Field(default=None, description="评论文本内容")
    image_url: str | None = Field(default=None, description="图片URL或S3路径")
    business_type: str | None = Field(default=None, description="业务类型，如商品评论")
    callback_url: str | None = Field(default=None, description="回调URL")

    @model_validator(mode="after")
    def check_content_not_empty(self) -> ModerationRequest:
        text_empty = not self.text or not self.text.strip()
        image_empty = not self.image_url or not self.image_url.strip()
        if text_empty and image_empty:
            raise ValueError("text 和 image_url 不能同时为空")
        return self


class MatchedRule(BaseModel):
    """A rule matched during moderation."""

    rule_id: str = Field(description="规则ID")
    rule_name: str = Field(description="规则名称")
    action: str = Field(description="触发动作: reject/review/flag")


class ModerationResponse(BaseModel):
    """Content moderation response."""

    task_id: str = Field(description="审核任务ID")
    status: str = Field(description="任务状态: pending/processing/completed/failed")
    result: str | None = Field(default=None, description="审核结果: pass/reject/review/flag")
    text_label: str | None = Field(default=None, description="文案标签: safe/spam/toxic/hate_speech/privacy_leak/political/self_harm/illegal_trade/misleading")
    image_label: str | None = Field(default=None, description="图片标签: none/pornography/gambling/drugs/violence/terrorism/qr_code_spam/contact_info/ad_overlay/minor_exploitation")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="置信度")
    matched_rules: list[MatchedRule] = Field(default_factory=list, description="命中规则列表")
    degraded: bool = Field(default=False, description="是否降级处理")
    processing_time_ms: int | None = Field(default=None, ge=0, description="处理耗时（毫秒）")
    language: str | None = Field(default=None, description="审核内容语言代码（ISO 639-1）")
