//! Validation and merge of stage patches into the [`Analysis`] record.
//!
//! Two kinds of problems are distinguished:
//! - a broken contract (duplicate IDs, wrong dimension, invalid score) rejects the whole patch,
//!   so the step is marked failed and the bug is visible;
//! - an unverifiable item (claim not verbatim, dangling source, reason without evidence) is
//!   dropped and reported, as the plan requires for LLM output.

use std::collections::HashSet;

use crate::analysis::{Analysis, Claim, Dimension, Document, Evidence, Score, SourceRef, Span};
use crate::stage::{StageName, StagePatch};

/// Shortest quoted passage checked as a quotation; shorter ones are terms or scare quotes.
const MIN_QUOTE_CHARS: usize = 12;

/// What was dropped while applying a patch, for the step's `detail`.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct ApplyReport {
    pub dropped: Vec<String>,
    /// Progress note forwarded from the stage.
    pub detail: Option<String>,
}

impl ApplyReport {
    /// One line for the UI, e.g. "14 sources; dropped 2: claim cl3 is not verbatim, …".
    #[must_use]
    pub fn summary(&self) -> Option<String> {
        let dropped = (!self.dropped.is_empty()).then(|| {
            format!(
                "dropped {}: {}",
                self.dropped.len(),
                self.dropped.join("; ")
            )
        });
        match (self.detail.clone(), dropped) {
            (Some(d), Some(x)) => Some(format!("{d}; {x}")),
            (d, x) => d.or(x),
        }
    }
}

#[derive(Debug, Clone, PartialEq, thiserror::Error)]
pub enum ApplyError {
    #[error("the document has no text")]
    EmptyDocument,
    #[error("this stage needs the document, but extract produced none")]
    MissingDocument,
    #[error("duplicate id `{0}`")]
    DuplicateId(String),
    #[error("unknown context id `{0}`")]
    UnknownContext(String),
    #[error("evidence `{id}` has a family outside the {expected:?} dimension")]
    WrongDimension { id: String, expected: Dimension },
    #[error("invalid score for the {dimension:?} dimension: {problem}")]
    InvalidScore {
        dimension: Dimension,
        problem: String,
    },
}

impl Analysis {
    /// Validates `patch` against the current record and merges it.
    pub fn apply(&mut self, patch: StagePatch) -> Result<ApplyReport, ApplyError> {
        let mut report = ApplyReport::default();
        match patch {
            StagePatch::Extract(p) => {
                if p.document.paragraphs.iter().all(|t| t.trim().is_empty()) {
                    return Err(ApplyError::EmptyDocument);
                }
                self.document = Some(p.document);
                self.language = p.language;
            }
            StagePatch::Understand(p) => {
                let doc = self.document.as_ref().ok_or(ApplyError::MissingDocument)?;
                unique_ids(p.claims.iter().map(|c| c.id.as_str()))?;
                let (kept, dropped): (Vec<Claim>, Vec<Claim>) = p
                    .claims
                    .into_iter()
                    .partition(|c| span_text(doc, c.span).is_some_and(|t| t == c.text));
                report.dropped.extend(
                    dropped
                        .iter()
                        .map(|c| format!("claim {} is not verbatim in the text", c.id)),
                );
                self.topic = Some(p.topic);
                self.claims = kept;
                self.queries = p.queries;
            }
            StagePatch::Retrieve(p) => {
                unique_ids(p.context.iter().map(|c| c.id.as_str()))?;
                unique_ids(p.sources.iter().map(|s| s.domain.as_str()))?;
                self.context = p.context;
                self.sources = p.sources;
                report.detail = p.detail;
            }
            StagePatch::Story(p) => {
                for a in &p.assignments {
                    if !self.context.iter().any(|c| c.id == a.context_id) {
                        return Err(ApplyError::UnknownContext(a.context_id.clone()));
                    }
                }
                for a in p.assignments {
                    if let Some(c) = self.context.iter_mut().find(|c| c.id == a.context_id) {
                        c.similarity = Some(a.similarity);
                        c.in_story = Some(a.in_story);
                        c.story_reason = a.reason;
                    }
                }
                let kept = self
                    .context
                    .iter()
                    .filter(|c| c.in_story == Some(true))
                    .count();
                report.detail = Some(format!(
                    "{kept} of {} items in the story",
                    self.context.len()
                ));
            }
            StagePatch::Signals(dimension, p) => {
                self.append_evidence(dimension, p.evidence, &mut report)?;
            }
            StagePatch::Score(p) => {
                self.check_score(Dimension::Single, &p.scores.single)?;
                self.check_score(Dimension::Coordinated, &p.scores.coordinated)?;
                self.scores = Some(p.scores);
            }
            StagePatch::Explain(p) => {
                let mut explanation = p.explanation;
                let known: HashSet<&str> = self.evidence.iter().map(|e| e.id.as_str()).collect();
                let sources = self.quotable();
                let verbatim = |text: &str| {
                    quotations(text)
                        .iter()
                        .all(|q| sources.iter().any(|s| s.contains(q)))
                };

                let before = explanation.reasons.len();
                explanation.reasons.retain(|r| {
                    !r.evidence_ids.is_empty()
                        && r.evidence_ids.iter().all(|id| known.contains(id.as_str()))
                });
                let uncited = before - explanation.reasons.len();
                explanation.reasons.retain(|r| verbatim(&r.text));
                let misquoting = before - uncited - explanation.reasons.len();
                if uncited > 0 {
                    report
                        .dropped
                        .push(format!("{uncited} reasons without valid evidence"));
                }
                if misquoting > 0 {
                    report.dropped.push(format!(
                        "{misquoting} reasons with a quotation that is not verbatim"
                    ));
                }
                if !verbatim(&explanation.summary) {
                    explanation.summary.clear();
                    report
                        .dropped
                        .push("the summary: it had a quotation that is not verbatim".into());
                }
                self.explanation = Some(explanation);
            }
        }
        Ok(report)
    }

