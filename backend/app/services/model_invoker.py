"""AI model invoker wrapping Amazon Bedrock calls with fallback support."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import boto3

logger = logging.getLogger(__name__)


@dataclass
class ModelSettings:
    """Plain config object decoupled from the ORM ModelConfig model.

    Carries only the fields needed by :class:`ModelInvoker` so that callers
    can construct it from any source (DB row, dict, env vars, …).
    """

    model_id: str
    temperature: float = 0.0
    max_tokens: int = 1024
    fallback_model_id: str | None = None
    fallback_temperature: float = 0.0
    fallback_max_tokens: int = 1024
    fallback_result: str = "review"


@dataclass
class ModelResponse:
    """Structured response returned by :class:`ModelInvoker`."""

    result: str  # pass / reject / review / flag
    text_label: str = "safe"  # safe/spam/toxic/hate_speech/privacy_leak/political/self_harm/illegal_trade/misleading
    image_label: str = "无"  # 无/pornography/gambling/drugs/violence/terrorism/qr_code_spam/contact_info/ad_overlay/minor_exploitation
    confidence: float = 0.0
    matched_rules: list[dict] = field(default_factory=list)
    raw_response: str = ""
    degraded: bool = False
    model_id: str = ""
    language: str = ""


class ModelInvoker:
    """Invoke Amazon Bedrock models with automatic fallback.

    The class uses the Bedrock **converse** API which natively supports
    both text and image content blocks.

    Parameters
    ----------
    bedrock_client:
        A ``boto3`` ``bedrock-runtime`` client.  Accepting it as a
        constructor argument makes the class easy to test with mocks /
        stubs.
    """

    def __init__(self, bedrock_client=None):
        self._client = bedrock_client

    @property
    def client(self):
        """Lazily initialise the Bedrock runtime client."""
        if self._client is None:
            self._client = boto3.client("bedrock-runtime")
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def invoke(
        self,
        prompt: str,
        images: list[bytes] | None,
        settings: ModelSettings,
        *,
        model_id_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> ModelResponse:
        """Call a single Bedrock model via the *converse* API.

        Raises on any Bedrock / network error so that
        :meth:`invoke_with_fallback` can catch and retry.
        """
        model_id = model_id_override or settings.model_id
        temperature = temperature_override if temperature_override is not None else settings.temperature
        max_tokens = max_tokens_override if max_tokens_override is not None else settings.max_tokens

        content_blocks: list[dict] = [{"text": prompt}]
        if images:
            for idx, img_bytes in enumerate(images):
                content_blocks.append(
                    {
                        "image": {
                            "format": "png",
                            "source": {"bytes": img_bytes},
                        }
                    }
                )

        messages = [{"role": "user", "content": content_blocks}]

        inference_config: dict = {"maxTokens": max_tokens}
        if temperature > 0:
            inference_config["temperature"] = temperature

        logger.info("Invoking Bedrock model %s", model_id)
        response = self.client.converse(
            modelId=model_id,
            messages=messages,
            inferenceConfig=inference_config,
        )

        raw_text = self._extract_text(response)
        parsed = self._parse_response(raw_text)

        return ModelResponse(
            result=parsed.get("result", "review"),
            text_label=parsed.get("text_label", "safe"),
            image_label=parsed.get("image_label", "无"),
            confidence=float(parsed.get("confidence", 0.0)),
            matched_rules=parsed.get("matched_rules", []),
            raw_response=raw_text,
            degraded=False,
            model_id=model_id,
            language=parsed.get("language", ""),
        )

    async def invoke_with_fallback(
        self,
        prompt: str,
        images: list[bytes] | None,
        settings: ModelSettings,
    ) -> ModelResponse:
        """Try primary model, then fallback, then return a safe default.

        Degradation chain (Requirements 1.6, 7.4):
        1. Primary model → success → return result
        2. Primary fails → fallback model (if configured) → return result
           with ``degraded=True``
        3. Fallback also fails (or not configured) → return default result
           with ``degraded=True``
        """
        # --- 1. Try primary model ---
        try:
            return await self.invoke(prompt, images, settings)
        except Exception:
            logger.exception(
                "Primary model %s failed; attempting fallback", settings.model_id
            )

        # --- 2. Try fallback model ---
        if settings.fallback_model_id:
            try:
                resp = await self.invoke(
                    prompt,
                    images,
                    settings,
                    model_id_override=settings.fallback_model_id,
                    temperature_override=settings.fallback_temperature,
                    max_tokens_override=settings.fallback_max_tokens,
                )
                resp.degraded = True
                return resp
            except Exception:
                logger.exception(
                    "Fallback model %s also failed; returning default result",
                    settings.fallback_model_id,
                )

        # --- 3. Default safe result ---
        default_result = settings.fallback_result or "review"
        logger.warning(
            "All models failed. Returning default result: %s", default_result
        )
        return ModelResponse(
            result=default_result,
            confidence=0.0,
            matched_rules=[],
            raw_response="",
            degraded=True,
            model_id="",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(response: dict) -> str:
        """Pull the assistant's text out of a Bedrock *converse* response."""
        try:
            output = response["output"]["message"]["content"]
            parts = [block["text"] for block in output if "text" in block]
            return "\n".join(parts)
        except (KeyError, IndexError, TypeError):
            logger.warning("Could not extract text from Bedrock response")
            return ""

    @staticmethod
    def _parse_response(raw_text: str) -> dict:
        """Best-effort JSON parse of the model's text output.

        The model is prompted to return JSON with ``result``,
        ``confidence``, and ``matched_rules`` keys.  If parsing fails we
        return sensible defaults so the caller always gets a usable dict.
        """
        if not raw_text.strip():
            return {}

        # Try to find a JSON object in the response (models sometimes wrap
        # JSON in markdown code fences).
        text = raw_text.strip()
        if "```" in text:
            # Extract content between first pair of triple-backtick fences
            parts = text.split("```")
            for part in parts[1:]:
                candidate = part.strip()
                if candidate.startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    text = candidate
                    break

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse model response as JSON: %s", raw_text[:200])
            return {"result": "review", "confidence": 0.0, "matched_rules": []}
