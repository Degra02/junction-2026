# Directions for "Decode the Noise" — comparison and open decisions

> **Superseded (Fri 21:00):** the team chose a new direction, a context-aware pipeline for single-actor and coordinated propaganda. Plan and open decisions: `docs/plan.md`. This file remains as background (judges' feedback, confidence-score proposal, dataset facts).

Written Fri 13.11 evening from three branches pushed within 15 minutes of each other (commit times, Helsinki):

| | Branch | Commit | Where it lives now |
|---|---|---|---|
| **A** | `degra/hostinger-spec` (first version) | `fa5fcfa`, 21:22 | Superseded by B in the merge `ec6aff3`; original text in `git show fa5fcfa:SPEC.md` |
| **B** | `lyreplus/spec` | `5820a6d`, 21:19 | Merged: current `SPEC.md`, `docs/hostinger-challenge.md`; recorded as a team decision in `DECISIONS.md` (Fri 20:30) |
| **C** | `pcerka/setup` | `ef2b9e4`, 21:33 | Not merged: `docs/swarm-idea.md` on that branch |

C was pushed after B's decision line and covers what B lists as out of scope ("account-level social media bot detection"). So the team has not actually converged yet.

## Judges' feedback (Fri evening)
1. **Show the confidence score and how it is calculated**: which signals and cross-references produced it, not just a number.
2. **Scale and impact matter**: network traffic analysis could be a good fit.
3. **Focus on one type of detection (or a few)** and do it well, rather than going broad and delivering weak results.
4. **The frontend matters too**, but tackle it later, once the specs of the whole project are final.

What this changes:
- Point 3 argues against B as written (three detectors, nine sponsors) and for A, C, or one detector built from them.
- Point 2 favours A, and especially traffic analysis at hosting scale (see "A + C" below).
- Point 1 favours directions where each signal can be measured on labelled data, so its weight in the score can be justified: A and C have labels; B's provenance and copy-network parts do not.
- Point 4 makes frontend work wait for the spec freeze (decision 11).

## The ideas in one line each
- **A — Clean the traffic.** Classify each visitor session in our own VPS's web logs as human, verified bot, fake bot, scanner or credential stuffer. Verdicts come from rules plus a small classifier; an LLM only explains them.
- **B — Analyse one piece of content.** Given a URL, text or screenshot, name the manipulation techniques (quoting exact spans), show who is behind the site, and find other sites carrying the same text. Built from many sponsor services.
- **C — Spot the swarm in a stream of posts.** Find groups of accounts that act as one: near-duplicate text, synchronised timing, shared infrastructure. A cluster is flagged only when at least two signals agree. Detection is deterministic; an LLM only writes the summary.
- **A + C — Spot the swarm in traffic** (new, combines the two after the judges' feedback). Apply C's clustering to A's web traffic: find groups of IPs/sessions that act as one (credential-stuffing botnets, distributed scrapers, coordinated scanners). C's three signals map directly:
  - text → request fingerprint (path sequence, method, status pattern, user-agent family);
  - time → synchronised bursts, machine-regular intervals;
  - infrastructure → shared ASN, /24 subnet, reverse DNS.

  One detection type, deterministic, labelled data from A, and a scale story: only a host sees the same botnet hitting thousands of its customers' sites at once.

## Side by side
| | A — traffic | B — content item | C — account swarm |
|---|---|---|---|
| Hostinger directions | Clean the traffic | Name the technique + Trust the source + Spot the swarm (sites) | Spot the swarm (accounts) |
| Input | Access logs of our own site | One URL / text / screenshot | A batch or stream of posts |
| Unit judged | Visitor session | The item, plus the network of sites copying it | Cluster of accounts |
| Detector | Rules, classifier, reverse-DNS check, honeypot paths | Fine-tuned Gemma for techniques; Nemotron verifies spans; MinHash for reuse; RDAP and shared tracking IDs for provenance | MinHash + LSH on text, time bursts, metadata; graph components; ≥2 of 3 signals |
| Who decides the verdict | Deterministic | Models decide the technique labels (spans must match the text verbatim); provenance and reuse are deterministic | Deterministic |
| LLM | AI Router, explanations only | Nemotron VL as investigator agent and verifier; Gemma on the VPS | AI Router, cluster narrative only |
| Sponsors used | Hostinger (optional: Aiven, Nemotron, Verda) | 9 in tiers: Nemotron, Context.dev, Oxylabs, Gemma, Verda, Modal, Aiven, Codex, CRACI | Hostinger only (none named) |
| Labelled eval data | Zenodo web-robot logs, labels that hold by construction on our live logs, attack scripts | SemEval-2020 (open download), 2023/2024 (registration); hard negatives labelled by the team | Cresci-2017 (social spambots vs genuine accounts, tweets with timestamps); IRA tweets (positives only) |
| Labelled data for the swarm/provenance part | n/a | **None yet**: only the technique part has a benchmark | Cresci-2017 |
| Live input judges can try | Their own phone visiting the site | Any URL they paste | None named; datasets are Twitter 2014–2018 |
| Demo moment | Judge's phone shows up as "human"; our attack script is flagged with reasons | Paste a URL → technique spans, copy-site graph sharing one GA/GTM ID, then a fact-check correctly cleared | Not written yet |
| False-positive guards | Verified bots allowed; judge per session, not per IP (venue NAT); abstain | Hard-negative sets (fact-checks, satire, op-eds, wire copy) with FPR each; verbatim span check; abstain on model disagreement | ≥2 signals; tiers high/medium/watch; allow-list for publishers; shared IP never enough |
| Runs on the Hostinger VPS | Everything | API, UI and Gemma; the rest calls external services | Everything |
| Main risks | Reads as a generic WAF; least "propaganda" | Breadth: three detectors and nine sponsors in 48 h; Gemma on 2 vCPU; research-only licences; Oxylabs $500 plan | No live data; old Twitter data; the infrastructure signal can only be tested on synthetic data |
| How the confidence score would be built | Per-signal weights learned on the labelled logs; reverse-DNS and honeypot hits are near-certain cross-references | Model probabilities for techniques; hand-set weights for provenance and copies (no labels to learn them from) | Number and strength of agreeing signals → tier; weights learnable on Cresci-2017 |
| Fit with judges' feedback | Scale ✓, focus ✓, explainable score ✓ | Focus ✗ (three detectors), explainable score partial | Focus ✓, explainable score ✓, scale and live data weak |

## Where they agree
All three already share these, so they can be recorded as decisions now:
- The verdict needs **several independent signals**; one weak signal is never enough.
- An **abstain / watch** outcome is a first-class result, not a failure.
- **False-positive rate is reported per hard-negative set**, alongside a written list of known false positives.
- Page content and log fields are **data, never instructions** to a model.
- Live on the Hostinger VPS with a public URL.

## Where B and C overlap
Both say "Spot the swarm" but mean different things:
- **B** searches the web for copies of one text and clusters the **sites** that carry it.
- **C** clusters the **accounts** inside a stream of posts.

Both use MinHash for text reuse. C's cluster rules (≥2 signals, confidence tiers, publisher allow-list) and its labelled benchmark (Cresci-2017) are exactly what B's swarm step lacks. B's live web search and its demo are exactly what C lacks.

## Confidence score: a proposal that fits any direction
The judges want to see how the number is made. Proposal:
1. **Group signals into independent families**, e.g. text/request fingerprint, timing, infrastructure, external cross-references (reverse DNS, honeypot hit, the same source seen on other sites, public abuse lists).
2. **Each signal contributes a weight** = how much more often it occurs in bad than in good cases on labelled data (log likelihood ratio). Within a family take only the strongest signal, so correlated evidence is not counted twice; sum across families.
3. **Convert the sum to a probability and calibrate it** on held-out data: a score of 0.9 should mean about 90% of such cases were really bad. Show the calibration table on the evaluation page.
4. **Show the breakdown with every verdict**: one line per family with its contribution, e.g. "+2.1 posting interval 4.0 s ± 0.1 s across 38 sessions", "+1.4 same /24 subnet", "−3.0 reverse DNS verified as Googlebot".
5. **Tiers come from calibrated precision** (high / medium / watch / abstain), not from hand-picked cut-offs.

Where labels are missing, weights must be hand-set; the evaluation page has to say so. That is the main reason point 1 of the feedback favours A and C.

## Scale and impact (for traffic directions)
- **Impact story**: Hostinger hosts millions of sites. A botnet that stuffs credentials into one site usually hits many; only the host can correlate across sites. A + C turns that into one detector.
- **What we can show honestly in 48 h**:
  - throughput on the KVM 2 (requests per second sessionised and scored);
  - a replay of the 4.09M-request public dataset;
  - cross-site correlation over several demo sites (subdomains) on our VPS, with the limit stated: one VPS, not real customer traffic.
- **Ask the booth** for anonymised multi-site logs; with them, the scale claim becomes measured instead of argued.

## Dataset facts (checked Fri evening)
| Dataset | Used by | Access | Terms |
|---|---|---|---|
| SemEval-2020 Task 11 / PTC | B | Open, 1.1 MB, [Zenodo 3952415](https://zenodo.org/records/3952415) | Academic use only |
| SemEval-2023 Task 3, 2024 Task 4 | B | Registration + passcode; 2023 approval is manual | Research only, no redistribution |
| Cresci-2017 | C | Open, 466 MB zip, [Bot Repository](https://botometer.osome.iu.edu/bot-repository/datasets.html) | Academic research only; Twitter content-redistribution terms apply |
| Bot Repository "astroturf" | (C, option) | Open | CC BY-NC-ND 4.0; hyper-active political bots in follow trains |
| FiveThirtyEight IRA tweets | C | Open, [GitHub](https://github.com/fivethirtyeight/russian-troll-tweets), 2.97M tweets from 2,848 handles | Positives only |
| Web-robot server logs | A | Open, [Zenodo 3477932](https://zenodo.org/records/3477932) | Licence not checked |

Nothing from this table goes into the repo: it becomes public under MIT.

## Decisions we need to take
Ordered by deadline. The preliminary submission (name, punchline, track, challenges) is due **Fri 23:59**.

1. **Which product.** Options, re-read against the judges' feedback:
   - **A + C: swarm detection in traffic.** Fits all three detection points (one detection type, explainable score from labelled signals, scale). Weakest on the "propaganda" headline of the brief, although traffic is one of its four named directions.
   - **A alone.** Simpler than A + C; per-session verdicts only, no coordinated-group view.
   - **C standalone with a live stream** (e.g. Bluesky Jetstream, a public WebSocket with no auth). Focused and explainable; weak on scale and limited to old labelled data.
   - **B narrowed to one detector** (technique naming only, or copy networks only). Keeps the content angle; the judges' focus point rules out B as written.
   - **B as written.** Broadest, and goes directly against feedback point 3.

   Decide before 23:59: the preliminary submission needs the name and punchline.
2. **Swarm unit**: IPs/sessions (A + C), sites (B), accounts (C), or several behind one clustering module.
3. **What judges can try live**: visit the site from their own device and watch the verdict (A, A + C), paste a URL (B), watch a live stream (C + Jetstream), or a fixed replay. "Demo works only on our data" is what the brief warns against.
4. **Who sets the verdict.** Proposed rule: swarm and provenance verdicts are deterministic; technique labels may come from a model only when every span matches the text verbatim. LLMs explain; they never override.
5. **Default model endpoint**: Hostinger AI Router (visible Hostinger usage, explains-only role in A/C) or Nemotron + Gemma (tech prizes in B). Both are reachable through `LLM_BASE_URL`; pick the demo default and the fallback.
6. **Sponsor scope**: if we keep B, which tier-1 services are truly on the demo path. Every extra service is another key, adapter and failure point before Sun 03:00.
7. **Data tonight**: who downloads SemEval-2020 and/or Cresci-2017; who registers for SemEval-2023/2024; who collects hard negatives. Licences: all research/academic only; ask the organisers whether a public MIT repo with weights trained on them is acceptable.
8. **Shared false-positive contract**: write the agreed principles above into `DECISIONS.md` as one line, so every component follows them.
9. **Owners**: map components to the four roles in `AGENTS.md` (integrator, AI core, product, problem/pitch).
10. **Confidence formula**: adopt the proposal above (families, likelihood-ratio weights, calibration, per-verdict breakdown) or an alternative. Every component must return its breakdown through the API, because the UI will display it.
11. **Frontend timing**: no frontend work until the spec is final (after decision 1 and the booth answers). Until then the API returns everything the UI will need, including the score breakdown. Product collects design references meanwhile.
12. **Branch cleanup**: once 1 is decided, the integrator merges `pcerka/setup`'s `docs/swarm-idea.md` (or the parts kept) and updates `SPEC.md` scope; A's text stays only in history.
