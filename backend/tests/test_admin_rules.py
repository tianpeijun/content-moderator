"""Tests for Admin Rules CRUD API.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.6
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.rule_versions import RuleVersion
from backend.app.models.rules import Rule

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
        prompt_template="检查以下内容: {{content}}",
        variables={"content": "test"},
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


def _make_version(rule_id: uuid.UUID, version: int = 1, **overrides) -> MagicMock:
    """Build a mock RuleVersion object."""
    defaults = dict(
        id=uuid.uuid4(),
        rule_id=rule_id,
        version=version,
        snapshot={"name": "old-name", "type": "text"},
        modified_by="user-123",
        modified_at=NOW,
        change_summary="Updated fields: name",
    )
    defaults.update(overrides)
    mock = MagicMock(spec=RuleVersion)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def _patch_auth():
    """Bypass Cognito auth — return fake claims."""
    from backend.app.core.auth import verify_cognito_token

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
# Tests — GET /api/admin/rules (Requirement 3.1)
# ---------------------------------------------------------------------------

class TestListRules:
    """Validates: Requirement 3.1 — list rules with optional filtering."""

    def test_list_rules_returns_200(self, client: TestClient, mock_db):
        rule = _make_rule()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [rule]
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "违禁词检测"

    def test_list_rules_empty(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/rules")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_rules_filter_by_type(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/rules?type=image")
        assert resp.status_code == 200

    def test_list_rules_filter_by_enabled(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/rules?enabled=true")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/rules (Requirement 3.2)
# ---------------------------------------------------------------------------

class TestCreateRule:
    """Validates: Requirement 3.2 — create rule with required fields."""

    def test_create_rule_returns_201(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()

        def _add_side_effect(obj):
            obj.id = rule_id
            obj.created_at = NOW
            obj.updated_at = NOW

        mock_db.add.side_effect = _add_side_effect
        mock_db.refresh = MagicMock()

        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "新规则",
                "type": "text",
                "prompt_template": "检查内容: {{content}}",
                "action": "reject",
                "priority": 1,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "新规则"
        assert body["type"] == "text"
        assert body["action"] == "reject"
        assert body["priority"] == 1
        assert body["enabled"] is True
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_rule_missing_name_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "type": "text",
                "prompt_template": "template",
                "action": "reject",
                "priority": 1,
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_create_rule_missing_type_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "test",
                "prompt_template": "template",
                "action": "reject",
                "priority": 1,
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_create_rule_missing_prompt_template_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "test",
                "type": "text",
                "action": "reject",
                "priority": 1,
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_create_rule_missing_action_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "test",
                "type": "text",
                "prompt_template": "template",
                "priority": 1,
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_create_rule_missing_priority_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "test",
                "type": "text",
                "prompt_template": "template",
                "action": "reject",
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_create_rule_invalid_type_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "test",
                "type": "invalid",
                "prompt_template": "template",
                "action": "reject",
                "priority": 1,
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422

    def test_create_rule_invalid_action_returns_422(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/rules",
            json={
                "name": "test",
                "type": "text",
                "prompt_template": "template",
                "action": "invalid",
                "priority": 1,
            },
        )
        assert resp.status_code == 400 or resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests — PUT /api/admin/rules/{rule_id} (Requirements 3.3, 3.6)
# ---------------------------------------------------------------------------

class TestUpdateRule:
    """Validates: Requirements 3.3, 3.6 — update rule + version history."""

    def test_update_rule_returns_200(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        rule = _make_rule(id=rule_id)

        # First call: find rule; second call: max version; third: not used
        mock_result_rule = MagicMock()
        mock_result_rule.scalar_one_or_none.return_value = rule

        mock_result_version = MagicMock()
        mock_result_version.scalar_one_or_none.return_value = None  # no prior versions

        mock_db.execute.side_effect = [mock_result_rule, mock_result_version]
        mock_db.refresh = MagicMock()

        resp = client.put(
            f"/api/admin/rules/{rule_id}",
            json={"name": "更新后的规则"},
        )
        assert resp.status_code == 200
        # Verify version was saved (add called for RuleVersion)
        assert mock_db.add.call_count == 1
        mock_db.commit.assert_called_once()

    def test_update_rule_saves_version_snapshot(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        rule = _make_rule(id=rule_id, name="原始名称")

        mock_result_rule = MagicMock()
        mock_result_rule.scalar_one_or_none.return_value = rule

        mock_result_version = MagicMock()
        mock_result_version.scalar_one_or_none.return_value = 2  # existing max version

        mock_db.execute.side_effect = [mock_result_rule, mock_result_version]
        mock_db.refresh = MagicMock()

        resp = client.put(
            f"/api/admin/rules/{rule_id}",
            json={"name": "新名称"},
        )
        assert resp.status_code == 200

        # The version added should have version=3 (2+1)
        added_obj = mock_db.add.call_args[0][0]
        assert isinstance(added_obj, RuleVersion)
        assert added_obj.version == 3
        assert added_obj.snapshot["name"] == "原始名称"

    def test_update_nonexistent_rule_returns_404(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.put(
            f"/api/admin/rules/{rule_id}",
            json={"name": "test"},
        )
        assert resp.status_code == 404

    def test_update_rule_change_summary(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        rule = _make_rule(id=rule_id)

        mock_result_rule = MagicMock()
        mock_result_rule.scalar_one_or_none.return_value = rule

        mock_result_version = MagicMock()
        mock_result_version.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_result_rule, mock_result_version]
        mock_db.refresh = MagicMock()

        resp = client.put(
            f"/api/admin/rules/{rule_id}",
            json={"name": "new", "priority": 5},
        )
        assert resp.status_code == 200
        added_version = mock_db.add.call_args[0][0]
        assert "name" in added_version.change_summary
        assert "priority" in added_version.change_summary


# ---------------------------------------------------------------------------
# Tests — DELETE /api/admin/rules/{rule_id} (Requirement 3.1)
# ---------------------------------------------------------------------------

class TestDeleteRule:
    """Validates: Requirement 3.1 — delete rule."""

    def test_delete_rule_returns_204(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        rule = _make_rule(id=rule_id)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = rule
        mock_db.execute.return_value = mock_result

        resp = client.delete(f"/api/admin/rules/{rule_id}")
        assert resp.status_code == 204
        mock_db.delete.assert_called_once_with(rule)
        mock_db.commit.assert_called_once()

    def test_delete_nonexistent_rule_returns_404(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.delete(f"/api/admin/rules/{rule_id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/rules/{rule_id}/versions (Requirement 3.6)
# ---------------------------------------------------------------------------

class TestListRuleVersions:
    """Validates: Requirement 3.6 — version history."""

    def test_list_versions_returns_200(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        rule = _make_rule(id=rule_id)
        v1 = _make_version(rule_id, version=1)
        v2 = _make_version(rule_id, version=2)

        # First execute: check rule exists; second: fetch versions
        mock_result_rule = MagicMock()
        mock_result_rule.scalar_one_or_none.return_value = rule

        mock_result_versions = MagicMock()
        mock_result_versions.scalars.return_value.all.return_value = [v2, v1]

        mock_db.execute.side_effect = [mock_result_rule, mock_result_versions]

        resp = client.get(f"/api/admin/rules/{rule_id}/versions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["version"] == 2
        assert data[1]["version"] == 1

    def test_list_versions_nonexistent_rule_returns_404(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/rules/{rule_id}/versions")
        assert resp.status_code == 404

    def test_list_versions_empty(self, client: TestClient, mock_db):
        rule_id = uuid.uuid4()
        rule = _make_rule(id=rule_id)

        mock_result_rule = MagicMock()
        mock_result_rule.scalar_one_or_none.return_value = rule

        mock_result_versions = MagicMock()
        mock_result_versions.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [mock_result_rule, mock_result_versions]

        resp = client.get(f"/api/admin/rules/{rule_id}/versions")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Tests — Auth (Requirement 10.2)
# ---------------------------------------------------------------------------

class TestAdminAuth:
    """Validates: Requirement 10.2 — Cognito auth required."""

    def test_missing_auth_returns_401(self, mock_db):
        """Without Cognito token override, endpoints should return 401."""
        # Remove the auth override so real auth kicks in
        app.dependency_overrides.pop(
            __import__(
                "backend.app.core.auth", fromlist=["verify_cognito_token"]
            ).verify_cognito_token,
            None,
        )
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/rules")
            assert resp.status_code == 401
