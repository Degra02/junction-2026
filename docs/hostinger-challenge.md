# Hostinger "Decode the Noise" — research notes

Evidence behind `SPEC.md`. The product (Name the technique + Trust the source + Spot the swarm on web content) is decided in `DECISIONS.md`; this file adds facts, datasets, methods and risks for it. Researched Fri 13.11.

## The brief (paraphrased)
- Build an AI-powered tool that analyses text, social content or web-traffic patterns to detect coordinated propaganda, bot-driven amplification or bad-actor behaviour. Form is open: API, dashboard, explainable classifier, monitoring service.
- **Hard requirement**: deployed and running live on Hostinger infrastructure by the end, with a public URL judges can open.
- **Judged on**: strength and honesty of the detection logic, including false positives, over a polished front end. "Show your precision and false-positive rate, not just a demo that works on the happy path."
- Directions: Spot the swarm, Name the technique, Clean the traffic, Trust the source. We combine three; Clean the traffic is out of scope.
- Mentors at the Hostinger booth all weekend: Minijus Savickas (VPS product), Emilis Strimaitis (innovations, AI agents). Talk "Vibe Coding Solved Building. Now Comes the Hard Part", Sat 13:00.

## What Hostinger provides
| Resource | Facts | Consequence |
|---|---|---|
| VPS KVM 2 | 2 vCPU, 8 GB RAM, 100 GB NVMe, 8 TB bandwidth, root, Docker, free domain; one-click Ollama/n8n/Node/Python templates | CPU only. A small quantised Gemma fits in RAM; measure latency before relying on it in the demo path. |
| AI Router | Base URL `https://router.hostinger.com/v1`, keys start `sk-hstgr-`; OpenAI- and Anthropic-SDK compatible; `/chat/completions`, `/responses`, `/messages`, `/embeddings`; per-key daily/monthly spend limits and model allow-lists. Model IDs documented publicly: `claude-sonnet-5`, `gpt-5.2`, `text-embedding-3-small`, `text-embedding-3-large`. [docs](https://www.hostinger.com/support/what-is-hostinger-ai-router-and-how-to-get-started/), [LiteLLM](https://docs.litellm.ai/docs/providers/hostinger_router) | Whether Nemotron or Gemma are in the catalogue is unknown: check hPanel → AI Router → Models. Router embeddings are a ready option for the reuse detector. Set a spend limit on the key. |
| Connector / MCP | `claude mcp add --transport http hostinger https://mcp.hostinger.com` (OAuth); scoped `hostinger-vps-mcp` with 68 VPS operations. [repo](https://github.com/hostinger/api-mcp-server) | The one sponsor MCP for deploys. |

## Name the technique: datasets
| Dataset | Content | Access | Terms |
|---|---|---|---|
| **SemEval-2020 Task 11 / PTC** | ~550 English news articles, span-level labels, 18 techniques (14 classes for technique classification); gold labels for the training sets | **Direct download, no registration**: `datasets-v2.tgz`, 1.1 MB, [Zenodo 3952415](https://zenodo.org/records/3952415) | PTC page: "may only be used for academic purposes" ([ptc](https://propaganda.math.unipd.it/ptc/)) |
| SemEval-2023 Task 3 | News in 6 languages, paragraph-level multi-label, 23 techniques in 6 categories | Registration, then a team passcode after **manual approval** ([task](https://propaganda.math.unipd.it/semeval2023task3/)) | Scientific research only; no redistribution in part or full |
| SemEval-2024 Task 4 | Memes, text-only (20 techniques) and multimodal (22) subtasks, hierarchical labels | Registration, then passcode ([task](https://propaganda.math.unipd.it/semeval2024task4)) | Scientific research only; no redistribution; do not reuse the images |
| Annotation guidelines (JRC) | Definitions and examples for every technique | Public PDF ([JRC132862](https://knowledge4policy.ec.europa.eu/sites/default/files/JRC132862_technical_report_annotation_guidelines_final_with_affiliations_1.pdf)) | Use for prompt definitions and UI explanations |

Consequences:
- SemEval-2020 is the only one usable tonight. It gives the Friday zero-shot baseline and the first Gemma fine-tune data.
- Register for 2023 and 2024 now; approval is manual and may not arrive this weekend.
- The repo becomes public under MIT: never commit these datasets. Fine-tuned weights are derived from research-only data, so check with the organisers before publishing them.
- The three taxonomies differ (18 vs 23 vs 22 techniques). Map to one label set, e.g. the 6 SemEval-2023 categories, before comparing models.
- Label noise is high on fine-grained techniques. Report category-level metrics next to technique-level ones.

## Spot the swarm: method
Pacheco et al., ICWSM 2021 ([paper](https://arxiv.org/abs/2001.05658)), an unsupervised pipeline that fits our copy-network detector:
1. Choose traces: exact phrases, MinHash shingles, shared tracking IDs, outbound links.
2. Build a bipartite graph of sites × traces. **IDF-weight** traces so common ones (popular quotes, wire copy, CMS boilerplate) carry little evidence.
3. Project onto a site × site graph (Jaccard or cosine). Keep only the strongest edges; the paper keeps the top 1%.
4. Take connected components as candidate networks.

Findings to reuse:
- A support filter (minimum number of traces per site) cuts noise.
- **Combining trace types** (text reuse plus shared infrastructure) reduces false positives. This matches our "reuse alone is never a verdict" rule.
- Coordination ≠ automation ≠ malice: the paper found mixed human/bot clusters. Say this in the UI next to every network.

## Trust the source: signals
- **Domain age**: RDAP returns JSON with a `registration` event; it replaces WHOIS for gTLDs.
- **First certificate**: Certificate Transparency logs (e.g. crt.sh, crt.live) give the first certificate date per hostname. This is a second, independent age signal and also lists sibling subdomains.
- **Shared tracking IDs** (GA, GTM, AdSense): the SPEC's key insight; the Modal sandbox catches IDs injected by JavaScript.
- **AI-generated text: weak signal only.** Open-source detectors show unacceptable false-positive rates at naive thresholds ([RAID, ACL 2024](https://aclanthology.org/2024.acl-long.674.pdf)). The strongest zero-shot method, Binoculars ([paper](https://arxiv.org/abs/2401.12070)), needs two 7B models and does not fit the VPS. If used at all, show it as context, never as evidence for the verdict.

## Risks
- **"Deployed on Hostinger" vs external services.** Most of the pipeline calls Context.dev, Oxylabs, NVIDIA, Verda, Modal and Aiven. The API, UI and Gemma run on the VPS, which should satisfy the requirement, but execution plus live Hostinger deploy is 25% of the score. Confirm at the booth (question 1). Routing a fallback model through the AI Router strengthens the case.
- **Gemma on 2 vCPU.** Few output tokens per classification helps, but span extraction over a full article is long input. Measure latency per article on the VPS before Saturday 16:00. Fallback: classify paragraphs in parallel, or serve the fine-tune from Verda behind the same client.
- **Hard negatives are where the false-positive rate is decided.** Fact-checks, satire, op-eds and wire copy must be collected early, not on Saturday night.
- **Licences on the demo path.** No SemEval text on screen in the public demo; use the live copy-network case.

## Considered and dropped: Clean the traffic
Bot detection in web-server logs was evaluated first because it allows labels by construction (honeypot paths, reverse-DNS-verified crawlers, tagged human sessions) and a public labelled dataset ([Zenodo 3477932](https://zenodo.org/records/3477932)). The team chose content analysis instead (`DECISIONS.md`, Fri 20:30). The by-construction idea still applies to our evals: build eval items whose label is certain from how they were made (known wire stories, known fact-check articles), not from a model.

## Overlap with other Junction challenges
- **MariaDB "Wikipedia Through Time"** (partner challenge): its M dataset has 862,076 versions of 19,742 Finnish history articles, with editor, anonymous flag and `sha1` (a repeated hash marks a revert). It provides free ground truth for coordinated editing. Only relevant if a project may enter two partner challenges. [datasets](https://github.com/MariaDB/mariadb-wikipedia-datasets)
- **Exa** (partner challenge): a search API that would compete with Oxylabs/Context.dev in our flow. Not in our tiers.

## Questions for the Hostinger booth
1. Does calling external services (Context.dev, Oxylabs, NVIDIA, Verda, Modal, Aiven) from the VPS satisfy "deployed and running live on Hostinger", given that the API, UI and Gemma run there?
2. Does the AI Router catalogue include Nemotron or Gemma, and how many credits does each team get?
3. Can they share real cases of cloned or propaganda sites seen on their hosting, to evaluate against?
4. How much do they weigh the three directions we combine against depth in one?
5. Free-domain provisioning time.

## Sources
- Datasets: <https://zenodo.org/records/3952415>, <https://propaganda.math.unipd.it/ptc/>, <https://propaganda.math.unipd.it/semeval2023task3/>, <https://propaganda.math.unipd.it/semeval2024task4>
- Coordination detection: <https://arxiv.org/abs/2001.05658>
- AI-text detection: <https://aclanthology.org/2024.acl-long.674.pdf>, <https://arxiv.org/abs/2401.12070>
- Hostinger: <https://www.hostinger.com/support/what-is-hostinger-ai-router-and-how-to-get-started/>, <https://docs.litellm.ai/docs/providers/hostinger_router>, <https://github.com/hostinger/api-mcp-server>
