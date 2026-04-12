"""Batch test worker — SQS-triggered Lambda that executes test suites.

Receives SQS messages containing test_record_id, test_suite_id, and rule_ids,
then processes each test case by invoking the moderation pipeline and comparing
results against expected outcomes.

Validates: Requirements 6.3, 6.7
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.database import SessionLocal
from backend.app.models.model_config import ModelConfig
from backend.app.models.rules import Rule
from backend.app.models.test_records import TestRecord
from backend.app.services.model_invoker import ModelInvoker, ModelResponse, ModelSettings
from backend.app.services.rule_engine import ModerationContent, RuleEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single test case parsed from the Excel test suite."""

    index: int
    text: str | None = None
    image_url: str | None = None
    expected_result: str = "pass"
    expected_text_label: str | None = None
    expected_image_label: str | None = None
    business_type: str | None = None
    notes: str | None = None


@dataclass
class TestCaseResult:
    """Result of executing a single test case."""

    index: int
    expected: str
    actual: str
    expected_text_label: str | None = None
    expected_image_label: str | None = None
    actual_text_label: str = "safe"
    actual_image_label: str = "无"
    confidence: float = 0.0
    matched_rules: list[dict] = field(default_factory=list)
    passed: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# BatchTestWorker
# ---------------------------------------------------------------------------

