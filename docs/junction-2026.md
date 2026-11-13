# Junction 2026 — event, judging, sponsors

Researched 10–11 Nov 2026. Full challenge briefs were not public yet: re-check the Junction Platform on Friday.

## Event
- Hype Areena, Kivenlahti, Espoo. 13–15 Nov 2026. Teams of 1–4. ~2,000 participants, €100k prize pool.
- Sources: <https://2026.hackjunction.com/>, <https://hackjunction.app/hackathons/junction-2026>
- Submissions are open-sourced under MIT; the team keeps ownership.
- Submission fields (platform schema): name ≤100 chars, punchline ≤300, description ≤3000, source URL, demo URL, video URL, ≤5 images, track, challenges (the schema caps at 5, but the team confirmed on site that tech challenges are uncapped), table location. Video length limit not published. <https://github.com/hackjunction/JunctionApp/blob/STAG/shared/constants/project-schema.js>

### Schedule (UTC+2)
| When | What |
|---|---|
| Fri 16:00 | Doors open, registration 2nd floor |
| Fri 18:00 | Opening: DeepMind keynote, challenge videos |
| Fri 19:30 | Hacking starts |
| Fri 20:15 | Google DeepMind workshop |
| Fri 20:30/20:45 | Verda onboarding workshop (Loft); Arduino workshop (5th floor) |
| Fri 21:15 | MLH x GitHub session |
| **Fri 23:59** | **Preliminary submission** |
| Sat 11:15 | Cala workshop |
| Sat 12:00 | Submissions open |
| Sat 12:15 | Ignite Next workshop (5th floor) |
| Sat 13:00 | Hostinger keynote |
| Sat 13:45 | Modal workshop |
| Sat 14:50 | Kiuas workshop |
| Sat 16:45 | Exa workshop |
| Sat 17:45 | Context.dev workshop |
| **Sun 10:00** | **Final submission** |
| Sun 10:30–14:00 | Peer review at tables |
| Sun 14:00 | Final ceremony: top 5 pitches, challenge winners 15:10, Junction winner 15:50 |

