"""Rule engine for template parsing and prompt assembly."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models.label_definitions import LabelDefinition
from backend.app.models.rules import Rule

logger = logging.getLogger(__name__)

# Regex pattern matching {{variable}} placeholders (allows optional whitespace inside braces)
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass
class ModerationContent:
    """Content to be moderated."""

    text: str | None = None
    image_url: str | None = None


class RuleEngine:
    """Core engine for rule loading, template rendering, and prompt assembly."""

    def get_active_rules(
        self, db: Session, business_type: str | None = None
    ) -> list[Rule]:
        """Load enabled rules from PostgreSQL, optionally filtered by *business_type*.

        Rules are returned sorted by priority ascending (lower number = higher
        priority), matching Requirements 3.4, 3.5, 4.3.
        """
        stmt = select(Rule).where(Rule.enabled.is_(True))
        if business_type is not None:
            stmt = stmt.where(Rule.business_type == business_type)
        stmt = stmt.order_by(Rule.priority.asc())
        return list(db.scalars(stmt).all())

    def get_enabled_labels(
        self, db: Session, label_type: str | None = None
    ) -> list[LabelDefinition]:
        """Load enabled label definitions from PostgreSQL, sorted by sort_order.

        Optionally filtered by *label_type* (text / image).
        """
        stmt = select(LabelDefinition).where(LabelDefinition.enabled.is_(True))
        if label_type is not None:
            stmt = stmt.where(LabelDefinition.label_type == label_type)
        stmt = stmt.order_by(LabelDefinition.sort_order.asc())
        return list(db.scalars(stmt).all())

    def assemble_prompt(
        self,
        rules: list[Rule],
        content: ModerationContent,
        labels: list[LabelDefinition] | None = None,
    ) -> str:
        """Assemble the final prompt from rule fragments and moderation content.

        Each rule's ``prompt_template`` is rendered via :meth:`render_template`
        using the rule's ``variables`` dict.  Rendered fragments are
        concatenated in the order they appear (callers should pass rules
        already sorted by priority ascending).

        When *labels* are provided, a label classification instruction section
        is appended listing all enabled text and image labels with their
        display_name.

        The moderation content text is appended at the end so the AI model
        knows what to evaluate.

        **Property 7**: fragment order in the output matches priority order.
        **Property 9**: prompt contains all enabled labels, no disabled ones.
        """
        fragments: list[str] = []
        for rule in rules:
            variables = rule.variables if rule.variables else {}
            rendered = self.render_template(rule.prompt_template, variables)
            if rendered.strip():
                fragments.append(rendered)

        prompt_parts = fragments.copy()

        # Dynamic label classification instruction
        if labels:
            text_labels = [lb for lb in labels if lb.label_type == "text"]
            image_labels = [lb for lb in labels if lb.label_type == "image"]

            label_instruction_parts = [
                "你必须在响应 JSON 中包含以下字段：",
            ]

            if text_labels:
                text_keys = ", ".join(lb.label_key for lb in text_labels)
                label_instruction_parts.append(
                    f"- text_label: 文案分类标签，取值范围 [{text_keys}]"
                )

            if image_labels:
                image_keys = ", ".join(lb.label_key for lb in image_labels)
                label_instruction_parts.append(
                    f"- image_label: 图片分类标签，取值范围 [{image_keys}]"
                )

            label_instruction_parts.append("- language: 审核内容的语言代码（ISO 639-1，如 zh、en、fr）")

            # Add label descriptions
            label_instruction_parts.append("")
            label_instruction_parts.append("各标签含义：")
            for lb in labels:
                desc = f" - {lb.description}" if lb.description else ""
                label_instruction_parts.append(f"- {lb.label_key}: {lb.display_name}{desc}")

            prompt_parts.append("\n".join(label_instruction_parts))

        if content.text:
            prompt_parts.append(f"待审核内容：{content.text}")
        if content.image_url:
            prompt_parts.append(f"待审核图片：{content.image_url}")

        return "\n".join(prompt_parts)

    def render_template(self, template: str, variables: dict[str, str]) -> str:
        """Replace ``{{variable}}`` placeholders in *template* with values from *variables*.

        * Every ``{{name}}`` token is replaced by ``variables[name]`` when the
          key exists.
        * If a placeholder references a variable **not** present in *variables*,
          it is replaced with an empty string and a warning is logged.
        * After replacement the result is guaranteed to contain **no**
          ``{{...}}`` patterns (roundtrip consistency – Property 6).
        """

        def _replacer(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in variables:
                return variables[var_name]
            logger.warning(
                "Template variable '%s' is not defined; replacing with empty string",
                var_name,
            )
            return ""

        return _PLACEHOLDER_RE.sub(_replacer, template)
