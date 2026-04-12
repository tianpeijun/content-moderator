"""Unit tests for RuleEngine."""

import logging
import uuid

import pytest

from backend.app.models.rules import Rule
from backend.app.services.rule_engine import ModerationContent, RuleEngine


@pytest.fixture
def engine():
    return RuleEngine()


def _make_rule(
    *,
    priority: int = 0,
    prompt_template: str = "rule fragment",
    variables: dict | None = None,
    enabled: bool = True,
    business_type: str | None = None,
    name: str = "test-rule",
    rule_type: str = "text",
    action: str = "reject",
) -> Rule:
    """Create a Rule ORM instance without touching the database."""
    rule = Rule(
        id=uuid.uuid4(),
        name=name,
        type=rule_type,
        business_type=business_type,
        prompt_template=prompt_template,
        variables=variables,
        action=action,
        priority=priority,
        enabled=enabled,
    )
    return rule


class TestRenderTemplate:
    """Tests for the render_template method."""

    def test_single_variable_replacement(self, engine: RuleEngine):
        result = engine.render_template("Hello {{name}}!", {"name": "World"})
        assert result == "Hello World!"

    def test_multiple_variables(self, engine: RuleEngine):
        template = "{{greeting}}, {{name}}! Welcome to {{place}}."
        variables = {"greeting": "Hi", "name": "Alice", "place": "Wonderland"}
        result = engine.render_template(template, variables)
        assert result == "Hi, Alice! Welcome to Wonderland."

    def test_repeated_variable(self, engine: RuleEngine):
        result = engine.render_template(
            "{{x}} and {{x}} again", {"x": "val"}
        )
        assert result == "val and val again"

    def test_no_placeholders(self, engine: RuleEngine):
        result = engine.render_template("plain text", {"a": "b"})
        assert result == "plain text"

    def test_empty_template(self, engine: RuleEngine):
        result = engine.render_template("", {"a": "b"})
        assert result == ""

    def test_empty_variables(self, engine: RuleEngine):
        """Undefined variables are replaced with empty string."""
        result = engine.render_template("Hello {{name}}!", {})
        assert result == "Hello !"

    def test_undefined_variable_logs_warning(self, engine: RuleEngine, caplog):
        with caplog.at_level(logging.WARNING):
            engine.render_template("{{missing}}", {})
        assert "missing" in caplog.text

    def test_whitespace_inside_braces(self, engine: RuleEngine):
        result = engine.render_template("{{ name }}", {"name": "Bob"})
        assert result == "Bob"

    def test_no_leftover_placeholders(self, engine: RuleEngine):
        """Property 6: result must not contain any {{...}} patterns."""
        template = "{{a}} and {{b}} and {{c}}"
        variables = {"a": "1", "b": "2"}  # c is missing
        result = engine.render_template(template, variables)
        assert "{{" not in result
        assert "}}" not in result

    def test_variable_value_with_special_chars(self, engine: RuleEngine):
        result = engine.render_template(
            "Check: {{items}}", {"items": "品牌A, 品牌B, 品牌C"}
        )
        assert result == "Check: 品牌A, 品牌B, 品牌C"

    def test_adjacent_placeholders(self, engine: RuleEngine):
        result = engine.render_template("{{a}}{{b}}", {"a": "X", "b": "Y"})
        assert result == "XY"


class TestAssemblePrompt:
    """Tests for the assemble_prompt method."""

    def test_single_rule_fragment(self, engine: RuleEngine):
        rules = [_make_rule(priority=1, prompt_template="检查违禁词")]
        content = ModerationContent(text="好产品")
        result = engine.assemble_prompt(rules, content)
        assert "检查违禁词" in result
        assert "待审核内容：好产品" in result

    def test_fragments_ordered_by_priority(self, engine: RuleEngine):
        """Property 7: fragments appear in priority-ascending order."""
        rules = [
            _make_rule(priority=1, prompt_template="FIRST"),
            _make_rule(priority=5, prompt_template="SECOND"),
            _make_rule(priority=10, prompt_template="THIRD"),
        ]
        content = ModerationContent(text="test")
        result = engine.assemble_prompt(rules, content)
        idx_first = result.index("FIRST")
        idx_second = result.index("SECOND")
        idx_third = result.index("THIRD")
        assert idx_first < idx_second < idx_third

    def test_variables_rendered_in_fragments(self, engine: RuleEngine):
        rules = [
            _make_rule(
                priority=1,
                prompt_template="禁止提及：{{brands}}",
                variables={"brands": "品牌A, 品牌B"},
            )
        ]
        content = ModerationContent(text="评论")
        result = engine.assemble_prompt(rules, content)
        assert "禁止提及：品牌A, 品牌B" in result

    def test_empty_rules_list(self, engine: RuleEngine):
        content = ModerationContent(text="hello")
        result = engine.assemble_prompt([], content)
        assert "待审核内容：hello" in result

    def test_content_with_image_url(self, engine: RuleEngine):
        rules = [_make_rule(priority=1, prompt_template="检查图片")]
        content = ModerationContent(image_url="https://example.com/img.jpg")
        result = engine.assemble_prompt(rules, content)
        assert "检查图片" in result
        assert "待审核图片：https://example.com/img.jpg" in result

    def test_content_with_text_and_image(self, engine: RuleEngine):
        rules = [_make_rule(priority=1, prompt_template="综合审核")]
        content = ModerationContent(text="好评", image_url="s3://bucket/img.png")
        result = engine.assemble_prompt(rules, content)
        assert "综合审核" in result
        assert "待审核内容：好评" in result
        assert "待审核图片：s3://bucket/img.png" in result

    def test_blank_template_skipped(self, engine: RuleEngine):
        """Rules whose rendered template is blank should be skipped."""
        rules = [
            _make_rule(priority=1, prompt_template="KEEP"),
            _make_rule(priority=2, prompt_template="   "),
        ]
        content = ModerationContent(text="x")
        result = engine.assemble_prompt(rules, content)
        assert "KEEP" in result
        # The blank fragment should not produce an empty line between KEEP and content
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 2  # "KEEP" + "待审核内容：x"

    def test_none_variables_treated_as_empty_dict(self, engine: RuleEngine):
        rules = [_make_rule(priority=1, prompt_template="no vars", variables=None)]
        content = ModerationContent(text="t")
        result = engine.assemble_prompt(rules, content)
        assert "no vars" in result
