"""Tests for BatchTestWorker.

Validates: Requirements 6.3, 6.7
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.batch_test_worker import (
    BatchTestWorker,
    TestCase,
    TestCaseResult,
    calculate_metrics,
    lambda_handler,
)
from backend.app.services.model_invoker import ModelResponse, ModelSettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model_response(result: str = "pass", confidence: float = 0.95) -> ModelResponse:
    return ModelResponse(
        result=result,
        confidence=confidence,
        matched_rules=[],
        raw_response="",
        degraded=False,
        model_id="test-model",
    )


def _make_test_record_mock(
    record_id=None,
    suite_id=None,
    status="pending",
    progress_current=0,
    progress_total=0,
):
    record = MagicMock()
    record.id = record_id or uuid.uuid4()
    record.test_suite_id = suite_id or uuid.uuid4()
    record.status = status
    record.progress_current = progress_current
    record.progress_total = progress_total
    record.started_at = None
    record.completed_at = None
    record.report = None
    record.rule_ids = []
    return record


def _make_test_suite_mock(suite_id=None, total_cases=3):
    suite = MagicMock()
    suite.id = suite_id or uuid.uuid4()
    suite.name = "test_suite.xlsx"
    suite.file_key = "test-suites/abc/test.xlsx"
    suite.total_cases = total_cases
    return suite


def _make_rule_mock(rule_id=None, priority=1, name="test-rule"):
    rule = MagicMock()
    rule.id = rule_id or uuid.uuid4()
    rule.name = name
    rule.priority = priority
    rule.prompt_template = "审核规则: {{content}}"
    rule.variables = {"content": "测试"}
    rule.enabled = True
    rule.business_type = "商品评论"
    rule.type = "text"
    rule.action = "reject"
    return rule


# ---------------------------------------------------------------------------
# Tests — TestCase / TestCaseResult dataclasses
# ---------------------------------------------------------------------------


class TestDataClasses:
    """Basic sanity checks for data classes."""

    def test_test_case_defaults(self):
        tc = TestCase(index=1)
        assert tc.index == 1
        assert tc.text is None
        assert tc.image_url is None
        assert tc.expected_result == "pass"
        assert tc.business_type is None
        assert tc.notes is None

    def test_test_case_with_values(self):
        tc = TestCase(
            index=5,
            text="hello",
            image_url="https://img.example.com/1.png",
            expected_result="reject",
            business_type="商品评论",
            notes="test note",
        )
        assert tc.index == 5
        assert tc.text == "hello"
        assert tc.expected_result == "reject"

    def test_test_case_result_defaults(self):
        r = TestCaseResult(index=1, expected="pass", actual="pass", passed=True)
        assert r.confidence == 0.0
        assert r.matched_rules == []
        assert r.error is None

    def test_test_case_result_with_error(self):
        r = TestCaseResult(
            index=2, expected="reject", actual="error", passed=False, error="timeout"
        )
        assert r.error == "timeout"
        assert not r.passed


# ---------------------------------------------------------------------------
# Tests — _execute_single_case
# ---------------------------------------------------------------------------


class TestExecuteSingleCase:
    """Validates: Requirement 6.3 — invoke moderation pipeline per case."""

    @pytest.mark.asyncio
    async def test_matching_result_marks_passed(self):
        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(
            return_value=_make_model_response("pass", 0.9)
        )
        worker = BatchTestWorker(model_invoker=invoker)

        case = TestCase(index=1, text="good review", expected_result="pass")
        result = await worker._execute_single_case(
            case, rules=[], model_settings=ModelSettings(model_id="m")
        )

        assert result.passed is True
        assert result.actual == "pass"
        assert result.expected == "pass"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_mismatching_result_marks_not_passed(self):
        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(
            return_value=_make_model_response("reject", 0.8)
        )
        worker = BatchTestWorker(model_invoker=invoker)

        case = TestCase(index=2, text="bad review", expected_result="pass")
        result = await worker._execute_single_case(
            case, rules=[], model_settings=ModelSettings(model_id="m")
        )

        assert result.passed is False
        assert result.actual == "reject"
        assert result.expected == "pass"

    @pytest.mark.asyncio
    async def test_exception_captured_as_error(self):
        """Validates: Requirement 6.7 — single case failure doesn't abort."""
        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(
            side_effect=RuntimeError("model exploded")
        )
        worker = BatchTestWorker(model_invoker=invoker)

        case = TestCase(index=3, text="text", expected_result="pass")
        result = await worker._execute_single_case(
            case, rules=[], model_settings=ModelSettings(model_id="m")
        )

        assert result.passed is False
        assert result.actual == "error"
        assert "model exploded" in result.error

    @pytest.mark.asyncio
    async def test_label_mismatch_marks_not_passed(self):
        """Result matches but label mismatch should mark as not passed."""
        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(
            return_value=ModelResponse(
                result="reject", text_label="toxic", image_label="无",
                confidence=0.9, matched_rules=[], raw_response="",
                degraded=False, model_id="test-model",
            )
        )
        worker = BatchTestWorker(model_invoker=invoker)

        case = TestCase(
            index=1, text="bad text", expected_result="reject",
            expected_text_label="spam",  # mismatch: actual is "toxic"
        )
        result = await worker._execute_single_case(
            case, rules=[], model_settings=ModelSettings(model_id="m")
        )

        assert result.passed is False
        assert result.actual == "reject"
        assert result.actual_text_label == "toxic"
        assert result.expected_text_label == "spam"

    @pytest.mark.asyncio
    async def test_labels_captured_from_response(self):
        """Actual labels should be captured from ModelResponse."""
        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(
            return_value=ModelResponse(
                result="pass", text_label="safe", image_label="无",
                confidence=0.95, matched_rules=[], raw_response="",
                degraded=False, model_id="test-model",
            )
        )
        worker = BatchTestWorker(model_invoker=invoker)

        case = TestCase(index=1, text="good review", expected_result="pass")
        result = await worker._execute_single_case(
            case, rules=[], model_settings=ModelSettings(model_id="m")
        )

        assert result.actual_text_label == "safe"
        assert result.actual_image_label == "无"


