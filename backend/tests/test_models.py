"""Tests for SQLAlchemy data models."""

import uuid
from datetime import datetime

from sqlalchemy import inspect

from backend.app.core.database import Base
from backend.app.models import (
    ModelConfig,
    ModerationLog,
    Rule,
    RuleVersion,
    TestRecord,
    TestSuite,
)


class TestRuleModel:
    def test_table_name(self):
        assert Rule.__tablename__ == "rules"

    def test_columns_exist(self):
        cols = {c.name for c in inspect(Rule).columns}
        expected = {
            "id", "name", "type", "business_type", "prompt_template",
            "variables", "action", "priority", "enabled",
            "created_at", "updated_at",
        }
        assert expected.issubset(cols)

    def test_primary_key(self):
        pk_cols = [c.name for c in inspect(Rule).columns if c.primary_key]
        assert pk_cols == ["id"]

    def test_id_is_uuid(self):
        col = inspect(Rule).columns["id"]
        assert "UUID" in str(col.type)


class TestRuleVersionModel:
    def test_table_name(self):
        assert RuleVersion.__tablename__ == "rule_versions"

    def test_columns_exist(self):
        cols = {c.name for c in inspect(RuleVersion).columns}
        expected = {
            "id", "rule_id", "version", "snapshot",
            "modified_by", "modified_at", "change_summary",
        }
        assert expected.issubset(cols)

    def test_foreign_key_to_rules(self):
        col = inspect(RuleVersion).columns["rule_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "rules.id" in fk_targets


class TestModelConfigModel:
    def test_table_name(self):
        assert ModelConfig.__tablename__ == "model_config"

    def test_columns_exist(self):
        cols = {c.name for c in inspect(ModelConfig).columns}
        expected = {
            "id", "model_id", "model_name", "temperature", "max_tokens",
            "is_primary", "is_fallback", "fallback_result",
            "cost_per_1k_input", "cost_per_1k_output", "updated_at",
        }
        assert expected.issubset(cols)


class TestTestSuiteModel:
    def test_table_name(self):
        assert TestSuite.__tablename__ == "test_suites"

    def test_columns_exist(self):
        cols = {c.name for c in inspect(TestSuite).columns}
        expected = {"id", "name", "file_key", "total_cases", "created_at"}
        assert expected.issubset(cols)


class TestTestRecordModel:
    def test_table_name(self):
        assert TestRecord.__tablename__ == "test_records"

    def test_columns_exist(self):
        cols = {c.name for c in inspect(TestRecord).columns}
        expected = {
            "id", "test_suite_id", "rule_ids", "model_config_snapshot",
            "status", "progress_current", "progress_total",
            "report", "started_at", "completed_at",
        }
        assert expected.issubset(cols)

    def test_foreign_key_to_test_suites(self):
        col = inspect(TestRecord).columns["test_suite_id"]
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "test_suites.id" in fk_targets


class TestModerationLogModel:
    def test_table_name(self):
        assert ModerationLog.__tablename__ == "moderation_logs"

    def test_columns_exist(self):
        cols = {c.name for c in inspect(ModerationLog).columns}
        expected = {
            "id", "task_id", "status", "input_text", "input_image_url",
            "business_type", "final_prompt", "model_response", "result",
            "confidence", "matched_rules", "processing_time_ms",
            "degraded", "model_id", "created_at",
        }
        assert expected.issubset(cols)

    def test_task_id_unique(self):
        col = inspect(ModerationLog).columns["task_id"]
        assert col.unique is True

    def test_indexes_defined(self):
        indexes = {idx.name for idx in inspect(ModerationLog).local_table.indexes}
        assert "idx_logs_result_created" in indexes
        assert "idx_logs_business_type_created" in indexes
        assert "idx_logs_task_id" in indexes

    def test_idx_logs_task_id_is_unique(self):
        for idx in inspect(ModerationLog).local_table.indexes:
            if idx.name == "idx_logs_task_id":
                assert idx.unique is True
                break


class TestAllModelsRegistered:
    def test_all_tables_in_metadata(self):
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "rules", "rule_versions", "model_config",
            "test_suites", "test_records", "moderation_logs",
        }
        assert expected.issubset(table_names)
