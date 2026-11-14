//! `fixtures/analysis.json` is the example record stages are tested against
//! (`pipeline.common.fixtures`). It must be exactly what the API would have stored: here every
//! stage's part of it goes through `Analysis::apply` again and nothing may be dropped or changed.

use junction_contracts::{
    Analysis, ContextItem, Dimension, ExplainPatch, ExtractPatch, RetrievePatch, ScorePatch,
    SignalsPatch, StagePatch, StoryAssignment, StoryPatch, UnderstandPatch,
};

const FIXTURE: &str = include_str!("../fixtures/analysis.json");

#[test]
fn the_example_analysis_survives_its_own_validation() {
    let expected: Analysis = serde_json::from_str(FIXTURE).expect("fixture matches the contract");
    let before_story = |c: &ContextItem| ContextItem {
        similarity: None,
        in_story: None,
        story_reason: None,
        ..c.clone()
    };
    let assignment = |c: &ContextItem| StoryAssignment {
        context_id: c.id.clone(),
        similarity: c.similarity.expect("story ran"),
        in_story: c.in_story.expect("story ran"),
        reason: c.story_reason.clone(),
    };
    let signals = |dimension| {
        let evidence = expected.evidence.iter();
        let evidence = evidence.filter(|e| e.family.dimension() == dimension);
        StagePatch::Signals(
            dimension,
            SignalsPatch {
                evidence: evidence.cloned().collect(),
            },
        )
    };
    let patches = [
        StagePatch::Extract(ExtractPatch {
            document: expected.document.clone().expect("document"),
            language: expected.language.clone(),
        }),
        StagePatch::Understand(UnderstandPatch {
            topic: expected.topic.clone().expect("topic"),
            claims: expected.claims.clone(),
            queries: expected.queries.clone(),
        }),
        StagePatch::Retrieve(RetrievePatch {
            context: expected.context.iter().map(before_story).collect(),
            sources: expected.sources.clone(),
            detail: None,
        }),
        StagePatch::Story(StoryPatch {
            assignments: expected.context.iter().map(assignment).collect(),
        }),
        signals(Dimension::Single),
        signals(Dimension::Coordinated),
        StagePatch::Score(ScorePatch {
            scores: expected.scores.clone().expect("scores"),
        }),
        StagePatch::Explain(ExplainPatch {
            explanation: expected.explanation.clone().expect("explanation"),
        }),
    ];

    let mut replayed = Analysis::new(
        expected.id,
        expected.input.clone(),
        expected.pipeline_version.clone(),
        expected.created_at,
    );
    for patch in patches {
        let report = replayed.apply(patch).expect("patch accepted");
        assert_eq!(report.dropped, [] as [String; 0]);
    }
    // Status, steps and timestamps are written by the orchestrator, not by patches.
    let replayed = Analysis {
        status: expected.status,
        steps: expected.steps.clone(),
        updated_at: expected.updated_at,
        ..replayed
    };
    assert_eq!(replayed, expected);
}
