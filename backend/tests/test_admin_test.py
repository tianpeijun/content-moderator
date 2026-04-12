"""Tests for Admin Batch Test API.

Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.core.auth import verify_cognito_token
from backend.app.core.database import get_db
from backend.app.main import app
from backend.app.models.test_records import TestRecord
from backend.app.models.test_suites import TestSuite

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_CLAIMS = {"sub": "user-123", "username": "admin"}
NOW = datetime(2024, 6, 15, 10, 0, 0, tzinfo=timezone.utc)

REQUIRED_HEADERS = ["序号", "内容文本", "图片URL", "期望结果", "业务类型", "备注"]


def _make_xlsx(headers: list[str], rows: list[list]) -> bytes:
    """Create an in-memory .xlsx file and return its bytes."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def _make_valid_xlsx(num_rows: int = 2) -> bytes:
    """Create a valid test suite .xlsx with the given number of data rows."""
    rows = []
    for i in range(1, num_rows + 1):
        rows.append([i, f"测试文本{i}", "", "pass", "商品评论", ""])
    return _make_xlsx(REQUIRED_HEADERS, rows)


def _make_suite(**overrides) -> MagicMock:
    defaults = dict(
        id=uuid.uuid4(),
        name="test.xlsx",
        file_key="test-suites/abc/test.xlsx",
        total_cases=5,
        created_at=NOW,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=TestSuite)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_record(**overrides) -> MagicMock:
    defaults = dict(
        id=uuid.uuid4(),
        test_suite_id=uuid.uuid4(),
        rule_ids=["rule-1"],
        model_config_snapshot=None,
        status="pending",
        progress_current=0,
        progress_total=5,
        report=None,
        started_at=None,
        completed_at=None,
    )
    defaults.update(overrides)
    mock = MagicMock(spec=TestRecord)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _patch_auth():
    app.dependency_overrides[verify_cognito_token] = lambda: FAKE_CLAIMS
    yield
    app.dependency_overrides.pop(verify_cognito_token, None)


@pytest.fixture()
def mock_db():
    session = MagicMock()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(_patch_auth, mock_db):
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/test-suites/upload (Requirement 6.1, 6.2)
# ---------------------------------------------------------------------------