    /// Removes everything `stage` produced, so that it can run again on this record.
    pub fn clear_output(&mut self, stage: StageName) {
        match stage {
            StageName::Extract => {
                self.document = None;
                self.language = None;
            }
            StageName::Understand => {
                self.topic = None;
                self.claims.clear();
                self.queries.clear();
            }
            StageName::Retrieve => {
                self.context.clear();
                self.sources.clear();
            }
            StageName::Story => {
                for c in &mut self.context {
                    c.similarity = None;
                    c.in_story = None;
                    c.story_reason = None;
                }
            }
            StageName::SignalsSingle => self
                .evidence
                .retain(|e| e.family.dimension() != Dimension::Single),
            StageName::SignalsCoordinated => self
                .evidence
                .retain(|e| e.family.dimension() != Dimension::Coordinated),
            StageName::Score => self.scores = None,
            StageName::Explain => self.explanation = None,
        }
    }

    fn append_evidence(
        &mut self,
        dimension: Dimension,
        evidence: Vec<Evidence>,
        report: &mut ApplyReport,
    ) -> Result<(), ApplyError> {
        if let Some(e) = evidence.iter().find(|e| e.family.dimension() != dimension) {
            return Err(ApplyError::WrongDimension {
                id: e.id.clone(),
                expected: dimension,
            });
        }
        unique_ids(self.evidence.iter().chain(&evidence).map(|e| e.id.as_str()))?;
        for e in evidence {
            match self.unverifiable(&e) {
                Some(why) => report.dropped.push(format!("evidence {}: {why}", e.id)),
                None => self.evidence.push(e),
            }
        }
        Ok(())
    }

    fn check_score(&self, dimension: Dimension, score: &Score) -> Result<(), ApplyError> {
        let invalid = |problem: String| ApplyError::InvalidScore { dimension, problem };
        match (score.abstained, score.confidence, &score.reason) {
            (true, None, Some(_)) => {}
            (true, _, _) => {
                return Err(invalid("abstained needs a reason and no confidence".into()));
            }
            (false, Some(c), _) if (0.0..=1.0).contains(&c) => {}
            (false, c, _) => return Err(invalid(format!("confidence {c:?} is not in [0, 1]"))),
        }
        for b in &score.breakdown {
            if b.family.dimension() != dimension {
                return Err(invalid(format!(
                    "breakdown family {:?} belongs to the other dimension",
                    b.family
                )));
            }
            for id in &b.evidence_ids {
                if !self.evidence.iter().any(|e| &e.id == id) {
                    return Err(invalid(format!("breakdown cites unknown evidence `{id}`")));
                }
            }
        }
        Ok(())
    }

