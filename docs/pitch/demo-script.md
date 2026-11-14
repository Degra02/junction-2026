# Demo script

Target: 3 minutes live, same beats in the video. Live site: <https://the4thlover.tech>. Every input below is a real, documented case from `evals/labelled.jsonl`; its analysis ID (submitted after the last deploy) is in the table at the end, so the live demo plays it back with `events?replay=true` and never waits on a source.

## Beats

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Landing page, one input box | "A reader sees an article and can't tell if it's manipulation, or one node of a network pushing the same story. Checking that by hand is hours of OSINT. We do it in under five minutes, and we show every source." |
| 0:20–1:10 | **Input 1, coordinated**: a Pravda-network article. Progress steps tick: reading, finding other coverage (N sources), checking fact-checkers, comparing | "We don't ask a model whether this is propaganda. We go and find how everyone else covered the same event." Point at the coordinated score and open "Show how we calculated this": each family's contribution in log-odds. Say what carries it: today the domain on VIGINUM's Portal Kombat list (`known_networks`), not copies; "the list is also how this article got its label, so the metrics page shows the number without it". Copied passages on other language editions only if the run found them. |
| 1:10–1:50 | **Input 2, single-actor**: `fcd_de_002`, a German article claiming NASA manipulated the climate data | Single-actor 0.832. Open "Show how we calculated this": a fact-check matched across languages (Climate Feedback rated the claim "Inaccurate", linked), persuasion techniques in the text (appeals to authority, personal attacks, slogans). "Every reason links to its evidence; quotes are checked word for word, or dropped." |
| 1:50–2:30 | **Input 3, hard negative**: `fc_de_005`, BR24's debunk of the same claim | "A naive detector flags this: it quotes the hoax. Ours does not give it a score": it says **Not enough evidence** ("Only 0 other reports on the same event were found; at least 3 are needed to compare"). We abstain instead of guessing, and the metrics page counts abstentions as coverage, not as wins. |
| 2:30–3:00 | Metrics page | Precision and false-positive rate per dimension with 95% intervals, FPR on each hard-negative set (fact-checks, satire, wire copy, press releases), abstain and failure rates, ablation per family. "Measured on third-party labels, not on our opinion. Runs on one Hostinger VPS, CPU only." |

## Rules for the live demo
- No "propaganda / not propaganda" wording (D4): say "signs of", "confidence", "evidence".
- If the live site is slow, switch to replay links; if it is down, play the backup recording.
- Numbers on the metrics page are read from `evals/metrics.json`; say the set size and the intervals, not only the point values.

## Inputs

Submitted on the VPS on Sat 14 Nov, evening (`POST /api/analyses?force=true`, pipeline after #24, Oxylabs on, Google Fact Check key not yet set); `fcd_de_002` and `fc_de_005` re-run after #27 (`rerun?from=signals_single`, `sha-1833d1f`: satire guard, cross-lingual fact-check verdict match). Play back with `GET /api/analyses/{id}/events?replay=true`. Re-submit the `fcd_*` items once `GOOGLE_FACTCHECK_API_KEY` is on the VPS, and every item after the last deploy; keep the clean runs.

| Beat | Item | Language | Why | Analysis ID | Result |
|---|---|---|---|---|---|
| Coordinated | `pk_de_002` deutsch.news-pravda.com "Yuri Kotenok: Leidenschaften nach Konstantinovka" | de | Same piece the same day on the fr, es and en editions (`pk_fr_001`, `pk_es_001`, `pk_en_002`); the domain is on the VIGINUM list | `01a1dae7-401d-731c-af9d-b08a42306086` | coordinated 0.622 from `known_networks`; 2 reports found, no copies; single abstains (1 report) |
| Coordinated, backup | `pk_de_004` austria.news-pravda.com, Latvian oil reserves | de | Copies in nl, pt, ro (`pk_nl_001`, `pk_pt_001`, `pk_ro_001`) | `01a1dae7-4016-77c1-9083-2ad685506776` | coordinated 0.622 from `known_networks`; 1 report, no copies; single abstains |
| Single-actor | `fcd_de_002` achgut.com "Sind die Klimadaten manipuliert?" | de | BR24 #Faktenfuchs rated the claim false | `01a1db57-b2d1-75b2-a829-61bb61a365d9` (first run `01a1daeb-b551-7706-ae2b-6ad7f0540212` abstained) | **single 0.832**: `fact_checks` rated_false (Climate Feedback "Inaccurate", science.feedback.org), techniques (justification 0.37, attack on reputation 0.27); coordinated 0.076 |
| Single-actor, 2nd language | `fcd_en_001` cdm.press "Christians being crucified in Syria" | en | DW Faktencheck: false | `01a1dae8-3d1f-7648-b402-a830ed249618` | single abstains (1 report); coordinated 0.153 with one `text_reuse` hit by exact phrase |
| Hard negative | `fc_de_005` BR24 #Faktenfuchs debunk of the `fcd_de_002` claim | de | Quotes the hoax; should stay low | `01a1db57-b426-76d0-8eaa-2ca77c6e86d6` (first run `01a1daea-03ba-751b-9d7b-4a4c827f71cb`) | both abstain (0 reports in the story). Risk: techniques fire on the quoted hoax (attack on reputation 0.57); it stays out of the score only because single abstains |