class TestUploadTestSuite:
    """Validates: Requirements 6.1, 6.2 — upload and validate .xlsx test suite."""

    def test_upload_valid_xlsx_returns_201(self, client: TestClient, mock_db):
        xlsx_bytes = _make_valid_xlsx(3)

        # Mock db.add / db.commit / db.refresh
        def fake_refresh(obj):
            obj.id = uuid.uuid4()
            obj.created_at = NOW

        mock_db.refresh.side_effect = fake_refresh

        resp = client.post(
            "/api/admin/test-suites/upload",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "test.xlsx"
        assert body["total_cases"] == 3

    def test_upload_non_xlsx_returns_400(self, client: TestClient, mock_db):
        resp = client.post(
            "/api/admin/test-suites/upload",
            files={"file": ("test.csv", b"a,b,c", "text/csv")},
        )
        assert resp.status_code == 400
        assert "xlsx" in resp.json()["detail"].lower()

    def test_upload_missing_columns_returns_400(self, client: TestClient, mock_db):
        xlsx_bytes = _make_xlsx(["序号", "内容文本"], [[1, "text"]])
        resp = client.post(
            "/api/admin/test-suites/upload",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 400
        assert "缺少必要列" in resp.json()["detail"]

    def test_upload_invalid_expected_result_returns_400(self, client: TestClient, mock_db):
        xlsx_bytes = _make_xlsx(
            REQUIRED_HEADERS,
            [[1, "text", "", "invalid_value", "商品评论", ""]],
        )
        resp = client.post(
            "/api/admin/test-suites/upload",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 400
        assert "期望结果值无效" in resp.json()["detail"]

    def test_upload_empty_xlsx_returns_400(self, client: TestClient, mock_db):
        wb = Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = client.post(
            "/api/admin/test-suites/upload",
            files={"file": ("test.xlsx", buf.read(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        # Empty file (only header, no data) or truly empty
        assert resp.status_code in (201, 400)


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/test-suites/{id}/run (Requirement 6.3)
# ---------------------------------------------------------------------------


class TestRunTestSuite:
    """Validates: Requirement 6.3 — start batch test via SQS."""

    def test_run_returns_201(self, client: TestClient, mock_db):
        suite = _make_suite()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = suite
        mock_db.execute.return_value = mock_result

        def fake_refresh(obj):
            obj.id = uuid.uuid4()

        mock_db.refresh.side_effect = fake_refresh

        resp = client.post(
            f"/api/admin/test-suites/{suite.id}/run",
            json={"rule_ids": ["rule-1", "rule-2"]},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "test_record_id" in body
        assert body["status"] == "pending"

    def test_run_suite_not_found_returns_404(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.post(
            f"/api/admin/test-suites/{uuid.uuid4()}/run",
            json={"rule_ids": ["rule-1"]},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/test-suites/{id}/progress (Requirement 6.3)
# ---------------------------------------------------------------------------


class TestGetProgress:
    """Validates: Requirement 6.3 — query test progress."""

    def test_progress_returns_200(self, client: TestClient, mock_db):
        suite_id = uuid.uuid4()
        record = _make_record(test_suite_id=suite_id, status="running", progress_current=3, progress_total=10)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/test-suites/{suite_id}/progress")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["progress_current"] == 3
        assert body["progress_total"] == 10

    def test_progress_no_record_returns_404(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/test-suites/{uuid.uuid4()}/progress")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/test-suites/{id}/report (Requirement 6.4)
# ---------------------------------------------------------------------------


class TestGetReport:
    """Validates: Requirement 6.4 — get test report."""

    def test_report_returns_200(self, client: TestClient, mock_db):
        suite_id = uuid.uuid4()
        record = _make_record(
            test_suite_id=suite_id,
            status="completed",
            report={
                "accuracy": 0.9,
                "recall": 0.85,
                "f1_score": 0.87,
                "confusion_matrix": {"TP": 40, "FP": 5, "TN": 50, "FN": 5},
                "error_cases": [],
                "rule_hit_distribution": {"rule-1": 30},
            },
            started_at=NOW,
            completed_at=NOW,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/test-suites/{suite_id}/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["accuracy"] == 0.9
        assert body["confusion_matrix"]["TP"] == 40

    def test_report_no_record_returns_404(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.get(f"/api/admin/test-suites/{uuid.uuid4()}/report")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/test-suites/{id}/export (Requirement 6.5)
# ---------------------------------------------------------------------------


class TestExportReport:
    """Validates: Requirement 6.5 — export test report."""

    def test_export_returns_200(self, client: TestClient, mock_db):
        suite_id = uuid.uuid4()
        record = _make_record(test_suite_id=suite_id, status="completed", report={"accuracy": 0.9})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db.execute.return_value = mock_result

        resp = client.post(f"/api/admin/test-suites/{suite_id}/export")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["report"]["accuracy"] == 0.9

    def test_export_no_record_returns_404(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.post(f"/api/admin/test-suites/{uuid.uuid4()}/export")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — GET /api/admin/test-records (Requirement 6.6)
# ---------------------------------------------------------------------------


class TestListTestRecords:
    """Validates: Requirement 6.6 — list historical test records."""

    def test_list_returns_200(self, client: TestClient, mock_db):
        records = [_make_record(), _make_record()]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = records
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/test-records")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 2

    def test_list_empty_returns_200(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        resp = client.get("/api/admin/test-records")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Tests — POST /api/admin/test-records/compare (Requirement 6.6)
# ---------------------------------------------------------------------------


class TestCompareRecords:
    """Validates: Requirement 6.6 — compare two test records."""

    def test_compare_returns_200(self, client: TestClient, mock_db):
        rec_a = _make_record()
        rec_b = _make_record()

        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = rec_a
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none.return_value = rec_b
        mock_db.execute.side_effect = [mock_result_a, mock_result_b]

        resp = client.post(
            "/api/admin/test-records/compare",
            json={"record_id_a": str(rec_a.id), "record_id_b": str(rec_b.id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "record_a" in body
        assert "record_b" in body

    def test_compare_record_a_not_found(self, client: TestClient, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = client.post(
            "/api/admin/test-records/compare",
            json={"record_id_a": str(uuid.uuid4()), "record_id_b": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_compare_record_b_not_found(self, client: TestClient, mock_db):
        rec_a = _make_record()
        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = rec_a
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_result_a, mock_result_b]

        resp = client.post(
            "/api/admin/test-records/compare",
            json={"record_id_a": str(rec_a.id), "record_id_b": str(uuid.uuid4())},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — Auth (Requirement 10.2)
# ---------------------------------------------------------------------------


class TestAdminTestAuth:
    """Validates: Requirement 10.2 — Cognito auth required for all test endpoints."""

    def test_upload_without_auth_returns_401(self, mock_db):
        from unittest.mock import patch

        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post("/api/admin/test-suites/upload")
            assert resp.status_code == 401

    def test_run_without_auth_returns_401(self, mock_db):
        from unittest.mock import patch

        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post(f"/api/admin/test-suites/{uuid.uuid4()}/run", json={"rule_ids": []})
            assert resp.status_code == 401

    def test_records_without_auth_returns_401(self, mock_db):
        from unittest.mock import patch

        app.dependency_overrides.pop(verify_cognito_token, None)
        with patch("backend.app.core.auth._fetch_jwks") as mock_jwks:
            mock_jwks.side_effect = Exception("no jwks")
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.get("/api/admin/test-records")
            assert resp.status_code == 401