## Judging
- Partners pick their own track/challenge winners.
- Main prize: face-to-face peer review (Gavel pairwise comparison, ~15 projects per reviewer) → top 5 → live pitch to a 7-person grand jury. <https://www.junctionplatform.com/review-options>
- Stated jury criteria:
  - Kia Kanninen (Founders House): a problem worth solving, not an easy vibe-coded feature.
  - Daksh Raghuvanshi (AfterQuery RL lead, [StoreBench](https://arxiv.org/abs/2610.10942)): explain exactly why an agent fails in your world; a reward that holds when someone tries to break it.
  - Otto Söderlund (Supercell AI lead): real user problem, something people come back to.
  - Hubertus van der Drift (Context.dev CTO): fast, pragmatic, one insight that makes it 10x better.
  - Timo Ahopelto (Lifeline Ventures), Umar Noor (Google DeepMind), one TBA.
- Implication: real problem + working agent + documented failure modes + adversarial evals beats a polished UI.

## Tracks
Hardware (Arduino), Healthcare, AI Infrastructure (Verda), FinTech, Agentic AI, Data. Tech challenges run across all tracks.

## Challenge partners
| Partner | Challenge (as published) | Dev surface |
|---|---|---|
| Verda | AI Infra track. "Best use of Verda": any challenge solved using any Verda service. 1st €10k credits + merch, 2nd/3rd €2.5k. Document the process; show it scales beyond a prototype. Credits for all teams via Platform coupon. [blog](https://verda.com/blog/junction-2026) | GPU instances, serverless containers, object storage, Inference API `https://inference.verda.com/v1` (Kimi K3.1 Pro, 1M ctx). [redeem credits](https://docs.verda.com/resources/obtaining-free-credits/how-to-redeem-credits/) |
| Valio Aimo | "Trusted Trade Agents": agents for foodservice purchasing (find, compare, handle surprises) with humans in control; synthetic data + mock APIs. [IG](https://www.instagram.com/p/De9TVp8nJi0) | Provided mock APIs |
| S-Pankki | "Personal Economic Trainer": conversational money coach on synthetic transaction data. | Compute numbers deterministically, LLM explains |
| Cala | "Make Unicorns Real": product for founders/VCs, Slush timing. [IG](https://www.instagram.com/p/DfFSwa_COOz) | `POST /v1/knowledge/query` (Cala QL), MCP `api.cala.ai/mcp/`. [quickstart](https://docs.cala.ai/quickstart) |
| MariaDB | "Wikipedia Through Time": vector search + history-preserving tables. [IG](https://www.instagram.com/p/DfHNd7wCIQy) | `VECTOR`, `VEC_DISTANCE`, system-versioned tables, [MCP](https://github.com/mariadb/mcp) |
| Meta | AI glasses: hands-free point-of-view experiences. [IG](https://www.instagram.com/p/DfRxJqCCMc_/) | Wearables Device Access Toolkit, Ray-Ban Display web apps + browser simulator |
| Arduino / Ignite Next × Intel | Hardware Lab: UNO Q, LeRobot arms, 3D printers | Arduino App Lab + Bricks; OpenVINO on NPU |
| Google DeepMind | Featured partner, "something special" for winners; MLH "Best Use of Gemini API" | Gemini 3.8 Flash / Live, Gemma 4, ADK (Python/TS), Robotics ER 2 |
| AfterQuery | No brief; RL lead on grand jury | Reproducible environments / evals |
| Hostinger | "Decode the Noise": detect propaganda, bots and bad actors online; must run live on Hostinger with a public URL; judged on honest detection logic, false-positive handling, precision/FPR. Directions: swarm, technique, traffic, provenance. Details: `hostinger-challenge.md` | VPS KVM 2 (2 vCPU, 8 GB, Docker, free domain), AI Router `https://router.hostinger.com/v1`, MCP `https://mcp.hostinger.com` |
| City of Espoo, Bahn Express, Stoa, Rokoko, AstraZeneca, Tieto | Teaser or nothing yet | — |

## Tech partners
Best-use prizes confirmed: **NVIDIA Nemotron, Modal, Cloudinary**. Others give credits/tools.

| Partner | Use |
|---|---|
| NVIDIA | build.nvidia.com free endpoints (Nemotron), OpenAI-compatible `integrate.api.nvidia.com/v1` |
| Modal | Serverless GPU/CPU in Python, sandboxes; Starter $30/mo, 3 seats |
| Cloudinary | Media APIs, AI transforms, MCP |
| OpenAI Codex | Codex CLI, Agents SDK, Responses/Realtime API |
| Featherless | OpenAI-style API over open-weight models |
| Exa | Search / Contents / Answer / Websets / Monitors, MCP; $10 free |
| Context.dev | Scrape/crawl → Markdown, `/web/extract` with JSON Schema, monitors; 1k free credits/mo |
| Aiven | Free Postgres (pgvector), Kafka, OpenSearch, Valkey |
| Oxylabs | Scraping API, Agent Browser, MCP |
| IronShard | S3-compatible storage with zero-copy branches for agents, MCP |
| Wendy | Physical-AI OS, Go2/G1 MuJoCo sim, MCP |
| Qualia, Scailab | Robotics eval / synthetic data — waitlist / private beta |
| CRACI | Secure CI runners |

## Stack candidates
- One OpenAI-compatible client; provider via `LLM_BASE_URL` (Verda, NVIDIA, Featherless, OpenAI).
- Agent loop: plain tool calling, OpenAI Agents SDK, or Google ADK (if targeting DeepMind/Gemini).
- Python + FastAPI (uv) backend, TypeScript + Vite/Next frontend, contract in `contracts/openapi.yaml`.
- Postgres + pgvector (Aiven) or MariaDB (if that challenge).
- Heavy compute on Modal or Verda.
- `evals/`: deterministic scenario runner + adversarial cases + failure-mode table shown in the demo.

## Unknown until the event
Full briefs and prizes for most partners, video length limit, extra submission questions, 7th judge.
