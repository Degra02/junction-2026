# Demo script

Target: 3 minutes live, same beats in the video. Live site: <https://the4thlover.tech>. Every input below is a real, documented case from `evals/labelled.jsonl`; its analysis ID (submitted after the last deploy) is in the table at the end, so the live demo plays it back with `events?replay=true` and never waits on a source.

## Beats

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Landing page, one input box | "A reader sees an article and can't tell if it's manipulation, or one node of a network pushing the same story. Checking that by hand is hours of OSINT. We do it in under five minutes, and we show every source." |
| 0:20–1:10 | **Input 1, coordinated**: a Pravda-network article. Progress steps tick: reading, finding other coverage (N sources), checking fact-checkers, comparing | "We don't ask a model whether this is propaganda. We go and find how everyone else covered the same event." Point at the coordinated score: copied passages on other language editions within hours, domains on VIGINUM's Portal Kombat list. Open "Show how we calculated this": each family's contribution in log-odds. |
| 1:10–1:50 | **Input 2, single-actor**: a claim debunked by a fact-checker, in a second language | Claims contradicted by the coverage, the fact-check matched, tone compared with the peers on the same story. "Every reason links to its evidence; quotes are checked word for word, or dropped." |
| 1:50–2:30 | **Input 3, hard negative**: the fact-check of the same claim (or agency copy republished by many newsrooms) | "A naive detector flags this: it quotes the hoax / it is copied everywhere. Ours stays low: quotations are masked, news agencies are recognised." Then "Not enough evidence" on an item with too little coverage: we abstain instead of guessing. |
| 2:30–3:00 | Metrics page | Precision and false-positive rate per dimension with 95% intervals, FPR on each hard-negative set (fact-checks, satire, wire copy, press releases), abstain and failure rates, ablation per family. "Measured on third-party labels, not on our opinion. Runs on one Hostinger VPS, CPU only." |

## Rules for the live demo
- No "propaganda / not propaganda" wording (D4): say "signs of", "confidence", "evidence".
- If the live site is slow, switch to replay links; if it is down, play the backup recording.
- Numbers on the metrics page are read from `evals/metrics.json`; say the set size and the intervals, not only the point values.

## Inputs

Submit each one on the VPS after the last deploy (`POST /api/analyses?force=true`). Record the analysis ID and keep the one with a clean run. Swap in a backup if the main item has gone offline or scores without evidence.

| Beat | Item | Language | Why | Analysis ID |
|---|---|---|---|---|
| Coordinated | `pk_de_002` deutsch.news-pravda.com "Yuri Kotenok: Leidenschaften nach Konstantinovka" | de | Same piece the same day on the fr, es and en editions (`pk_fr_001`, `pk_es_001`, `pk_en_002`); the domain is on the VIGINUM list | after deploy |
| Coordinated, backup | `pk_de_004` austria.news-pravda.com, Latvian oil reserves | de | Copies in nl, pt, ro (`pk_nl_001`, `pk_pt_001`, `pk_ro_001`) | after deploy |
| Single-actor | `fcd_de_002` achgut.com "Sind die Klimadaten manipuliert?" | de | BR24 #Faktenfuchs rated the claim false | after deploy |
| Single-actor, 2nd language | `fcd_en_001` cdm.press "Christians being crucified in Syria" | en | DW Faktencheck: false | after deploy |
| Hard negative | `fc_de_005` BR24 #Faktenfuchs debunk of the `fcd_de_002` claim | de | Quotes the hoax; should stay low | after deploy |
