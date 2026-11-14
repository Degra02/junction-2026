# Submission text

Fields of the Junction platform (`docs/junction-2026.md`): name ≤ 100 characters, punchline ≤ 300, description ≤ 3,000. The name is the one from the preliminary submission (Fri 23:59); it is not recorded in the repo. Numbers come from the committed `evals/metrics.json` (284 items, weights fitted on the same set with 5-fold cross-validation, `df75a3a`); recompute them here if the metrics change.

## Punchline (D17, 114 characters)
Paste a link. See how everyone else covered it, what's been copied, and how sure we are — with every source shown.

## Links
- Demo: <https://the4thlover.tech>
- Source: <https://github.com/Degra02/junction-2026> (MIT)
- Track: Hostinger "Decode the Noise". Tech challenge: Oxylabs (D7: exact-phrase web and news search, blocked pages). Google MLH "Best Use of Gemini API" (D15) only if the team counts the LLM calls (`gemini-3.1-flash-lite` through Hostinger AI Router): no Gemini grounded-search adapter was built.

## Description (2,768 characters)
A reader sees an article and cannot tell whether it is manipulation by its author, or one node of a network pushing the same story. Answering that today is hours of manual OSINT. A model's opinion of the text alone is not an answer: it is biased by language, prompt-injectable and the reader cannot check it.

We take one piece of content (pasted text or a link, in any language) and go and find how everyone else covered the same event: the RSS feeds of curated outlets, GDELT and Oxylabs for exact-phrase searches and blocked pages, Google Fact Check Tools for fact-checks. For every outlet we look up the domain's age, its first TLS certificate, its type (news agency, fact-checker, satire…) and whether it is on VIGINUM's list of the Russian "Portal Kombat" network.

From that context we answer two separate questions: how strongly the content shows signs of propaganda by its author (persuasion techniques, tone far more charged than its peers on the same story, claims the coverage contradicts or fact-checkers rate false), and of coordinated propaganda (passages copied across unrelated outlets, copies within hours, shared tracking IDs, documented networks). Each answer is a confidence score with the evidence behind it, never a "propaganda / not propaganda" label. When the evidence is too thin, it says "Not enough evidence" and why, instead of guessing.

How the score is calculated is on screen: each signal family contributes one number (its strongest signal only, so correlated evidence is not counted twice) and a logistic regression adds them up. "Show how we calculated this" lists every contribution and links each one to its source. An LLM summarises the evidence; it never sets the score, and every quote it uses is checked word for word against the sources.

We designed against the ways a naive detector fails: fact-checks that quote a hoax, news agency copy republished by hundreds of newsrooms, satire, op-eds and emotional but accurate reporting. Quotations are masked before scoring, agencies are recognised, tone is compared with peers rather than judged in absolute.

Evaluation uses third-party labels only: 284 items in 12 languages from fact-checkers' ClaimReview ratings, EUvsDisinfo cases, VIGINUM-listed Pravda-network sites, and hard negatives (fact-checks, wire copy, press releases, satire, op-eds, emotional reporting). Single-actor: precision 0.98 and false-positive rate 0.03 (1 of 39, a satire piece), but it scores only 43% of items and abstains on the rest, so it catches 46% of all positives; it rests mostly on fact-check matches (cross-validated AUC 0.98, 0.84 without them). Coordinated: perfect on the set, but only because the VIGINUM list both labels the positives and is a signal: without it the AUC falls to 0.38. We publish those numbers next to the headline.

It runs on one Hostinger VPS (2 vCPU, 8 GB, no GPU): a Rust API, a Python worker with CPU models, LLM calls through Hostinger AI Router. The same detector works on any set of sites: a host could run it across hosted domains to spot networks like Portal Kombat.
