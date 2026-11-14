# Persuasion in memes and short posts: analysis plan

Status: **priority over the source graph** (Sun 15.11, 01:00, `DECISIONS.md`). Phases 1 and 2 come before every source-graph task; phase 3 comes before the graph's after-submission phases. Goes beyond `docs/plan.md`, like the source graph: each contract change goes through the integrator. Tasks and done criteria per person: `docs/next-steps.md` → "Persuasion in memes and posts".

## 1. The failure
Degra02 analysed a political meme from r/Conservative (image upload with the Reddit post as `context_url`). The cartoon puts a podium labelled "AFFORDABILITY" behind a stack of papers labelled "TRUMP INVESTIGATIONS"; a voter holding groceries says "I THOUGHT THIS WAS ABOUT MY GROCERY BILL". It makes no checkable claim; it persuades by juxtaposition, irony and an implied straw man (the opponent's affordability agenda is "really" about investigations). Result: **"Not enough evidence" on both dimensions.** Coordinated abstaining is correct (no copies were found). Single-actor abstaining is the bug.

How each stage saw it (code on `main` at `fed5165`):

| Stage | What happens |
|---|---|
| extract (`pipeline/extract/vision.py`) | The image's text becomes 3 short paragraphs plus the Reddit title. The vision prompt says "never judge", so the visual argument survives only as a neutral `[Visual context]` sentence. `Post.community` (r/Conservative) is dropped. |
| understand | Claims must be verbatim checkable facts (`triage` keeps `fact`): the meme's message is implied, so **0 claims**. |
| signals_single | `[Visual context]` paragraphs are excluded from techniques (`single.py:47`). With 0 claims, `claim_support` and `fact_checks` have nothing to check. The outlet `reddit.com` is 20 years old, so `domain_age` is 0. |
| score | `_single_abstention`: no fact-check match and fewer than 3 related reports → abstain, **whatever the techniques found**. |
| signals_coordinated | A copy needs ≥ 8 shared word 5-grams; the image's text has 4 (all in the speech bubble). Text reuse can never fire on a meme. |

## 2. Measurements
Technique model (`Mishtar4/persuasion-detector-xlm-roberta`, pinned revision, model thresholds) on the meme's text, Sun 00:45:

| Input | Detected |
|---|---|
| Each text block of the image, or all three joined | nothing (highest probability 0.03) |
| The meme written as a prose description | `Doubt` |
| The implied claim written out ("Democrats promised… all they really care about is investigating Trump") | `Doubt`, `Appeal_to_Hypocrisy`; `Straw_Man` 0.53 against its 0.95 threshold |

Highest single-actor confidence a claimless meme can reach with the fitted `weights.json` (intercept −1.60, techniques 1.28, tone 0.41), with the abstention removed:

| Scenario | single |
|---|---|
| What the model detects on this meme (nothing) | 0.168 |
| One category in 1 of 4 paragraphs (value 0.25 → strength 0.5) | 0.277 |
| Techniques saturated | 0.420 |
| Techniques and tone saturated | 0.523 |

## 3. Causes
1. **The single-actor abstention mixes two kinds of family.** "Fewer than 3 related reports" matters for the families that compare with coverage (`tone`, `claim_support`). `techniques` and `source_profile` read the content and its source only, and are thrown away with them.
2. **Nothing that sees the persuasion may judge it.** The only model that sees the image is told not to; the technique model reads 3- to 8-word fragments, far from its training data (news paragraphs).
3. **Implied claims are dropped.** Memes argue by implication; the verbatim rule leaves no claim, so no fact-check search and no fact-check match.
4. **The combiner was fitted on articles whose single-actor positives are mostly fact-checker debunks.** `fact_checks` weighs 4.05; `techniques` alone has CV AUC 0.4965. The 284-item set has no image and no social post, and the 123 items on which single abstained are not fitted, which hides cause 1.
5. **Coordination is text-only**: an image repeated across accounts is invisible.
6. **A Reddit or X address of an image post analyses the title only**: the image in `Post.links` is never read.

## 4. Design
Decided (`DECISIONS.md`, Sun 01:00):

- **D5 amended: a multimodal LLM rates persuasion techniques.** New single-actor family **`rhetoric`** (contract: `Family::Rhetoric`), next to `techniques` (XLM-R), so the fit and its ablation show what each adds. One typed call per analysis in `signals_single`, through `pipeline/common/llm` with its own model setting (`LLM_RATER_MODEL`; `gemini-4-hydrogen` is the candidate: fast, multimodal, cheap). Signal stages may make LLM calls through `pipeline/common/llm` (as `judge.verify_pairs` already does); they still fetch nothing from the web.
- **What the rater sees**: title and paragraphs (max 12,000 characters, like understand), and the image itself when `input.kind == image` and `input.value` is a data URI. For an image URL the rater reads the `[Visual context]` paragraph instead (no fetch in a signal stage).
- **What the rater returns**: per detected technique, its SemEval-2023 category (the six `signal` names of `techniques`: `attack_on_reputation`, `justification`, `simplification`, `distraction`, `call`, `manipulative_wording`), the technique name, `clear` or `weak`, and either a verbatim quote of the content's own words or, for a purely visual technique, the visual element it uses. One evidence item per category, `value` 1.0 (`clear`) or 0.5 (`weak`), strongest first.
- **Evidence stays checkable**: every quote is located with `spans.locate`; a quote that is not found drops the item. A visual-only item points at the `[Visual context]` paragraph and its `detail` says it is our description of the image. Quoted passages (`text.own_words`) are not the author's words: a technique found only inside a quotation is dropped.
- **The prompt judges the move, never the side**: technique definitions only, no truth judgement, no outside knowledge about whether a claim is true, the same rules whichever party is the target; content goes in `user`, never in `system`. Satire handling is unchanged (satire outlet and `[Satire/humour meme]` still abstain).
- **Implied claims**: understand also returns up to 3 `implied_claims` (contract: `Topic.implied_claims: Vec<String>`), one English sentence each, only for what the content asserts by implication (memes, rhetorical questions, sarcasm). They feed fact-check search and fact-check matching only, **never `claim_support`** (a paraphrase against reports gives false contradictions) and never a quotation in the explanation.
- **Vision describes the implied message**: the `[Visual context]` sentence also states, neutrally, what the image implies ("The image implies that …"). It is still no verdict.
- **Abstention split (phase 2)**: with fewer than 3 related reports and no fact-check match, single-actor no longer abstains when an intrinsic family (`techniques`, `rhetoric`, `source_profile`) has evidence; it is scored, and the explanation says no coverage was found to compare with. It abstains when none of them has evidence either.
- **Unchanged**: D4 (no "propaganda / not" label, a confidence per dimension), the verbatim rules of the API, satire abstention, the coordinated dimension's rules.

## 5. Phases and gates
| Phase | Content | Gate to merge |
|---|---|---|
| 1, score-neutral, before the Sun 03:00 freeze | contract (`Family::Rhetoric`, `Topic.implied_claims`), `llm` model setting with image input, rater, implied claims, vision implied message, image posts read through vision, web labels | **No calibrated number moves**: `rhetoric` has `STRENGTH` entries (the explanation and the UI show its evidence) but is **not** in `families.SINGLE` and has no coefficient, so it adds nothing to the confidence and the "points both ways" abstention cannot see it. `mise run check` passes. |
| 2, the score change | abstention split, fact-check search and matching on implied claims, meme labelled set, eval run, refit with ablation, metrics | **One PR carries `weights.json` and `evals/metrics.json` together.** Cut-off Sun 06:00; past it, phase 2 waits for after submission and the pitch shows phase 1. |
| 3, after submission | image reuse for coordinated (Reddit duplicates, perceptual hash of images in retrieved posts) | Fit with its ablation, like every new family. |

Phase 2 is accepted when, against the numbers in `docs/ai-core.md`:
- no single-actor FPR on an article hard-negative set gets worse (today 0 on emotional, fact_checks, op_eds, press_releases, wire_copy);
- the meme set is reported as its own rows (precision, recall, FPR, abstain rate);
- `cv.ablation.rhetoric` is reported (`auc_without`, `auc_alone`);
- the symmetry check (section 6) is reported;
- the meme of section 1 is scored on single-actor (not abstained), with `rhetoric` evidence citing its words or its visual juxtaposition. **No threshold or weight is tuned to this one example.**

## 6. Evaluation data
- **Labels from third parties** (`evals/README.md`): [SemEval-2024 Task 4](https://aclanthology.org/2024.semeval-1.275) (multilingual persuasion techniques in memes). Subtask 2b is binary, propagandistic vs not, so it has negatives. About 100 English memes, balanced, downloaded by `evals/download_data.sh` into the gitignored `evals/data/`; nothing from the dataset is committed. Check the licence before use; the label of an item is the annotators' (`source`: "SemEval-2024 Task 4").
- **Hard negatives**: the subtask 2b negatives, plus mainstream editorial cartoons and plain jokes when a third party's label exists.
- **Symmetry check (not a label)**: 10 pasted-text pairs, each a meme's text and visual description with the political target swapped (party, person). Report the mean and maximum |Δ single| between the two sides of a pair; a gap above 0.1 is a finding to fix in the rater prompt before the PR.
- **Construct**: on articles a single-actor positive mostly means "debunked by a fact-checker"; on memes it means "uses persuasion techniques". Report both sets separately, never one merged headline.

## 7. Risks
| Risk | Mitigation |
|---|---|
| The rater leans to one political side | Section 6 symmetry check; prompt rules in section 4; quotes must be verbatim |
| The rater over-flags ordinary persuasive writing (op-eds, press releases) | Hard-negative FPR gate in section 5; `weak` counts half |
| Prompt injection inside the content | Content in `user` only; typed output; quotes verified against the document |
| Latency and cost | One call per analysis on a fast model; the rater runs alongside XLM-R, not after each paragraph. Report `signals_single` p50/p95 from `/api/stats` after the deploy |
| The model is unavailable | The rater returns no evidence and logs a warning (as `judge.verify_pairs`); the analysis still finishes |
| Calibrated numbers move before the refit | Phase 1 gate |

## 8. Not decided
- A profile of the community (subreddit, channel) as the source. Typing communities as partisan touches D9; `Post.community` stays out of the document until the team decides.
- Whether `rhetoric` replaces `techniques` once the ablation is in. Decide on the phase 2 numbers.