# ---------------------------------------------------------------------------
# Tests — process_test_suite
# ---------------------------------------------------------------------------


class TestProcessTestSuite:
    """Validates: Requirements 6.3, 6.7 — full suite processing."""

    @pytest.mark.asyncio
    async def test_process_updates_record_to_completed(self):
        record_id = uuid.uuid4()
        suite_id = uuid.uuid4()

        record = _make_test_record_mock(record_id=record_id, suite_id=suite_id)
        suite = _make_test_suite_mock(suite_id=suite_id, total_cases=2)

        db = MagicMock()
        db.get.side_effect = lambda model, uid: (
            record if model.__name__ == "TestRecord" else suite
        )
        # For _load_rules and _load_model_settings
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_exec = MagicMock()
        mock_exec.scalars.return_value = mock_scalars
        mock_exec.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_exec

        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(
            return_value=_make_model_response("pass", 0.95)
        )
        worker = BatchTestWorker(model_invoker=invoker)

        await worker.process_test_suite(
            test_record_id=str(record_id),
            test_suite_id=str(suite_id),
            rule_ids=[],
            db=db,
        )

        assert record.status == "completed"
        assert record.completed_at is not None
        assert record.report is not None
        assert record.progress_current == 2

    @pytest.mark.asyncio
    async def test_process_missing_record_returns_early(self):
        db = MagicMock()
        db.get.return_value = None

        worker = BatchTestWorker()
        # Should not raise
        await worker.process_test_suite(
            test_record_id=str(uuid.uuid4()),
            test_suite_id=str(uuid.uuid4()),
            rule_ids=[],
            db=db,
        )
        # No commit for status update since record was not found
        db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_single_failure_does_not_abort_batch(self):
        """Validates: Requirement 6.7 — single case failure continues."""
        record_id = uuid.uuid4()
        suite_id = uuid.uuid4()

        record = _make_test_record_mock(record_id=record_id, suite_id=suite_id)
        suite = _make_test_suite_mock(suite_id=suite_id, total_cases=3)

        db = MagicMock()
        db.get.side_effect = lambda model, uid: (
            record if model.__name__ == "TestRecord" else suite
        )
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_exec = MagicMock()
        mock_exec.scalars.return_value = mock_scalars
        mock_exec.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_exec

        call_count = 0

        async def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("transient failure")
            return _make_model_response("pass", 0.9)

        invoker = MagicMock()
        invoker.invoke_with_fallback = AsyncMock(side_effect=_side_effect)
        worker = BatchTestWorker(model_invoker=invoker)

        await worker.process_test_suite(
            test_record_id=str(record_id),
            test_suite_id=str(suite_id),
            rule_ids=[],
            db=db,
        )

        # All 3 cases processed despite failure on case 2
        assert record.status == "completed"
        assert record.progress_current == 3
        # Report should contain error cases
        error_cases = record.report["error_cases"]
        assert len(error_cases) == 1
        assert error_cases[0]["index"] == 2


