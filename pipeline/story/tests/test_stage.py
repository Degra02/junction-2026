"""The stage as the worker calls it, with a stand-in for the model module (no download)."""

import sys
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pipeline.common import progress
from pipeline.common.contracts import StoryPatch
from pipeline.story.tests.test_assign import Embedder, analysis, item


@pytest.fixture
def fake_model(monkeypatch):
    """`pipeline.story.model` replaced before `stage` imports it; stage re-imported fresh."""
    fake = types.ModuleType("pipeline.story.model")
    fake.embed = Embedder()
    monkeypatch.setitem(sys.modules, "pipeline.story.model", fake)
    monkeypatch.delitem(sys.modules, "pipeline.story.stage", raising=False)
    import pipeline.story as story

    monkeypatch.setattr(story, "model", fake, raising=False)
    return fake


def test_run_is_resolved_lazily(fake_model):
    import pipeline.story as story

    patch = story.run(analysis(item(1, 0.95), item(2, 0.5)))
    assert [a.in_story for a in patch.assignments] == [True, False]
    with pytest.raises(AttributeError):
        story.not_a_stage  # noqa: B018


def test_progress_note(fake_model, monkeypatch):
    import pipeline.story as story

    notes: list[str] = []
    monkeypatch.setattr(progress, "report", notes.append)
    story.run(analysis(item(1, 0.9), item(2, 0.9)))
    assert notes == ["Comparing 2 reports with the article"]


def test_through_the_worker_endpoint(fake_model, monkeypatch):
    from worker import stages
    from worker.app import app

    monkeypatch.setattr(stages, "_loaded", {})  # import the stage again, with the fake model
    body = analysis(item(1, 0.95), item(2, 0.5)).model_dump(mode="json")
    response = TestClient(app).post("/stages/story", json=body)
    assert response.status_code == 200, response.text
    patch = StoryPatch.model_validate(response.json())
    assert [(a.context_id, a.in_story) for a in patch.assignments] == [
        ("ctx1", True),
        ("ctx2", False),
    ]
    assert isinstance(fake_model.embed.calls[0], list)
    assert np.isfinite([a.similarity for a in patch.assignments]).all()


def test_no_context_means_no_note_and_no_model_call(fake_model, monkeypatch):
    import pipeline.story as story

    notes: list[str] = []
    monkeypatch.setattr(progress, "report", notes.append)
    assert story.run(analysis()).assignments == []
    assert notes == [] and fake_model.embed.calls == []
