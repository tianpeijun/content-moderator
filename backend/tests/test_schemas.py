"""Tests for Pydantic schemas."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from backend.app.schemas.model_config import ModelConfigResponse, ModelConfigUpdate
from backend.app.schemas.moderation import (
    MatchedRule,
    ModerationRequest,
    ModerationResponse,
)
from backend.app.schemas.rules import (
    RuleCreate,
    RuleResponse,
    RuleUpdate,
    RuleVersionResponse,
)
from backend.app.schemas.test_records import TestRecordCompareRequest, TestRecordResponse
from backend.app.schemas.test_suites import (
    TestReportResponse,
    TestSuiteProgressResponse,
    TestSuiteUploadResponse,
)


# --- ModerationRequest ---


class TestModerationRequest:
    def test_valid_text_only(self):
        req = ModerationRequest(text="hello")
        assert req.text == "hello"
        assert req.image_url is None

    def test_valid_image_only(self):
        req = ModerationRequest(image_url="https://example.com/img.jpg")
        assert req.image_url == "https://example.com/img.jpg"

    def test_valid_both(self):
        req = ModerationRequest(text="hello", image_url="s3://bucket/key")
        assert req.text == "hello"
        assert req.image_url == "s3://bucket/key"

    def test_reject_both_empty(self):
        with pytest.raises(ValidationError, match="不能同时为空"):
            ModerationRequest()

    def test_reject_both_none(self):
        with pytest.raises(ValidationError):
            ModerationRequest(text=None, image_url=None)

    def test_reject_both_blank(self):
        with pytest.raises(ValidationError):
            ModerationRequest(text="   ", image_url="  ")

    def test_reject_empty_strings(self):
        with pytest.raises(ValidationError):
            ModerationRequest(text="", image_url="")

    def test_optional_fields(self):
        req = ModerationRequest(text="test", business_type="商品评论", callback_url="https://cb.com")
        assert req.business_type == "商品评论"
        assert req.callback_url == "https://cb.com"


# --- ModerationResponse ---


class TestModerationResponse:
    def test_minimal(self):
        resp = ModerationResponse(task_id="abc-123", status="pending")
        assert resp.task_id == "abc-123"
        assert resp.matched_rules == []
        assert resp.degraded is False

    def test_full(self):
        resp = ModerationResponse(
            task_id="abc",
            status="completed",
            result="reject",
            confidence=0.95,
            matched_rules=[MatchedRule(rule_id="r1", rule_name="违禁词", action="reject")],
            degraded=True,
            processing_time_ms=1200,
        )
        assert resp.result == "reject"
        assert len(resp.matched_rules) == 1


# --- RuleCreate ---


class TestRuleCreate:
    def test_valid(self):
        rule = RuleCreate(
            name="违禁词检测",
            type="text",
            prompt_template="检查以下内容: {{content}}",
            action="reject",
            priority=1,
        )
        assert rule.name == "违禁词检测"
        assert rule.enabled is True

    def test_reject_invalid_type(self):
        with pytest.raises(ValidationError):
            RuleCreate(
                name="test", type="invalid", prompt_template="t", action="reject", priority=1
            )

    def test_reject_invalid_action(self):
        with pytest.raises(ValidationError):
            RuleCreate(
                name="test", type="text", prompt_template="t", action="invalid", priority=1
            )

    def test_reject_missing_name(self):
        with pytest.raises(ValidationError):
            RuleCreate(type="text", prompt_template="t", action="reject", priority=1)

    def test_reject_empty_name(self):
        with pytest.raises(ValidationError):
            RuleCreate(name="", type="text", prompt_template="t", action="reject", priority=1)

    def test_reject_negative_priority(self):
        with pytest.raises(ValidationError):
            RuleCreate(name="test", type="text", prompt_template="t", action="reject", priority=-1)

    def test_reject_missing_prompt_template(self):
        with pytest.raises(ValidationError):
            RuleCreate(name="test", type="text", action="reject", priority=1)


# --- RuleUpdate ---


class TestRuleUpdate:
    def test_partial_update(self):
        update = RuleUpdate(name="new name")
        assert update.name == "new name"
        assert update.type is None

    def test_empty_update(self):
        update = RuleUpdate()
        assert update.name is None


# --- RuleResponse ---


class TestRuleResponse:
    def test_from_dict(self):
        now = datetime.utcnow()
        resp = RuleResponse(
            id=uuid.uuid4(),
            name="test",
            type="text",
            prompt_template="template",
            action="reject",
            priority=1,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        assert resp.name == "test"


# --- RuleVersionResponse ---


class TestRuleVersionResponse:
    def test_from_dict(self):
        now = datetime.utcnow()
        resp = RuleVersionResponse(
            id=uuid.uuid4(),
            rule_id=uuid.uuid4(),
            version=1,
            snapshot={"name": "test"},
            modified_at=now,
        )
        assert resp.version == 1


# --- TestSuiteUploadResponse ---


class TestTestSuiteUploadResponse:
    def test_valid(self):
        resp = TestSuiteUploadResponse(
            id=uuid.uuid4(), name="suite1", total_cases=100, created_at=datetime.utcnow()
        )
        assert resp.total_cases == 100


# --- TestSuiteProgressResponse ---


class TestTestSuiteProgressResponse:
    def test_valid(self):
        resp = TestSuiteProgressResponse(
            test_record_id=uuid.uuid4(), status="running", progress_current=50, progress_total=100
        )
        assert resp.progress_current == 50


# --- TestReportResponse ---


class TestTestReportResponse:
    def test_valid(self):
        resp = TestReportResponse(
            test_record_id=uuid.uuid4(),
            test_suite_id=uuid.uuid4(),
            status="completed",
            accuracy=0.95,
            recall=0.90,
            f1_score=0.92,
            confusion_matrix={"TP": 90, "FP": 5, "TN": 3, "FN": 2},
        )
        assert resp.accuracy == 0.95


# --- TestRecordResponse ---


class TestTestRecordResponse:
    def test_valid(self):
        resp = TestRecordResponse(
            id=uuid.uuid4(),
            test_suite_id=uuid.uuid4(),
            status="completed",
            progress_current=100,
            progress_total=100,
        )
        assert resp.status == "completed"


# --- TestRecordCompareRequest ---


class TestTestRecordCompareRequest:
    def test_valid(self):
        req = TestRecordCompareRequest(record_id_a=uuid.uuid4(), record_id_b=uuid.uuid4())
        assert req.record_id_a != req.record_id_b


# --- ModelConfigResponse ---


class TestModelConfigResponse:
    def test_valid(self):
        resp = ModelConfigResponse(
            id=uuid.uuid4(),
            model_id="anthropic.claude-3-sonnet",
            model_name="Claude 3 Sonnet",
            temperature=0.0,
            max_tokens=1024,
            is_primary=True,
            is_fallback=False,
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            updated_at=datetime.utcnow(),
        )
        assert resp.is_primary is True


# --- ModelConfigUpdate ---


class TestModelConfigUpdate:
    def test_partial(self):
        update = ModelConfigUpdate(temperature=0.5)
        assert update.temperature == 0.5
        assert update.model_id is None

    def test_reject_invalid_temperature(self):
        with pytest.raises(ValidationError):
            ModelConfigUpdate(temperature=3.0)
