"""Unit tests for ModelInvoker."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from backend.app.services.model_invoker import (
    ModelInvoker,
    ModelResponse,
    ModelSettings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bedrock_converse_response(body: dict) -> dict:
    """Build a minimal Bedrock *converse* API response dict."""
    return {
        "output": {
            "message": {
                "content": [{"text": json.dumps(body)}],
            }
        }
    }


def _make_settings(**overrides) -> ModelSettings:
    defaults = dict(
        model_id="anthropic.claude-3-haiku",
        temperature=0.0,
        max_tokens=1024,
        fallback_model_id=None,
        fallback_temperature=0.0,
        fallback_max_tokens=512,
        fallback_result="review",
    )
    defaults.update(overrides)
    return ModelSettings(**defaults)


def _make_client(side_effect=None, return_value=None) -> MagicMock:
    client = MagicMock()
    if side_effect is not None:
        client.converse.side_effect = side_effect
    elif return_value is not None:
        client.converse.return_value = return_value
    return client


# ---------------------------------------------------------------------------
# ModelResponse dataclass
# ---------------------------------------------------------------------------

class TestModelResponse:
    def test_defaults(self):
        r = ModelResponse(result="pass", confidence=0.9)
        assert r.matched_rules == []
        assert r.raw_response == ""
        assert r.degraded is False
        assert r.model_id == ""

    def test_all_fields(self):
        r = ModelResponse(
            result="reject",
            confidence=0.85,
            matched_rules=[{"rule_id": "1"}],
            raw_response="raw",
            degraded=True,
            model_id="m1",
        )
        assert r.result == "reject"
        assert r.confidence == 0.85
        assert r.degraded is True


# ---------------------------------------------------------------------------
# ModelSettings dataclass
# ---------------------------------------------------------------------------

class TestModelSettings:
    def test_defaults(self):
        s = ModelSettings(model_id="m1")
        assert s.temperature == 0.0
        assert s.max_tokens == 1024
        assert s.fallback_result == "review"

    def test_custom(self):
        s = _make_settings(fallback_model_id="m2", fallback_result="flag")
        assert s.fallback_model_id == "m2"
        assert s.fallback_result == "flag"


# ---------------------------------------------------------------------------
# invoke() – single model call
# ---------------------------------------------------------------------------

class TestInvoke:
    @pytest.mark.asyncio
    async def test_successful_text_only(self):
        body = {"result": "pass", "confidence": 0.95, "matched_rules": []}
        client = _make_client(return_value=_bedrock_converse_response(body))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        resp = await invoker.invoke("check this", None, settings)

        assert resp.result == "pass"
        assert resp.confidence == 0.95
        assert resp.degraded is False
        assert resp.model_id == settings.model_id
        client.converse.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_with_images(self):
        body = {"result": "reject", "confidence": 0.8, "matched_rules": [{"rule_id": "r1"}]}
        client = _make_client(return_value=_bedrock_converse_response(body))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        resp = await invoker.invoke("check", [b"\x89PNG"], settings)

        assert resp.result == "reject"
        assert len(resp.matched_rules) == 1
        # Verify image block was sent
        call_kwargs = client.converse.call_args
        content = call_kwargs.kwargs["messages"][0]["content"]
        assert any("image" in block for block in content)

    @pytest.mark.asyncio
    async def test_model_id_override(self):
        body = {"result": "pass", "confidence": 0.9, "matched_rules": []}
        client = _make_client(return_value=_bedrock_converse_response(body))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        resp = await invoker.invoke(
            "prompt", None, settings, model_id_override="other-model"
        )

        assert resp.model_id == "other-model"
        call_kwargs = client.converse.call_args
        assert call_kwargs.kwargs["modelId"] == "other-model"

    @pytest.mark.asyncio
    async def test_invoke_raises_on_error(self):
        client = _make_client(side_effect=Exception("Bedrock down"))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        with pytest.raises(Exception, match="Bedrock down"):
            await invoker.invoke("prompt", None, settings)

    @pytest.mark.asyncio
    async def test_unparseable_response_defaults_to_review(self):
        """When the model returns non-JSON, result should default to review."""
        raw_resp = {
            "output": {
                "message": {
                    "content": [{"text": "I cannot parse this as JSON"}],
                }
            }
        }
        client = _make_client(return_value=raw_resp)
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        resp = await invoker.invoke("prompt", None, settings)

        assert resp.result == "review"
        assert resp.confidence == 0.0

    @pytest.mark.asyncio
    async def test_json_in_code_fence(self):
        """Model wraps JSON in markdown code fences."""
        inner = json.dumps({"result": "flag", "confidence": 0.7, "matched_rules": []})
        raw_resp = {
            "output": {
                "message": {
                    "content": [{"text": f"```json\n{inner}\n```"}],
                }
            }
        }
        client = _make_client(return_value=raw_resp)
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        resp = await invoker.invoke("prompt", None, settings)

        assert resp.result == "flag"
        assert resp.confidence == 0.7


# ---------------------------------------------------------------------------
# invoke_with_fallback() – degradation chain
# ---------------------------------------------------------------------------

class TestInvokeWithFallback:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self):
        """Happy path: primary model works, no degradation."""
        body = {"result": "pass", "confidence": 0.99, "matched_rules": []}
        client = _make_client(return_value=_bedrock_converse_response(body))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings()

        resp = await invoker.invoke_with_fallback("prompt", None, settings)

        assert resp.result == "pass"
        assert resp.degraded is False
        assert client.converse.call_count == 1

    @pytest.mark.asyncio
    async def test_primary_fails_fallback_succeeds(self):
        """Primary fails, fallback model returns result with degraded=True."""
        fallback_body = {"result": "review", "confidence": 0.6, "matched_rules": []}
        call_count = 0

        def _side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("primary down")
            return _bedrock_converse_response(fallback_body)

        client = _make_client(side_effect=_side_effect)
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings(
            fallback_model_id="anthropic.claude-3-sonnet",
        )

        resp = await invoker.invoke_with_fallback("prompt", None, settings)

        assert resp.result == "review"
        assert resp.degraded is True
        assert resp.model_id == "anthropic.claude-3-sonnet"
        assert client.converse.call_count == 2

    @pytest.mark.asyncio
    async def test_both_fail_returns_default(self):
        """Both primary and fallback fail → default result with degraded=True."""
        client = _make_client(side_effect=Exception("all down"))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings(
            fallback_model_id="fallback-model",
            fallback_result="review",
        )

        resp = await invoker.invoke_with_fallback("prompt", None, settings)

        assert resp.result == "review"
        assert resp.degraded is True
        assert resp.confidence == 0.0
        assert resp.model_id == ""

    @pytest.mark.asyncio
    async def test_no_fallback_configured_returns_default(self):
        """Primary fails, no fallback configured → default result."""
        client = _make_client(side_effect=Exception("down"))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings(fallback_model_id=None, fallback_result="flag")

        resp = await invoker.invoke_with_fallback("prompt", None, settings)

        assert resp.result == "flag"
        assert resp.degraded is True

    @pytest.mark.asyncio
    async def test_custom_fallback_result(self):
        """Default result uses the configured fallback_result value."""
        client = _make_client(side_effect=Exception("down"))
        invoker = ModelInvoker(bedrock_client=client)
        settings = _make_settings(fallback_model_id=None, fallback_result="reject")

        resp = await invoker.invoke_with_fallback("prompt", None, settings)

        assert resp.result == "reject"
        assert resp.degraded is True


# ---------------------------------------------------------------------------
# _parse_response / _extract_text edge cases
# ---------------------------------------------------------------------------

class TestParseHelpers:
    def test_extract_text_empty_response(self):
        assert ModelInvoker._extract_text({}) == ""

    def test_extract_text_multiple_blocks(self):
        resp = {
            "output": {
                "message": {
                    "content": [
                        {"text": "part1"},
                        {"text": "part2"},
                    ]
                }
            }
        }
        assert ModelInvoker._extract_text(resp) == "part1\npart2"

    def test_parse_response_empty(self):
        assert ModelInvoker._parse_response("") == {}
        assert ModelInvoker._parse_response("   ") == {}

    def test_parse_response_valid_json(self):
        data = {"result": "pass", "confidence": 0.9}
        assert ModelInvoker._parse_response(json.dumps(data)) == data

    def test_parse_response_invalid_json(self):
        result = ModelInvoker._parse_response("not json at all")
        assert result["result"] == "review"