class BatchTestWorker:
    """Process batch test suites triggered via SQS.

    For each test case the worker:
    1. Loads rules by rule_ids
    2. Assembles a prompt with RuleEngine
    3. Invokes the AI model with ModelInvoker
    4. Compares actual vs expected result
    5. Updates progress in test_records
    6. On single-case failure, logs the error and continues (Req 6.7)
    """

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        model_invoker: ModelInvoker | None = None,
    ) -> None:
        self.rule_engine = rule_engine or RuleEngine()
        self.model_invoker = model_invoker or ModelInvoker()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_test_suite(
        self,
        test_record_id: str,
        test_suite_id: str,
        rule_ids: list[str],
        db: Session,
    ) -> None:
        """Execute all test cases for a test record.

        Updates the test_record row with progress, status, and final report.
        Single-case failures are recorded but do not abort the run.
        """
        # Mark record as running
        record = db.get(TestRecord, uuid.UUID(test_record_id))
        if record is None:
            logger.error("TestRecord %s not found — aborting", test_record_id)
            return

        record.status = "running"
        record.started_at = datetime.now(timezone.utc)
        db.commit()

        # Load rules
        rules = self._load_rules(db, rule_ids)

        # Load model settings
        model_settings = self._load_model_settings(db)

        # Load test cases (simulated from test suite)
        test_cases = self._load_test_cases(test_suite_id, db)

        record.progress_total = len(test_cases)
        db.commit()

        # Execute each test case
        results: list[TestCaseResult] = []
        for case in test_cases:
            result = await self._execute_single_case(case, rules, model_settings)
            results.append(result)

            # Update progress
            record.progress_current = len(results)
            db.commit()

        # Generate report via calculate_metrics (Task 6.2 placeholder)
        report = calculate_metrics(results)

        # Finalise record
        record.status = "completed"
        record.completed_at = datetime.now(timezone.utc)
        record.report = report
        db.commit()

        logger.info(
            "Test record %s completed: %d/%d cases, accuracy=%.2f",
            test_record_id,
            len(results),
            record.progress_total,
            report.get("accuracy", 0),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_rules(self, db: Session, rule_ids: list[str]) -> list[Rule]:
        """Load rules by their IDs, sorted by priority ascending."""
        uuids = [uuid.UUID(rid) for rid in rule_ids]
        stmt = (
            select(Rule)
            .where(Rule.id.in_(uuids))
            .order_by(Rule.priority.asc())
        )
        return list(db.scalars(stmt).all())

    def _load_model_settings(self, db: Session) -> ModelSettings:
        """Build a ModelSettings from the current DB model configuration."""
        primary = db.execute(
            select(ModelConfig).where(ModelConfig.is_primary.is_(True))
        ).scalar_one_or_none()

        fallback = db.execute(
            select(ModelConfig).where(ModelConfig.is_fallback.is_(True))
        ).scalar_one_or_none()

        if primary is None:
            # Sensible default when no config exists
            return ModelSettings(model_id="anthropic.claude-3-haiku-20240307-v1:0")

        return ModelSettings(
            model_id=primary.model_id,
            temperature=primary.temperature,
            max_tokens=primary.max_tokens,
            fallback_model_id=fallback.model_id if fallback else None,
            fallback_temperature=fallback.temperature if fallback else 0.0,
            fallback_max_tokens=fallback.max_tokens if fallback else 1024,
            fallback_result=primary.fallback_result or "review",
        )

    def _load_test_cases(
        self, test_suite_id: str, db: Session
    ) -> list[TestCase]:
        """Load test cases for a test suite.

        In production this would parse the Excel file stored in S3.
        For now we return a simulated list based on the suite's total_cases.
        """
        from backend.app.models.test_suites import TestSuite

        suite = db.get(TestSuite, uuid.UUID(test_suite_id))
        if suite is None:
            logger.warning("TestSuite %s not found", test_suite_id)
            return []

        # Simulate test cases — real implementation would parse S3 Excel
        cases: list[TestCase] = []
        for i in range(1, suite.total_cases + 1):
            cases.append(
                TestCase(
                    index=i,
                    text=f"模拟测试文本 {i}",
                    expected_result="pass",
                    business_type="商品评论",
                )
            )
        return cases

    async def _execute_single_case(
        self,
        case: TestCase,
        rules: list[Rule],
        model_settings: ModelSettings,
    ) -> TestCaseResult:
        """Run the moderation pipeline for one test case.

        On failure, the error is captured and the case is marked as failed
        rather than raising — ensuring the overall batch continues (Req 6.7).
        """
        try:
            content = ModerationContent(text=case.text, image_url=case.image_url)
            prompt = self.rule_engine.assemble_prompt(rules, content)

            response: ModelResponse = await self.model_invoker.invoke_with_fallback(
                prompt=prompt,
                images=None,
                settings=model_settings,
            )

            result_matched = response.result == case.expected_result
            text_label_matched = (
                case.expected_text_label is None
                or response.text_label == case.expected_text_label
            )
            image_label_matched = (
                case.expected_image_label is None
                or response.image_label == case.expected_image_label
            )
            passed = result_matched and text_label_matched and image_label_matched

            return TestCaseResult(
                index=case.index,
                expected=case.expected_result,
                actual=response.result,
                expected_text_label=case.expected_text_label,
                expected_image_label=case.expected_image_label,
                actual_text_label=response.text_label,
                actual_image_label=response.image_label,
                confidence=response.confidence,
                matched_rules=response.matched_rules,
                passed=passed,
            )
        except Exception as exc:
            logger.exception(
                "Test case %d failed with error: %s", case.index, exc
            )
            return TestCaseResult(
                index=case.index,
                expected=case.expected_result,
                actual="error",
                expected_text_label=case.expected_text_label,
                expected_image_label=case.expected_image_label,
                actual_text_label="",
                actual_image_label="",
                passed=False,
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Metrics calculation
# Validates: Requirements 6.4
# ---------------------------------------------------------------------------

def calculate_metrics(results: list[TestCaseResult]) -> dict:
    """Compute accuracy, precision, recall, F1, confusion matrix from test results.

    Binary classification: reject = positive, non-reject = negative.
    - TP: expected == "reject" AND actual == "reject"
    - FP: expected != "reject" AND actual == "reject"
    - TN: expected != "reject" AND actual != "reject"
    - FN: expected == "reject" AND actual != "reject"

    Also computes text_label_accuracy and image_label_accuracy when
    expected labels are provided in the test cases.

    Property 5 invariant: TP + FP + TN + FN == total

    Validates: Requirements 6.4, 13.6
    """
    total = len(results)
    if total == 0:
        return {
            "accuracy": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1_score": 0.0,
            "text_label_accuracy": 0.0,
            "image_label_accuracy": 0.0,
            "confusion_matrix": {"TP": 0, "FP": 0, "TN": 0, "FN": 0},
            "error_cases": [],
            "rule_hit_distribution": {},
        }

    # Binary confusion matrix (reject = positive, non-reject = negative)
    tp = sum(1 for r in results if r.expected == "reject" and r.actual == "reject")
    fp = sum(1 for r in results if r.expected != "reject" and r.actual == "reject")
    tn = sum(1 for r in results if r.expected != "reject" and r.actual != "reject")
    fn = sum(1 for r in results if r.expected == "reject" and r.actual != "reject")

    # Accuracy from confusion matrix to ensure consistency
    accuracy = (tp + tn) / total

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    # Error cases: where expected != actual (including label mismatches)
    error_cases = []
    for r in results:
        if r.expected != r.actual:
            error_cases.append({
                "index": r.index,
                "expected": r.expected,
                "actual": r.actual,
                "expected_text_label": r.expected_text_label,
                "actual_text_label": r.actual_text_label,
                "expected_image_label": r.expected_image_label,
                "actual_image_label": r.actual_image_label,
                "error": r.error,
            })

    # Rule hit distribution: count of each rule_name across all results
    rule_hits: dict[str, int] = {}
    for r in results:
        for mr in r.matched_rules:
            rule_name = mr.get("rule_name", mr.get("rule_id", "unknown"))
            rule_hits[rule_name] = rule_hits.get(rule_name, 0) + 1

    # Label accuracy: compare actual labels against expected labels
    # We use a convention: if the TestCase had expected labels, the caller
    # should have stored them on the result via a wrapper. For now we compute
    # based on the passed flag which already accounts for label matching.
    text_label_match = 0
    text_label_total = 0
    image_label_match = 0
    image_label_total = 0

    for r in results:
        # text_label accuracy: count cases where actual matches expected
        if r.expected_text_label is not None:
            text_label_total += 1
            if r.actual_text_label == r.expected_text_label:
                text_label_match += 1

        if r.expected_image_label is not None:
            image_label_total += 1
            if r.actual_image_label == r.expected_image_label:
                image_label_match += 1

    text_label_accuracy = (text_label_match / text_label_total) if text_label_total > 0 else 0.0
    image_label_accuracy = (image_label_match / image_label_total) if image_label_total > 0 else 0.0

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "text_label_accuracy": round(text_label_accuracy, 4),
        "image_label_accuracy": round(image_label_accuracy, 4),
        "confusion_matrix": {"TP": tp, "FP": fp, "TN": tn, "FN": fn},
        "error_cases": error_cases,
        "rule_hit_distribution": rule_hits,
    }


# ---------------------------------------------------------------------------
# Lambda handler (SQS event source)
# ---------------------------------------------------------------------------

async def _handle_sqs_event(event: dict) -> dict:
    """Process SQS records from a Lambda event.

    Each SQS record body is expected to be JSON with:
      - test_record_id: str
      - test_suite_id: str
      - rule_ids: list[str]
    """
    worker = BatchTestWorker()
    db = SessionLocal()

    try:
        for sqs_record in event.get("Records", []):
            body = json.loads(sqs_record["body"])
            test_record_id = body["test_record_id"]
            test_suite_id = body["test_suite_id"]
            rule_ids = body["rule_ids"]

            logger.info(
                "Processing SQS message: test_record=%s suite=%s",
                test_record_id,
                test_suite_id,
            )

            await worker.process_test_suite(
                test_record_id=test_record_id,
                test_suite_id=test_suite_id,
                rule_ids=rule_ids,
                db=db,
            )
    except Exception:
        logger.exception("Unhandled error in batch test worker")
        raise
    finally:
        db.close()

    return {"statusCode": 200, "body": "OK"}


def lambda_handler(event: dict, context) -> dict:
    """Mangum-compatible Lambda entry point for SQS batch test worker."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(_handle_sqs_event(event))
