"""Tests for POST /api/v1/moderate endpoint.

Validates: Requirements 1.1, 1.2, 1.3, 1.5, 5.4
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import Base
from backend.app.main import app
from backend.app.models.model_config import ModelConfig
from backend.app.models.moderation_logs import ModerationLog
from backend.app.services.model_invoker import ModelResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_API_KEY = "test-moderation-key"


def _make_primary_config() -> MagicMock:
    """Return a mock ModelConfig row marked as primary."""
    cfg = MagicMock(spec=ModelConfig)
    cfg.model_id = "anthropic.claude-3-haiku"
    cfg.temperature = 0.0
    cfg.max_tokens = 1024
    cfg.is_primary = True
    cfg.is_fallback = False
    cfg.fallback_result = "review"
    return cfg


def _make_fallback_config() -> MagicMock:
    cfg = MagicMock(spec=ModelConfig)
    cfg.model_id = "amazon.nova-lite"
    cfg.temperature = 0.0
    cfg.max_tokens = 512
    cfg.is_primary = False
    cfg.is_fallback = True
    cfg.fallback_result = None
    return cfg


def _ok_model_response(**overrides) -> ModelResponse:
    defaults = dict(
        result="pass",
        confidence=0.95,
        matched_rules=[],
        raw_response='{"result":"pass","confidence":0.95}',
        degraded=False,
        model_id="anthropic.claude-3-haiku",
    )
    defaults.update(overrides)
    return ModelResponse(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _patch_auth():
    """Bypass API key auth for all tests in this module."""
    with patch("backend.app.core.auth.settings") as mock_settings:
        mock_settings.api_keys = [VALID_API_KEY]
        yield


@pytest.fixture()
def _mock_db():
    """Provide a mock DB session via the get_db dependency override."""
    mock_session = MagicMock()

    # Default: primary config exists, no fallback
    primary = _make_primary_config()
    fallback = _make_fallback_config()

    def _scalar_one_or_none_side_effect():
        """Return primary or fallback based on the last executed query."""
        call_args = mock_session.execute.call_args
        # Inspect the compiled SQL to decide which config to return
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "is_primary" in compiled:
            return primary
        if "is_fallback" in compiled:
            return fallback
        return None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none = _scalar_one_or_none_side_effect
    mock_session.execute.return_value = mock_result
    mock_session.commit = MagicMock()
    mock_session.add = MagicMock()

    from backend.app.core.database import get_db

    app.dependency_overrides[get_db] = lambda: mock_session
    yield mock_session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(_patch_auth, _mock_db):
    """TestClient with auth and DB mocked."""
    return TestClient(app)


@pytest.fixture()
def mock_db(_mock_db):
    return _mock_db


# ---------------------------------------------------------------------------
# Tests — Input Validation (Requirement 1.5)
# ---------------------------------------------------------------------------

class TestInputValidation:
    """Validates: Requirement 1.5 — empty content returns 400."""

    def test_both_empty_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/v1/moderate",
            json={"text": None, "image_url": None},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert resp.status_code == 400

    def test_both_blank_strings_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/v1/moderate",
            json={"text": "   ", "image_url": "  "},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert resp.status_code == 400

    def test_empty_body_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/v1/moderate",
            json={},
            headers={"X-API-Key": VALID_API_KEY},
        )
        assert resp.status_code == 400

    def test_missing_api_key_returns_401(self):
        """No auth header → 401 (Requirement 1.7)."""
        with patch("backend.app.core.auth.settings") as ms:
            ms.api_keys = [VALID_API_KEY]
            c = TestClient(app)
            resp = c.post("/api/v1/moderate", json={"text": "hello"})
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Tests — Successful moderation (Requirements 1.1, 1.2, 1.3, 5.4)
# ---------------------------------------------------------------------------

class TestModerateEndpoint:
    """Validates: Requirements 1.1, 1.2, 1.3, 5.4"""

    @patch("backend.app.api.moderation._model_invoker")
    @patch("backend.app.api.moderation._rule_engine")
    def test_text_only_moderation(
        self, mock_re, mock_invoker, client, mock_db
    ):
        """Req 1.1 — text-only moderation returns a completed response."""
        mock_re.get_active_rules.return_value = []
        mock_re.assemble_prompt.return_value = "审核提示词"
        mock_invoker.invoke_with_fallback = AsyncMock(
            return_value=_ok_model_response()
        )

        resp = client.post(
            "/api/v1/moderate",
            json={"text": "这是一条正常评论"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["result"] == "pass"
        assert body["confidence"] == 0.95
        assert body["degraded"] is False
        assert "task_id" in body
        assert body["processing_time_ms"] >= 0

        # Verify log was persisted (Req 5.4)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("backend.app.api.moderation._image_fetcher")
    @patch("backend.app.api.moderation._model_invoker")
    @patch("backend.app.api.moderation._rule_engine")
    def test_text_and_image_moderation(
        self, mock_re, mock_invoker, mock_fetcher, client, mock_db
    ):
        """Req 1.2 — text + image moderation."""
        mock_re.get_active_rules.return_value = []
        mock_re.assemble_prompt.return_value = "审核提示词"
        mock_fetcher.fetch = AsyncMock(return_value=b"fake-image-bytes")
        mock_invoker.invoke_with_fallback = AsyncMock(
            return_value=_ok_model_response(result="reject", confidence=0.88)
        )

        resp = client.post(
            "/api/v1/moderate",
            json={"text": "评论", "image_url": "https://example.com/img.png"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["result"] == "reject"
        mock_fetcher.fetch.assert_awaited_once_with("https://example.com/img.png")

    @patch("backend.app.api.moderation._image_fetcher")
    @patch("backend.app.api.moderation._model_invoker")
    @patch("backend.app.api.moderation._rule_engine")
    def test_image_only_moderation(
        self, mock_re, mock_invoker, mock_fetcher, client, mock_db
    ):
        """Req 1.3 — image-only moderation."""
        mock_re.get_active_rules.return_value = []
        mock_re.assemble_prompt.return_value = "审核提示词"
        mock_fetcher.fetch = AsyncMock(return_value=b"img")
        mock_invoker.invoke_with_fallback = AsyncMock(
            return_value=_ok_model_response()
        )

        resp = client.post(
            "/api/v1/moderate",
            json={"image_url": "s3://bucket/key.png"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @patch("backend.app.api.moderation._model_invoker")
    @patch("backend.app.api.moderation._rule_engine")
    def test_matched_rules_in_response(
        self, mock_re, mock_invoker, client, mock_db
    ):
        """Matched rules from model response appear in the API response."""
        mock_re.get_active_rules.return_value = []
        mock_re.assemble_prompt.return_value = "prompt"
        mock_invoker.invoke_with_fallback = AsyncMock(
            return_value=_ok_model_response(
                matched_rules=[
                    {"rule_id": "r1", "rule_name": "违禁词", "action": "reject"}
                ]
            )
        )

        resp = client.post(
            "/api/v1/moderate",
            json={"text": "test"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        body = resp.json()
        assert len(body["matched_rules"]) == 1
        assert body["matched_rules"][0]["rule_name"] == "违禁词"

    @patch("backend.app.api.moderation._model_invoker")
    @patch("backend.app.api.moderation._rule_engine")
    def test_degraded_flag_propagated(
        self, mock_re, mock_invoker, client, mock_db
    ):
        """Degraded flag from model invoker is propagated to response."""
        mock_re.get_active_rules.return_value = []
        mock_re.assemble_prompt.return_value = "prompt"
        mock_invoker.invoke_with_fallback = AsyncMock(
            return_value=_ok_model_response(degraded=True, result="review")
        )

        resp = client.post(
            "/api/v1/moderate",
            json={"text": "test"},
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.json()["degraded"] is True


# ---------------------------------------------------------------------------
# Tests — GET /api/v1/moderate/{task_id} (Requirements 2.1, 2.2, 2.3)
# ---------------------------------------------------------------------------

class TestGetModerationResult:
    """Validates: Requirements 2.1, 2.2, 2.3"""

    def test_valid_task_id_returns_200(self, client: TestClient, mock_db):
        """Req 2.1, 2.3 — completed task returns full result details."""
        fake_log = MagicMock(spec=ModerationLog)
        fake_log.task_id = "abc-123"
        fake_log.status = "completed"
        fake_log.result = "reject"
        fake_log.confidence = 0.92
        fake_log.matched_rules = [
            {"rule_id": "r1", "rule_name": "违禁词检测", "action": "reject"}
        ]
        fake_log.degraded = False
        fake_log.processing_time_ms = 850

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_log
        mock_db.execute.return_value = mock_result

        resp = client.get(
            "/api/v1/moderate/abc-123",
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "abc-123"
        assert body["status"] == "completed"
        assert body["result"] == "reject"
        assert body["confidence"] == 0.92
        assert body["degraded"] is False
        assert body["processing_time_ms"] == 850
        assert len(body["matched_rules"]) == 1
        assert body["matched_rules"][0]["rule_name"] == "违禁词检测"

    def test_nonexistent_task_id_returns_404(self, client: TestClient, mock_db):
        """Req 2.2 — unknown taskId returns 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.get(
            "/api/v1/moderate/nonexistent-id",
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_missing_api_key_returns_401(self):
        """Req 10.1 — missing API key returns 401."""
        with patch("backend.app.core.auth.settings") as ms:
            ms.api_keys = [VALID_API_KEY]
            c = TestClient(app)
            resp = c.get("/api/v1/moderate/some-task-id")
            assert resp.status_code == 401

    def test_pending_task_returns_status_only(self, client: TestClient, mock_db):
        """Req 2.1 — pending task returns status without result details."""
        fake_log = MagicMock(spec=ModerationLog)
        fake_log.task_id = "pending-task"
        fake_log.status = "pending"
        fake_log.result = None
        fake_log.confidence = None
        fake_log.matched_rules = None
        fake_log.degraded = False
        fake_log.processing_time_ms = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = fake_log
        mock_db.execute.return_value = mock_result

        resp = client.get(
            "/api/v1/moderate/pending-task",
            headers={"X-API-Key": VALID_API_KEY},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "pending-task"
        assert body["status"] == "pending"
        assert body["result"] is None
        assert body["confidence"] is None
        assert body["matched_rules"] == []
        assert body["processing_time_ms"] is None