    /// Why an evidence item cannot be traced to its sources, if it cannot.
    fn unverifiable(&self, e: &Evidence) -> Option<String> {
        if !e.value.is_finite() {
            return Some("value is not a finite number".into());
        }
        if e.source_refs.is_empty() {
            return Some("it cites no source".into());
        }
        for r in &e.source_refs {
            match r {
                SourceRef::Document { span } => {
                    let ok = self
                        .document
                        .as_ref()
                        .is_some_and(|d| span_text(d, *span).is_some());
                    if !ok {
                        return Some("document span is out of range".into());
                    }
                }
                SourceRef::Context { id, quote } => {
                    let Some(item) = self.context.iter().find(|c| &c.id == id) else {
                        return Some(format!("unknown context `{id}`"));
                    };
                    if quote
                        .as_ref()
                        .is_some_and(|q| !item.text.contains(q.as_str()))
                    {
                        return Some(format!("quote is not verbatim in context `{id}`"));
                    }
                }
                SourceRef::Url { url } => {
                    if !(url.starts_with("https://") || url.starts_with("http://")) {
                        return Some(format!("`{url}` is not an http(s) URL"));
                    }
                }
            }
        }
        None
    }

    /// Every text a quotation may come from: the document, the context and evidence details.
    fn quotable(&self) -> Vec<&str> {
        let document = self
            .document
            .iter()
            .flat_map(|d| d.title.iter().chain(&d.paragraphs));
        let context = self.context.iter().flat_map(|c| {
            let claim = c.fact_check.iter().map(|f| &f.claim);
            c.title.iter().chain([&c.text]).chain(claim)
        });
        let evidence = self.evidence.iter().map(|e| &e.detail);
        document
            .chain(context)
            .chain(evidence)
            .map(String::as_str)
            .collect()
    }
}

fn unique_ids<'a>(ids: impl Iterator<Item = &'a str>) -> Result<(), ApplyError> {
    let mut seen = HashSet::new();
    for id in ids {
        if !seen.insert(id) {
            return Err(ApplyError::DuplicateId(id.to_owned()));
        }
    }
    Ok(())
}

/// Quotations in LLM-written `text`: passages of at least [`MIN_QUOTE_CHARS`] characters inside
/// double quotes or guillemets, without the punctuation at their edges.
fn quotations(text: &str) -> Vec<&str> {
    // Opening mark and the marks that close it, across the conventions of European languages.
    const fn closes(open: char, c: char) -> bool {
        matches!(
            (open, c),
            ('"', '"') | ('“' | '”', '”') | ('„', '“' | '”') | ('«', '»') | ('»', '«')
        )
    }
    let mut found = vec![];
    let mut open: Option<(usize, char)> = None;
    for (i, c) in text.char_indices() {
        match open {
            Some((start, mark)) if closes(mark, c) => {
                let quote = text[start..i]
                    .trim_matches(|c: char| c.is_whitespace() || ".,;:!?…".contains(c));
                if quote.chars().count() >= MIN_QUOTE_CHARS {
                    found.push(quote);
                }
                open = None;
            }
            None if matches!(c, '"' | '“' | '”' | '„' | '«' | '»') => {
                open = Some((i + c.len_utf8(), c));
            }
            _ => {}
        }
    }
    found
}

/// The text at `span`, if the span is valid. Offsets are Unicode code points.
fn span_text(doc: &Document, span: Span) -> Option<&str> {
    let paragraph = doc.paragraphs.get(span.paragraph as usize)?;
    if span.start >= span.end {
        return None;
    }
    let byte_at = |chars: u32| {
        paragraph
            .char_indices()
            .map(|(i, _)| i)
            .chain(std::iter::once(paragraph.len()))
            .nth(chars as usize)
    };
    paragraph.get(byte_at(span.start)?..byte_at(span.end)?)
}

#[cfg(test)]
mod tests {
    use chrono::Utc;
    use uuid::Uuid;

    use super::*;
    use crate::analysis::*;
    use crate::stage::*;

    fn record() -> Analysis {
        let mut a = Analysis::new(
            Uuid::now_v7(),
            Input {
                kind: InputKind::Text,
                value: "x".into(),
                context_url: None,
                explanation_language: None,
            },
            "test".into(),
            Utc::now(),
        );
        a.document = Some(Document {
            url: None,
            outlet: None,
            published_at: None,
            title: None,
            author: None,
            paragraphs: vec![
                "Perché il governo mente.".into(),
                "Second paragraph.".into(),
            ],
            outbound_links: vec![],
            tracking_ids: vec![],
        });
        a.context = vec![context("ctx1", "Wire copy about the same event.")];
        a
    }

    fn context(id: &str, text: &str) -> ContextItem {
        ContextItem {
            id: id.into(),
            url: format!("https://example.com/{id}"),
            outlet: Some("example.com".into()),
            published_at: None,
            title: None,
            author: None,
            text: text.into(),
            language: Some("en".into()),
            retrieved_by: "google_news".into(),
            tracking_ids: vec![],
            fact_check: None,
            similarity: None,
            in_story: None,
            story_reason: None,
        }
    }