# ---------------------------------------------------------------------------
# Tests — calculate_metrics
# ---------------------------------------------------------------------------


class TestCalculateMetrics:
    """Validates: Requirement 6.4 — metrics computation.

    **Validates: Requirements 6.4**
    """

    def test_empty_results(self):
        report = calculate_metrics([])
        assert report["accuracy"] == 0.0
        assert report["precision"] == 0.0
        assert report["recall"] == 0.0
        assert report["f1_score"] == 0.0
        assert report["confusion_matrix"]["TP"] == 0
        assert report["confusion_matrix"]["FP"] == 0
        assert report["confusion_matrix"]["TN"] == 0
        assert report["confusion_matrix"]["FN"] == 0
        assert report["error_cases"] == []
        assert report["rule_hit_distribution"] == {}

    def test_all_correct(self):
        results = [
            TestCaseResult(index=1, expected="pass", actual="pass", passed=True),
            TestCaseResult(index=2, expected="reject", actual="reject", passed=True),
        ]
        report = calculate_metrics(results)
        assert report["accuracy"] == 1.0
        assert report["error_cases"] == []
        # Property 5: TP+FP+TN+FN == total
        cm = report["confusion_matrix"]
        assert cm["TP"] + cm["FP"] + cm["TN"] + cm["FN"] == len(results)
        assert cm["TP"] == 1  # reject matched
        assert cm["TN"] == 1  # pass matched

    def test_mixed_results(self):
        results = [
            TestCaseResult(index=1, expected="pass", actual="pass", passed=True),
            TestCaseResult(index=2, expected="reject", actual="pass", passed=False),
            TestCaseResult(index=3, expected="pass", actual="reject", passed=False),
        ]
        report = calculate_metrics(results)
        cm = report["confusion_matrix"]
        # Property 5: TP+FP+TN+FN == total
        assert cm["TP"] + cm["FP"] + cm["TN"] + cm["FN"] == len(results)
        assert cm["TP"] == 0  # no reject correctly predicted
        assert cm["FP"] == 1  # expected=pass, actual=reject
        assert cm["TN"] == 1  # expected=pass, actual=pass
        assert cm["FN"] == 1  # expected=reject, actual=pass
        assert report["accuracy"] == pytest.approx(1 / 3, abs=0.01)
        assert len(report["error_cases"]) == 2

    def test_property5_tn_without_passed_flag(self):
        """TN must count cases where expected!=reject AND actual!=reject,
        regardless of the passed flag. E.g. expected=pass, actual=review
        is TN (both non-reject) even though passed=False.

        Property 5: TP+FP+TN+FN == total
        """
        results = [
            # expected=pass, actual=review → TN (both non-reject), passed=False
            TestCaseResult(index=1, expected="pass", actual="review", passed=False),
            # expected=reject, actual=reject → TP
            TestCaseResult(index=2, expected="reject", actual="reject", passed=True),
            # expected=reject, actual="pass" → FN
            TestCaseResult(index=3, expected="reject", actual="pass", passed=False),
            # expected=review, actual=reject → FP
            TestCaseResult(index=4, expected="review", actual="reject", passed=False),
        ]
        report = calculate_metrics(results)
        cm = report["confusion_matrix"]
        total = len(results)
        assert cm["TP"] + cm["FP"] + cm["TN"] + cm["FN"] == total
        assert cm["TP"] == 1
        assert cm["FP"] == 1
        assert cm["TN"] == 1
        assert cm["FN"] == 1
        assert report["accuracy"] == pytest.approx(2 / 4, abs=0.001)

    def test_precision_recall_f1_formulas(self):
        """Verify precision, recall, F1 formulas match Property 5 definitions."""
        results = [
            TestCaseResult(index=1, expected="reject", actual="reject", passed=True),
            TestCaseResult(index=2, expected="reject", actual="reject", passed=True),
            TestCaseResult(index=3, expected="pass", actual="reject", passed=False),
            TestCaseResult(index=4, expected="reject", actual="pass", passed=False),
            TestCaseResult(index=5, expected="pass", actual="pass", passed=True),
        ]
        report = calculate_metrics(results)
        cm = report["confusion_matrix"]
        # Property 5: TP+FP+TN+FN == total
        assert cm["TP"] + cm["FP"] + cm["TN"] + cm["FN"] == len(results)
        assert cm["TP"] == 2
        assert cm["FP"] == 1
        assert cm["TN"] == 1
        assert cm["FN"] == 1

        # Precision = TP / (TP + FP) = 2/3
        expected_precision = 2 / 3
        assert report["precision"] == pytest.approx(expected_precision, abs=0.001)

        # Recall = TP / (TP + FN) = 2/3
        expected_recall = 2 / 3
        assert report["recall"] == pytest.approx(expected_recall, abs=0.001)

        # F1 = 2 * P * R / (P + R)
        expected_f1 = 2 * expected_precision * expected_recall / (expected_precision + expected_recall)
        assert report["f1_score"] == pytest.approx(expected_f1, abs=0.001)

        # Accuracy = (TP + TN) / total = 3/5
        assert report["accuracy"] == pytest.approx(3 / 5, abs=0.001)

    def test_no_positive_cases(self):
        """When there are no reject cases, precision/recall/F1 should be 0."""
        results = [
            TestCaseResult(index=1, expected="pass", actual="pass", passed=True),
            TestCaseResult(index=2, expected="review", actual="review", passed=True),
        ]
        report = calculate_metrics(results)
        cm = report["confusion_matrix"]
        assert cm["TP"] + cm["FP"] + cm["TN"] + cm["FN"] == len(results)
        assert cm["TP"] == 0
        assert cm["FP"] == 0
        assert cm["TN"] == 2
        assert cm["FN"] == 0
        assert report["precision"] == 0.0
        assert report["recall"] == 0.0
        assert report["f1_score"] == 0.0
        assert report["accuracy"] == 1.0

    def test_error_cases_list(self):
        """Error cases should list all cases where expected != actual."""
        results = [
            TestCaseResult(index=1, expected="pass", actual="pass", passed=True),
            TestCaseResult(index=2, expected="reject", actual="pass", passed=False),
            TestCaseResult(
                index=3, expected="pass", actual="error", passed=False, error="timeout"
            ),
        ]
        report = calculate_metrics(results)
        error_cases = report["error_cases"]
        assert len(error_cases) == 2
        indices = [e["index"] for e in error_cases]
        assert 2 in indices
        assert 3 in indices
        # Verify error field is captured
        case3 = next(e for e in error_cases if e["index"] == 3)
        assert case3["error"] == "timeout"

    def test_rule_hit_distribution(self):
        results = [
            TestCaseResult(
                index=1,
                expected="reject",
                actual="reject",
                passed=True,
                matched_rules=[{"rule_name": "spam"}],
            ),
            TestCaseResult(
                index=2,
                expected="reject",
                actual="reject",
                passed=True,
                matched_rules=[{"rule_name": "spam"}, {"rule_name": "ads"}],
            ),
        ]
        report = calculate_metrics(results)
        assert report["rule_hit_distribution"]["spam"] == 2
        assert report["rule_hit_distribution"]["ads"] == 1

    def test_label_accuracy_all_matching(self):
        """text_label_accuracy and image_label_accuracy should be 1.0 when all labels match."""
        results = [
            TestCaseResult(
                index=1, expected="pass", actual="pass", passed=True,
                expected_text_label="safe", actual_text_label="safe",
                expected_image_label="无", actual_image_label="无",
            ),
            TestCaseResult(
                index=2, expected="reject", actual="reject", passed=True,
                expected_text_label="spam", actual_text_label="spam",
                expected_image_label="pornography", actual_image_label="pornography",
            ),
        ]
        report = calculate_metrics(results)
        assert report["text_label_accuracy"] == 1.0
        assert report["image_label_accuracy"] == 1.0

    def test_label_accuracy_partial_match(self):
        """Label accuracy should reflect partial matches correctly."""
        results = [
            TestCaseResult(
                index=1, expected="pass", actual="pass", passed=True,
                expected_text_label="safe", actual_text_label="safe",
                expected_image_label="无", actual_image_label="无",
            ),
            TestCaseResult(
                index=2, expected="reject", actual="reject", passed=False,
                expected_text_label="spam", actual_text_label="toxic",
                expected_image_label="pornography", actual_image_label="gambling",
            ),
        ]
        report = calculate_metrics(results)
        assert report["text_label_accuracy"] == pytest.approx(0.5, abs=0.001)
        assert report["image_label_accuracy"] == pytest.approx(0.5, abs=0.001)

    def test_label_accuracy_no_expected_labels(self):
        """When no expected labels are provided, label accuracy should be 0.0."""
        results = [
            TestCaseResult(index=1, expected="pass", actual="pass", passed=True),
            TestCaseResult(index=2, expected="reject", actual="reject", passed=True),
        ]
        report = calculate_metrics(results)
        assert report["text_label_accuracy"] == 0.0
        assert report["image_label_accuracy"] == 0.0

    def test_empty_results_includes_label_accuracy(self):
        """Empty results should include label accuracy fields at 0.0."""
        report = calculate_metrics([])
        assert "text_label_accuracy" in report
        assert "image_label_accuracy" in report
        assert report["text_label_accuracy"] == 0.0
        assert report["image_label_accuracy"] == 0.0

    def test_error_cases_include_label_fields(self):
        """Error cases should include expected/actual label fields."""
        results = [
            TestCaseResult(
                index=1, expected="pass", actual="reject", passed=False,
                expected_text_label="safe", actual_text_label="spam",
                expected_image_label="无", actual_image_label="pornography",
            ),
        ]
        report = calculate_metrics(results)
        assert len(report["error_cases"]) == 1
        ec = report["error_cases"][0]
        assert ec["expected_text_label"] == "safe"
        assert ec["actual_text_label"] == "spam"
        assert ec["expected_image_label"] == "无"
        assert ec["actual_image_label"] == "pornography"


