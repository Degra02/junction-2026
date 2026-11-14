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
