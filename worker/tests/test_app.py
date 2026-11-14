"""Worker endpoint tests: the stage contract the Rust API relies on."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from pipeline.common.contracts import Analysis, StageName
from worker import stages
from worker.app import app
from worker.stages import StageSpec

FAKE = "worker.tests.fake_stages"


def analysis_json(text: str = "Big lies everywhere") -> dict:
    return {
        "id": "01933b6e-0000-7000-8000-000000000000",
        "schema_version": 1,
        "pipeline_version": "test",
        "created_at": "2026-11-14T00:00:00Z",
        "updated_at": "2026-11-14T00:00:00Z",
        "status": "running",
        "error": None,
        "steps": [],
        "input": {"kind": "text", "value": text},
        "language": None,
        "document": None,
        "topic": None,
        "claims": [],
        "queries": [],
        "context": [],
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
    with TestClient(app) as c:
        yield c


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


def test_stage_exception_is_500_with_the_message(client: TestClient) -> None:
    r = client.post("/stages/score", json=analysis_json())
    assert r.status_code == 500
    assert r.json() == {"error": "stage_failed", "message": "RuntimeError: model crashed"}


def test_patch_with_unknown_fields_is_rejected(client: TestClient) -> None:
    r = client.post("/stages/explain", json=analysis_json())
    assert r.status_code == 500
    assert r.json()["error"] == "invalid_patch"


def test_invalid_analysis_body_is_422(client: TestClient) -> None:
    body = analysis_json()
    del body["input"]
    assert client.post("/stages/extract", json=body).status_code == 422


def test_unknown_stage_is_422(client: TestClient) -> None:
    assert client.post("/stages/nope", json=analysis_json()).status_code == 422


def test_health_lists_every_stage(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    implemented = {s["name"]: s["implemented"] for s in r.json()["stages"]}
    assert implemented == {
        "extract": True,
        "understand": False,
        "retrieve": False,
        "story": False,
        "signals_single": True,
        "signals_coordinated": True,
        "score": True,
        "explain": True,
    }
