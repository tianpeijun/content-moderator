"""Tests for Admin Prompt Preview & Test API.

Validates: Requirements 4.1, 4.2
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.model_config import ModelConfig
from backend.app.models.rules import Rule
from backend.app.services.model_invoker import ModelResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CLAIMS = {"sub": "user-123", "username": "admin"}
NOW = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_rule(**overrides) -> MagicMock:
    """Build a mock Rule object."""
    defaults = dict(
        id=uuid.uuid4(),
        name="违禁词检测",
        type="text",
        business_type="商品评论",
        prompt_template="检查以下内容是否包含违禁词。",
        variables={},
        action="reject",
        priority=1,
        enabled=True,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=Rule)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_model_config(is_primary=True, is_fallback=False) -> MagicMock:
    """Build a mock ModelConfig object."""
    mock = MagicMock(spec=ModelConfig)
    mock.model_id = "anthropic.claude-3-haiku"
    mock.temperature = 0.0
    mock.max_tokens = 1024
    mock.is_primary = is_primary
    mock.is_fallback = is_fallback
    mock.fallback_result = "review"
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_auth():
    """Bypass Cognito auth — return fake claims."""
    app.dependency_overrides[verify_cognito_token] = lambda: FAKE_CLAIMS
    yield
    app.dependency_overrides.pop(verify_cognito_token, None)


@pytest.fixture()
def mock_db():
    """Provide a mock DB session."""
    session = MagicMock()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(_patch_auth, mock_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/prompt/preview (Requirement 4.1)
# ---------------------------------------------------------------------------


class TestPromptPreview:
    """Validates: Requirement 4.1 — preview assembled prompt."""

    def test_preview_returns_assembled_prompt(self, client: TestClient, mock_db):
        rule1 = _make_rule(
            id=uuid.uuid4(),
            prompt_template="规则1：检查违禁词。",
            priority=1,
        )
        rule2 = _make_rule(
            id=uuid.uuid4(),
            prompt_template="规则2：检查广告内容。",
            priority=2,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rule1, rule2]
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/prompt/preview",
            json={
                "rule_ids": [str(rule1.id), str(rule2.id)],
                "text": "这是一条测试评论",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "prompt" in body
        assert "规则1" in body["prompt"]
        assert "规则2" in body["prompt"]
        assert "这是一条测试评论" in body["prompt"]

    def test_preview_empty_rule_ids(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/prompt/preview",
            json={"rule_ids": [], "text": "测试内容"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "prompt" in body
        assert "测试内容" in body["prompt"]

    def test_preview_with_image_url(self, client: TestClient, mock_db):
        rule = _make_rule(prompt_template="检查图片内容。", priority=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rule]
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/prompt/preview",
            json={
                "rule_ids": [str(rule.id)],
                "image_url": "https://example.com/img.png",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "https://example.com/img.png" in body["prompt"]

    def test_preview_no_content(self, client: TestClient, mock_db):
        """Preview with no text or image_url — still valid, just rules."""
        rule = _make_rule(prompt_template="基础规则。", priority=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rule]
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/prompt/preview",
            json={"rule_ids": [str(rule.id)]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "基础规则" in body["prompt"]

    def test_preview_with_template_variables(self, client: TestClient, mock_db):
        rule = _make_rule(
            prompt_template="禁止提及以下品牌：{{brands}}",
            variables={"brands": "品牌A, 品牌B"},
            priority=1,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rule]
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/prompt/preview",
            json={"rule_ids": [str(rule.id)], "text": "评论内容"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "品牌A, 品牌B" in body["prompt"]
        assert "{{" not in body["prompt"]


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/prompt/test (Requirement 4.2)
# ---------------------------------------------------------------------------


class TestPromptTest:
    """Validates: Requirement 4.2 — test prompt with AI model."""

    def test_test_returns_moderation_response(self, client: TestClient, mock_db):
        rule = _make_rule(prompt_template="检查内容。", priority=1)

        # DB: load rules
        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = [rule]

        # DB: load primary model config
        primary_config = _make_model_config(is_primary=True)
        mock_primary_result = MagicMock()
        mock_primary_result.scalar_one_or_none.return_value = primary_config

        # DB: load fallback model config
        mock_fallback_result = MagicMock()
        mock_fallback_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [
            mock_rules_result,
            mock_primary_result,
            mock_fallback_result,
        ]

        fake_model_resp = ModelResponse(
            result="pass",
            confidence=0.95,
            matched_rules=[],
            raw_response='{"result":"pass","confidence":0.95}',
            degraded=False,
            model_id="anthropic.claude-3-haiku",
        )

        with patch(
            "backend.app.api.admin_prompt._model_invoker.invoke_with_fallback",
            new_callable=AsyncMock,
            return_value=fake_model_resp,
        ):
            resp = client.post(
                "/api/admin/prompt/test",
                json={
                    "rule_ids": [str(rule.id)],
                    "text": "这是一条正常评论",
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["result"] == "pass"
        assert body["confidence"] == 0.95
        assert body["degraded"] is False
        assert "task_id" in body

    def test_test_with_image_invokes_fetcher(self, client: TestClient, mock_db):
        rule = _make_rule(prompt_template="检查图片。", priority=1)

        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = [rule]

        primary_config = _make_model_config(is_primary=True)
        mock_primary_result = MagicMock()
        mock_primary_result.scalar_one_or_none.return_value = primary_config

        mock_fallback_result = MagicMock()
        mock_fallback_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [
            mock_rules_result,
            mock_primary_result,
            mock_fallback_result,
        ]

        fake_model_resp = ModelResponse(
            result="reject",
            confidence=0.88,
            matched_rules=[{"rule_id": "r1", "rule_name": "图片审核", "action": "reject"}],
            raw_response="{}",
            degraded=False,
            model_id="anthropic.claude-3-haiku",
        )

        with patch(
            "backend.app.api.admin_prompt._image_fetcher.fetch",
            new_callable=AsyncMock,
            return_value=b"fake-image-bytes",
        ) as mock_fetch, patch(
            "backend.app.api.admin_prompt._model_invoker.invoke_with_fallback",
            new_callable=AsyncMock,
            return_value=fake_model_resp,
        ):
            resp = client.post(
                "/api/admin/prompt/test",
                json={
                    "rule_ids": [str(rule.id)],
                    "image_url": "https://example.com/img.png",
                },
            )
            mock_fetch.assert_called_once_with("https://example.com/img.png")

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == "reject"
        assert len(body["matched_rules"]) == 1

    def test_test_no_primary_model_returns_500(self, client: TestClient, mock_db):
        rule = _make_rule(prompt_template="检查。", priority=1)

        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = [rule]

        # No primary model configured
        mock_primary_result = MagicMock()
        mock_primary_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [
            mock_rules_result,
            mock_primary_result,
        ]

        resp = client.post(
            "/api/admin/prompt/test",
            json={"rule_ids": [str(rule.id)], "text": "test"},
        )
        assert resp.status_code == 500

    def test_test_model_failure_returns_500(self, client: TestClient, mock_db):
        rule = _make_rule(prompt_template="检查。", priority=1)

        mock_rules_result = MagicMock()
        mock_rules_result.scalars.return_value.all.return_value = [rule]

        primary_config = _make_model_config(is_primary=True)
        mock_primary_result = MagicMock()
        mock_primary_result.scalar_one_or_none.return_value = primary_config

        mock_fallback_result = MagicMock()
        mock_fallback_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [
            mock_rules_result,
            mock_primary_result,
            mock_fallback_result,
        ]

        with patch(
            "backend.app.api.admin_prompt._model_invoker.invoke_with_fallback",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Bedrock unavailable"),
        ):
            resp = client.post(
                "/api/admin/prompt/test",
                json={"rule_ids": [str(rule.id)], "text": "test"},
            )
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Tests — Auth (Requirement 10.2)
# ---------------------------------------------------------------------------


class TestPromptAuth:
    """Validates: Requirement 10.2 — Cognito auth required for prompt endpoints."""

    def test_preview_without_auth_returns_401(self, mock_db):
        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post(
                "/api/admin/prompt/preview",
                json={"rule_ids": [], "text": "test"},
            )
            assert resp.status_code == 401

    def test_test_without_auth_returns_401(self, mock_db):
        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post(
                "/api/admin/prompt/test",
                json={"rule_ids": [], "text": "test"},
            )
            assert resp.status_code == 401