    fn evidence(id: &str, family: Family, source_refs: Vec<SourceRef>) -> Evidence {
        Evidence {
            id: id.into(),
            family,
            signal: "s".into(),
            value: 0.5,
            detail: "d".into(),
            source_refs,
        }
    }

    fn cited() -> Vec<SourceRef> {
        vec![SourceRef::Context {
            id: "ctx1".into(),
            quote: None,
        }]
    }

    fn claim(id: &str, text: &str, span: Span) -> Claim {
        Claim {
            id: id.into(),
            text: text.into(),
            span,
        }
    }

    fn understand(claims: Vec<Claim>) -> StagePatch {
        StagePatch::Understand(UnderstandPatch {
            topic: Topic {
                summary: "s".into(),
                entities: vec![],
                date: None,
                place: None,
            },
            claims,
            queries: vec![],
        })
    }

    fn score(confidence: Option<f64>, abstained: bool, reason: Option<&str>) -> Score {
        Score {
            confidence,
            abstained,
            reason: reason.map(Into::into),
            breakdown: vec![],
        }
    }

    #[test]
    fn claims_are_checked_verbatim_with_code_point_offsets() {
        let mut a = record();
        let span = |start, end| Span {
            paragraph: 0,
            start,
            end,
        };
        let report = a
            .apply(understand(vec![
                // "é" is two bytes; offsets count characters, as in Python.
                claim("cl1", "il governo mente", span(7, 23)),
                claim("cl2", "invented quote", span(0, 14)),
                claim(
                    "cl3",
                    "out of range",
                    Span {
                        paragraph: 9,
                        start: 0,
                        end: 3,
                    },
                ),
            ]))
            .unwrap();
        assert_eq!(
            a.claims.iter().map(|c| c.id.as_str()).collect::<Vec<_>>(),
            ["cl1"]
        );
        assert_eq!(report.dropped.len(), 2);
    }

    #[test]
    fn understand_needs_a_document() {
        let mut a = record();
        a.document = None;
        assert_eq!(
            a.apply(understand(vec![])),
            Err(ApplyError::MissingDocument)
        );
    }

    #[test]
    fn empty_document_is_rejected() {
        let mut a = record();
        let mut doc = a.document.clone().unwrap();
        doc.paragraphs = vec!["  ".into()];
        let patch = StagePatch::Extract(ExtractPatch {
            document: doc,
            language: None,
        });
        assert_eq!(a.apply(patch), Err(ApplyError::EmptyDocument));
    }

    #[test]
    fn evidence_outside_the_stage_dimension_rejects_the_patch() {
        let mut a = record();
        let patch = StagePatch::Signals(
            Dimension::Single,
            SignalsPatch {
                evidence: vec![evidence("s1", Family::TextReuse, vec![])],
            },
        );
        assert!(matches!(
            a.apply(patch),
            Err(ApplyError::WrongDimension { .. })
        ));
        assert_eq!(a.evidence, []);
    }

    #[test]
    fn evidence_ids_must_be_unique_across_parallel_stages() {
        let mut a = record();
        let single = StagePatch::Signals(
            Dimension::Single,
            SignalsPatch {
                evidence: vec![evidence("e1", Family::Tone, cited())],
            },
        );
        let coordinated = StagePatch::Signals(
            Dimension::Coordinated,
            SignalsPatch {
                evidence: vec![evidence("e1", Family::Timing, cited())],
            },
        );
        a.apply(single).unwrap();
        assert_eq!(
            a.apply(coordinated),
            Err(ApplyError::DuplicateId("e1".into()))
        );
    }

    #[test]
    fn untraceable_evidence_is_dropped_and_reported() {
        let mut a = record();
        let ctx = |id: &str, quote: Option<&str>| SourceRef::Context {
            id: id.into(),
            quote: quote.map(Into::into),
        };
        let patch = StagePatch::Signals(
            Dimension::Coordinated,
            SignalsPatch {
                evidence: vec![
                    evidence(
                        "c1",
                        Family::TextReuse,
                        vec![ctx("ctx1", Some("Wire copy"))],
                    ),
                    evidence(
                        "c2",
                        Family::TextReuse,
                        vec![ctx("ctx1", Some("never said"))],
                    ),
                    evidence("c3", Family::TextReuse, vec![ctx("ctx9", None)]),
                    evidence(
                        "c4",
                        Family::Infrastructure,
                        vec![SourceRef::Url {
                            url: "javascript:alert(1)".into(),
                        }],
                    ),
                    evidence("c5", Family::Timing, vec![]),
                ],
            },
        );
        let report = a.apply(patch).unwrap();
        assert_eq!(
            a.evidence.iter().map(|e| e.id.as_str()).collect::<Vec<_>>(),
            ["c1"]
        );
        assert_eq!(report.dropped.len(), 4);
        assert!(report.summary().unwrap().starts_with("dropped 4: "));
    }

