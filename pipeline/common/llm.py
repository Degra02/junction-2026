"""The pipeline's one LLM client (AGENTS.md "Model calls").

Any OpenAI-compatible endpoint, chosen by `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`; the
deployment uses the Hostinger AI Router (D12). Stages never build a client of their own, so
switching provider stays a configuration change.

    class Understanding(BaseModel):
        summary: str
        claims: list[str]

    result = await llm.ask_json_async(Understanding, system=INSTRUCTIONS, user=article_text)

Content under analysis is data, never instructions: it goes in `user`; `system` holds only our
own prompt. Use the `_async` functions from `async def` stages and the plain ones from `def`
stages (those run in a worker thread).
"""

import json
import logging
import os
from functools import cache
from typing import Any

from openai import AsyncOpenAI, OpenAI
from pydantic import BaseModel, ValidationError

from pipeline.common.errors import StageError

log = logging.getLogger(__name__)

# One call must fit well inside the API's per-stage timeout (120 s), retries included.
_TIMEOUT_SECONDS = 45.0
_MAX_RETRIES = 1
GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class LLMOutputError(Exception):
    """The model's answer was not the JSON object that was asked for."""


def ask_text(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str:
    """The model's answer to `user` under the instructions in `system`."""
    base_url, api_key, chosen_model = _settings_for(model)
    request = _request(chosen_model, system, user, max_tokens, temperature)
    completion = _client(base_url, api_key).chat.completions.create(**request)
    return completion.choices[0].message.content or ""


async def ask_text_async(
    *,
    system: str,
    user: str,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
) -> str:
    """`ask_text` for `async def` stages."""
    base_url, api_key, chosen_model = _settings_for(model)
    request = _request(chosen_model, system, user, max_tokens, temperature)
    completion = await _async_client(base_url, api_key).chat.completions.create(**request)
    return completion.choices[0].message.content or ""


def ask_json[T: BaseModel](
    schema: type[T],
    *,
    system: str,
    user: str,
    model: str | None = None,
    image: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> T:
    """The model's answer parsed and validated as `schema`.

    The JSON Schema of `schema` is appended to `system`. `image`, when given, must be a
    `data:image/...;base64,...` URI (never a remote URL). Raises `LLMOutputError` when the
    answer does not validate.
    """
    base_url, api_key, chosen_model = _settings_for(model)
    request = _request(
        chosen_model, _with_schema(system, schema), user, max_tokens, temperature, image=image
    )
    request["response_format"] = {"type": "json_object"}
    completion = _client(base_url, api_key).chat.completions.create(**request)
    return _parse(schema, completion.choices[0].message.content)


async def ask_json_async[T: BaseModel](
    schema: type[T],
    *,
    system: str,
    user: str,
    model: str | None = None,
    image: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.0,
) -> T:
    """`ask_json` for `async def` stages."""
    base_url, api_key, chosen_model = _settings_for(model)
    request = _request(
        chosen_model, _with_schema(system, schema), user, max_tokens, temperature, image=image
    )
    request["response_format"] = {"type": "json_object"}
    completion = await _async_client(base_url, api_key).chat.completions.create(**request)
    return _parse(schema, completion.choices[0].message.content)


def _settings() -> tuple[str, str, str]:
    names = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
    values = [os.environ.get(name, "").strip() for name in names]
    missing = [name for name, value in zip(names, values, strict=True) if not value]
    if missing:
        log.error("LLM call without %s set", ", ".join(missing))
        raise StageError("The language model is not configured on this server")
    return values[0], values[1], values[2]


def _settings_for(model: str | None = None) -> tuple[str, str, str]:
    chosen = (model or "").strip()
    if not chosen:
        return _settings()
    rater_base = os.environ.get("LLM_RATER_BASE_URL", "").strip()
    rater_key = os.environ.get("LLM_RATER_API_KEY", "").strip()
    if rater_base and rater_key:
        return rater_base, rater_key, chosen
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    default_model = os.environ.get("LLM_MODEL", "").strip()
    if chosen.startswith("gemini-") and gemini_key and chosen != default_model:
        return rater_base or GEMINI_OPENAI_BASE_URL, gemini_key, chosen
    base_url, api_key, fallback_model = _settings()
    # Hostinger AI Router serves `gemini-3.1-flash-lite`, not `gemini-4-hydrogen`: when no
    # direct `GEMINI_API_KEY` or `LLM_RATER_BASE_URL` is set, fall back to `LLM_MODEL`.
    if chosen == "gemini-4-hydrogen" and not rater_base and "router.hostinger.com" in base_url:
        return base_url, rater_key or api_key, fallback_model
    return rater_base or base_url, rater_key or api_key, chosen


@cache
def _client(base_url: str, api_key: str) -> OpenAI:
    return OpenAI(
        base_url=base_url, api_key=api_key, timeout=_TIMEOUT_SECONDS, max_retries=_MAX_RETRIES
    )


@cache
def _async_client(base_url: str, api_key: str) -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=base_url, api_key=api_key, timeout=_TIMEOUT_SECONDS, max_retries=_MAX_RETRIES
    )


def _request(
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    *,
    image: str | None = None,
) -> dict[str, Any]:
    user_content: str | list[dict[str, Any]]
    if image is not None:
        if not image.startswith("data:image/") or ";base64," not in image:
            raise StageError("Unsupported image input")
        user_content = [
            {"type": "text", "text": user},
            {"type": "image_url", "image_url": {"url": image}},
        ]
    else:
        user_content = user
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }


def _with_schema(system: str, schema: type[BaseModel]) -> str:
    return (
        f"{system}\n\nAnswer with one JSON object that matches this JSON Schema, and nothing "
        f"else:\n{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
    )


def _parse[T: BaseModel](schema: type[T], content: str | None) -> T:
    try:
        return schema.model_validate_json(content or "")
    except ValidationError as e:
        raise LLMOutputError(f"the model did not return a valid {schema.__name__}") from e