# ---------------------------------------------------------------------------
# Tests — Lambda handler
# ---------------------------------------------------------------------------


class TestLambdaHandler:
    """Validates: SQS Lambda integration."""

    def test_lambda_handler_processes_sqs_event(self):
        record_id = str(uuid.uuid4())
        suite_id = str(uuid.uuid4())

        event = {
            "Records": [
                {
                    "body": json.dumps(
                        {
                            "test_record_id": record_id,
                            "test_suite_id": suite_id,
                            "rule_ids": [],
                        }
                    )
                }
            ]
        }

        mock_record = _make_test_record_mock()
        mock_suite = _make_test_suite_mock(total_cases=1)

        mock_db = MagicMock()
        mock_db.get.side_effect = lambda model, uid: (
            mock_record if model.__name__ == "TestRecord" else mock_suite
        )
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_exec = MagicMock()
        mock_exec.scalars.return_value = mock_scalars
        mock_exec.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_exec

        with patch(
            "backend.app.services.batch_test_worker.SessionLocal",
            return_value=mock_db,
        ), patch(
            "backend.app.services.batch_test_worker.ModelInvoker"
        ) as MockInvoker:
            mock_invoker_instance = MockInvoker.return_value
            mock_invoker_instance.invoke_with_fallback = AsyncMock(
                return_value=_make_model_response("pass")
            )

            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert mock_record.status == "completed"

    def test_lambda_handler_empty_records(self):
        event = {"Records": []}

        with patch(
            "backend.app.services.batch_test_worker.SessionLocal",
            return_value=MagicMock(),
        ):
            result = lambda_handler(event, None)

        assert result["statusCode"] == 200
