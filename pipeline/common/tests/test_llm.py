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