    #[test]
    fn story_assignments_must_reference_known_context() {
        let mut a = record();
        let patch = |id: &str| {
            StagePatch::Story(StoryPatch {
                assignments: vec![StoryAssignment {
                    context_id: id.into(),
                    similarity: 0.9,
                    in_story: true,
                    reason: None,
                }],
            })
        };
        assert_eq!(
            a.apply(patch("ctx9")),
            Err(ApplyError::UnknownContext("ctx9".into()))
        );
        let report = a.apply(patch("ctx1")).unwrap();
        assert_eq!(a.context[0].in_story, Some(true));
        assert_eq!(report.detail.as_deref(), Some("1 of 1 items in the story"));
    }

    #[test]
    fn scores_are_validated() {
        let cases = [
            (score(Some(0.8), false, None), true),
            (score(None, true, Some("fewer than 3 related items")), true),
            (score(Some(1.2), false, None), false),
            (score(None, false, None), false),
            (score(Some(0.5), true, Some("why")), false),
            (score(None, true, None), false),
        ];
        for (single, ok) in cases {
            let mut a = record();
            let patch = StagePatch::Score(ScorePatch {
                scores: Scores {
                    single: single.clone(),
                    coordinated: score(None, true, Some("no copies found")),
                },
            });
            assert_eq!(a.apply(patch).is_ok(), ok, "{single:?}");
        }
    }

    #[test]
    fn score_breakdown_must_cite_existing_evidence_of_its_dimension() {
        let contribution = |family, id: &str| Contribution {
            family,
            contribution: 1.2,
            evidence_ids: vec![id.into()],
        };
        let cases = [
            (contribution(Family::Tone, "s1"), true),
            (contribution(Family::Tone, "missing"), false),
            (contribution(Family::TextReuse, "s1"), false),
        ];
        for (entry, ok) in cases {
            let mut a = record();
            a.evidence = vec![evidence("s1", Family::Tone, cited())];
            let mut single = score(Some(0.7), false, None);
            single.breakdown = vec![entry.clone()];
            let patch = StagePatch::Score(ScorePatch {
                scores: Scores {
                    single,
                    coordinated: score(None, true, Some("none")),
                },
            });
            assert_eq!(a.apply(patch).is_ok(), ok, "{entry:?}");
        }
    }

    #[test]
    fn reasons_without_valid_evidence_are_dropped() {
        let mut a = record();
        a.evidence = vec![evidence("s1", Family::Tone, vec![])];
        let reason = |ids: &[&str]| Reason {
            text: "r".into(),
            evidence_ids: ids.iter().map(|s| (*s).to_owned()).collect(),
        };
        let patch = StagePatch::Explain(ExplainPatch {
            explanation: Explanation {
                summary: "s".into(),
                reasons: vec![reason(&["s1"]), reason(&[]), reason(&["s1", "ghost"])],
            },
        });
        let report = a.apply(patch).unwrap();
        assert_eq!(a.explanation.unwrap().reasons.len(), 1);
        assert_eq!(report.dropped, ["2 reasons without valid evidence"]);
    }

    #[test]
    fn explanations_may_only_quote_verbatim_text() {
        let mut a = record();
        a.evidence = vec![evidence("s1", Family::Tone, cited())];
        let reason = |text: &str| Reason {
            text: text.into(),
            evidence_ids: vec!["s1".into()],
        };
        let patch = StagePatch::Explain(ExplainPatch {
            explanation: Explanation {
                summary: "The text claims that «the minister stole millions».".into(),
                reasons: vec![
                    // Verbatim in the document; the comma inside the quotes is ignored.
                    reason("It says “il governo mente,” without a source."),
                    // Verbatim in a context item.
                    reason("Others wrote \"Wire copy about the same event.\""),
                    // Too short to be a quotation.
                    reason("A \"loaded\" word."),
                    reason("It says \"the government always lies\"."),
                ],
            },
        });
        let report = a.apply(patch).unwrap();
        let explanation = a.explanation.unwrap();
        assert_eq!(explanation.reasons.len(), 3);
        assert!(
            explanation
                .reasons
                .iter()
                .all(|r| !r.text.contains("always"))
        );
        assert_eq!(explanation.summary, "");
        assert_eq!(report.dropped.len(), 2, "{:?}", report.dropped);
    }
}
