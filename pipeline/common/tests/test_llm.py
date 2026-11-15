"""The LLM client against a local OpenAI-compatible endpoint: what is sent, what comes back."""

import asyncio
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import BaseModel

from pipeline.common import llm
from pipeline.common.errors import StageError


class Verdict(BaseModel):
    label: str
    confidence: float


class Endpoint:
    """A chat-completions endpoint that records requests and answers with `reply`."""

    def __init__(self) -> None:
        self.reply = ""
        self.requests: list[dict] = []
        self.authorization: list[str | None] = []
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["content-length"])
                endpoint.requests.append(json.loads(self.rfile.read(length)))
                endpoint.authorization.append(self.headers["authorization"])
                message = {"role": "assistant", "content": endpoint.reply}
                body = json.dumps(
                    {
                        "id": "chatcmpl-1",
                        "object": "chat.completion",
                        "created": 0,
                        "model": "test-model",
                        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
                    }
                ).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Iterator[Endpoint]:
    server = Endpoint()
    monkeypatch.setenv("LLM_BASE_URL", server.url)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    yield server
    server.server.shutdown()


def test_ask_json_sends_the_schema_and_validates_the_answer(endpoint: Endpoint) -> None:
    endpoint.reply = '{"label": "loaded language", "confidence": 0.8}'
    verdict = llm.ask_json(Verdict, system="Classify the text.", user="They are traitors.")

    assert verdict == Verdict(label="loaded language", confidence=0.8)
    request = endpoint.requests[0]
    assert request["model"] == "test-model"
    assert request["response_format"] == {"type": "json_object"}
    system, user = request["messages"]
    assert system["content"].startswith("Classify the text.")
    assert '"confidence"' in system["content"], "the JSON Schema is part of the instructions"
    assert user == {"role": "user", "content": "They are traitors."}
    assert endpoint.authorization == ["Bearer sk-test"]


def test_an_answer_that_is_not_the_schema_raises(endpoint: Endpoint) -> None:
    endpoint.reply = '{"label": "loaded language"}'
    with pytest.raises(llm.LLMOutputError):
        llm.ask_json(Verdict, system="Classify.", user="text")


def test_async_calls_use_the_same_endpoint(endpoint: Endpoint) -> None:
    endpoint.reply = "Three plain sentences."
    answer = asyncio.run(llm.ask_text_async(system="Explain.", user="evidence"))
    assert answer == "Three plain sentences."
    assert "response_format" not in endpoint.requests[0]


def test_missing_configuration_is_a_plain_stage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    with pytest.raises(StageError, match="not configured"):
        llm.ask_text(system="s", user="u")


def test_ask_json_supports_per_call_model_and_data_uri_image(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_RATER_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_RATER_API_KEY", raising=False)
    endpoint.reply = '{"label": "straw man", "confidence": 0.9}'
    data_uri = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    verdict = asyncio.run(
        llm.ask_json_async(
            Verdict,
            system="Rate rhetoric.",
            user="AFFORDABILITY",
            model="custom-rater-v1",
            image=data_uri,
        )
    )
    assert verdict == Verdict(label="straw man", confidence=0.9)
    request = endpoint.requests[-1]
    assert request["model"] == "custom-rater-v1"
    assert request["messages"][1] == {
        "role": "user",
        "content": [
            {"type": "text", "text": "AFFORDABILITY"},
            {"type": "image_url", "image_url": {"url": data_uri}},
        ],
    }

    # Remote URLs are rejected so signal stages never trigger implicit network fetches.
    with pytest.raises(StageError, match="Unsupported image input"):
        llm.ask_json(Verdict, system="s", user="u", image="https://example.com/meme.png")


def test_gemini_override_routes_to_gemini_openai_endpoint_when_key_set(
    endpoint: Endpoint, monkeypatch: pytest.MonkeyPatch
) -> None:
    gemini_server = Endpoint()
    try:
        gemini_server.reply = '{"label": "distraction", "confidence": 1.0}'
        monkeypatch.setattr(llm, "GEMINI_OPENAI_BASE_URL", gemini_server.url)
        monkeypatch.setenv("GEMINI_API_KEY", "gk-test")
        verdict = llm.ask_json(Verdict, system="Rate.", user="Caption", model="gemini-4-hydrogen")
        assert verdict == Verdict(label="distraction", confidence=1.0)
        assert gemini_server.requests[0]["model"] == "gemini-4-hydrogen"
        assert gemini_server.authorization == ["Bearer gk-test"]
        assert endpoint.requests == []
    finally:
        gemini_server.server.shutdown()
