"""Worker endpoint tests: the stage contract the Rust API relies on."""

import threading
from collections.abc import Iterator

import pytest
import uvicorn
from fastapi.testclient import TestClient

from pipeline.common.contracts import Analysis, StageName
from worker import __main__ as worker_main
from worker import stages
from worker.app import app
from worker.stages import StageSpec
from worker.tests import fake_stages

FAKE = "worker.tests.fake_stages"
ANALYSIS_ID = "01933b6e-0000-7000-8000-000000000000"


def analysis_json(text: str = "Big lies everywhere") -> dict:
    return {
        "id": ANALYSIS_ID,
        "schema_version": 1,
        "pipeline_version": "test",
        "created_at": "2026-11-14T00:00:00Z",
        "updated_at": "2026-11-14T00:00:00Z",
        "status": "running",
        "queue_position": None,
        "error": None,
        "steps": [],
        "input": {"kind": "text", "value": text},
        "language": None,
        "document": None,
        "topic": None,
        "claims": [],
        "queries": [],
        "context": [],
        "sources": [],
        "evidence": [],
        "scores": None,
        "explanation": None,
    }


# Stage -> (module, function) used by the tests instead of the real pipeline packages.
OVERRIDES = {
    StageName.extract: (FAKE, "extract"),
    StageName.signals_single: (FAKE, "signals_async"),
    StageName.signals_coordinated: (FAKE, "as_dict"),
    StageName.score: (FAKE, "raises"),
    StageName.explain: (FAKE, "wrong_shape"),
    StageName.story: ("worker.tests.broken_stage", "run"),
    StageName.understand: ("pipeline.no_such_stage", "run"),
    StageName.retrieve: (FAKE, "no_such_function"),
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    table = {
        name: StageSpec(module, function, stages.STAGES[name].patch)
        for name, (module, function) in OVERRIDES.items()
    }
    monkeypatch.setattr(stages, "STAGES", table)
    monkeypatch.setattr(stages, "_loaded", {})
    fake_stages.BROKEN_IMPORTS.clear()
    with TestClient(app) as c:
        yield c


def use(stage: StageName, function: str) -> None:
    """Points `stage` at another fake for the current test."""
    stages.STAGES[stage] = StageSpec(FAKE, function, stages.STAGES[stage].patch)


def test_the_fixture_is_a_valid_analysis() -> None:
    Analysis.model_validate(analysis_json())


def test_sync_stage_returns_its_patch(client: TestClient) -> None:
    r = client.post("/stages/extract", json=analysis_json("Hello"))
    assert r.status_code == 200
    assert r.json() == {
        "document": {
            "url": None,
            "outlet": None,
            "published_at": None,
            "title": None,
            "author": None,
            "paragraphs": ["Hello"],
            "outbound_links": [],
            "tracking_ids": [],
        },
        "language": None,
    }


def test_async_stage_and_tagged_source_refs(client: TestClient) -> None:
    r = client.post("/stages/signals_single", json=analysis_json())
    assert r.status_code == 200
    ref = r.json()["evidence"][0]["source_refs"][0]
    assert ref == {"kind": "document", "span": {"paragraph": 0, "start": 0, "end": 3}}


def test_plain_dict_results_are_validated_into_the_patch(client: TestClient) -> None:
    r = client.post("/stages/signals_coordinated", json=analysis_json())
    assert r.status_code == 200
    assert r.json() == {"evidence": []}


@pytest.mark.parametrize("stage", ["understand", "retrieve"])
def test_missing_module_or_function_is_501(client: TestClient, stage: str) -> None:
    r = client.post(f"/stages/{stage}", json=analysis_json())
    assert r.status_code == 501
    assert r.json()["error"] == "not_implemented"


def test_missing_dependency_inside_a_stage_is_500_not_501(client: TestClient) -> None:
    r = client.post("/stages/story", json=analysis_json())
    assert r.status_code == 500
    assert r.json()["error"] == "import_failed"
    assert "definitely_not_installed_dependency" in r.json()["message"]


def test_a_stage_that_fails_to_import_is_imported_once(client: TestClient) -> None:
    # Startup, two health checks and two stage calls: a module that loads models before it
    # fails must not load them again each time.
    for _ in range(2):
        client.get("/health")
        client.post("/stages/story", json=analysis_json())
    assert len(fake_stages.BROKEN_IMPORTS) == 1


def test_exception_text_never_leaves_the_worker(client: TestClient) -> None:
    r = client.post("/stages/score", json=analysis_json())
    assert r.status_code == 500
    assert r.json()["error"] == "stage_failed"
    assert "RuntimeError" in r.json()["message"]
    assert "SECRET-KEY" not in r.text


def test_stage_error_messages_are_passed_on_as_written(client: TestClient) -> None:
    use(StageName.score, "gives_up")
    r = client.post("/stages/score", json=analysis_json())
    assert r.status_code == 422
    assert r.json() == {"error": "stage_failed", "message": "The text is too short to analyse"}


def test_invalid_patches_are_rejected_without_echoing_their_values(client: TestClient) -> None:
    r = client.post("/stages/explain", json=analysis_json())
    assert r.status_code == 500
    assert r.json()["error"] == "invalid_patch"
    assert "unexpected" in r.json()["message"], "names the offending field"
    assert "SECRET-VALUE" not in r.text


def test_progress_notes_are_readable_while_the_stage_runs(client: TestClient) -> None:
    use(StageName.signals_coordinated, "reports_progress")
    fake_stages.STARTED.clear()
    fake_stages.RELEASE.clear()
    call = threading.Thread(
        target=client.post, args=("/stages/signals_coordinated",), kwargs={"json": analysis_json()}
    )
    call.start()
    try:
        assert fake_stages.STARTED.wait(timeout=5)
        running = client.get(f"/progress/{ANALYSIS_ID}").json()
        other = client.get("/progress/01933b6e-0000-7000-8000-00000000ffff").json()
    finally:
        fake_stages.RELEASE.set()
        call.join(timeout=5)

    assert running == {"signals_coordinated": "3 sources so far"}
    assert other == {}
    assert client.get(f"/progress/{ANALYSIS_ID}").json() == {}, "cleared when the stage ends"


def test_invalid_analysis_body_is_422(client: TestClient) -> None:
    body = analysis_json()
    del body["input"]
    assert client.post("/stages/extract", json=body).status_code == 422


def test_unknown_stage_is_422(client: TestClient) -> None:
    assert client.post("/stages/nope", json=analysis_json()).status_code == 422


def test_health_lists_every_stage_and_why_one_failed_to_load(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    loaded = {s["name"]: (s["implemented"], s["error"]) for s in r.json()["stages"]}
    assert loaded == {
        "extract": (True, None),
        "understand": (False, None),
        "retrieve": (False, None),
        "story": (False, "ModuleNotFoundError: definitely_not_installed_dependency"),
        "signals_single": (True, None),
        "signals_coordinated": (True, None),
        "score": (True, None),
        "explain": (True, None),
    }


def test_entrypoint_ignores_kubernetes_worker_service_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Kubernetes injects WORKER_PORT=tcp://<ip>:8001 for a Service named `worker`.
    monkeypatch.setenv("WORKER_HOST", "10.96.0.10")
    monkeypatch.setenv("WORKER_PORT", "tcp://10.96.0.10:8001")
    monkeypatch.delenv("STAGE_WORKER_HOST", raising=False)
    monkeypatch.delenv("STAGE_WORKER_PORT", raising=False)
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        uvicorn, "run", lambda app_path, **kw: calls.append({"app": app_path, **kw})
    )

    worker_main.main()
    monkeypatch.setenv("STAGE_WORKER_HOST", "0.0.0.0")
    monkeypatch.setenv("STAGE_WORKER_PORT", "9001")
    worker_main.main()

    assert calls == [
        {"app": "worker.app:app", "host": "127.0.0.1", "port": 8001, "workers": 1},
        {"app": "worker.app:app", "host": "0.0.0.0", "port": 9001, "workers": 1},
    ]
