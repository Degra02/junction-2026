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


class LLMOutputError(Exception):
    """The model's answer was not the JSON object that was asked for."""


def ask_text(*, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.0) -> str:
    """The model's answer to `user` under the instructions in `system`."""
    base_url, api_key, model = _settings()
    request = _request(model, system, user, max_tokens, temperature)
    completion = _client(base_url, api_key).chat.completions.create(**request)
    return completion.choices[0].message.content or ""


async def ask_text_async(
    *, system: str, user: str, max_tokens: int = 1024, temperature: float = 0.0
) -> str:
    """`ask_text` for `async def` stages."""
    base_url, api_key, model = _settings()
    request = _request(model, system, user, max_tokens, temperature)
    completion = await _async_client(base_url, api_key).chat.completions.create(**request)
    return completion.choices[0].message.content or ""


def ask_json[T: BaseModel](
    schema: type[T], *, system: str, user: str, max_tokens: int = 2048, temperature: float = 0.0
) -> T:
    """The model's answer parsed and validated as `schema`.

    The JSON Schema of `schema` is appended to `system`. Raises `LLMOutputError` when the
    answer does not validate.
    """
    base_url, api_key, model = _settings()
    request = _request(model, _with_schema(system, schema), user, max_tokens, temperature)
    request["response_format"] = {"type": "json_object"}
    completion = _client(base_url, api_key).chat.completions.create(**request)
    return _parse(schema, completion.choices[0].message.content)


async def ask_json_async[T: BaseModel](
    schema: type[T], *, system: str, user: str, max_tokens: int = 2048, temperature: float = 0.0
) -> T:
    """`ask_json` for `async def` stages."""
    base_url, api_key, model = _settings()
    request = _request(model, _with_schema(system, schema), user, max_tokens, temperature)
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
    model: str, system: str, user: str, max_tokens: int, temperature: float
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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
