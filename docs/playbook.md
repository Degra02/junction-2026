# Playbook — 4 people, 48h, agent-driven

## Roles
1. **Integrator** — owns `main`, contracts, `AGENTS.md`, `DECISIONS.md`; merges every round; keeps CI green.
2. **AI core** — agent/model loop, the key insight, `evals/` (adversarial cases, failure modes).
3. **Product** — UI and demo path, deploy. Give agents a concrete design reference to copy.
4. **Problem / pitch** — partner + user validation, demo data, end-to-end tests, video, description, pitch. Also codes.

## Timeline
| When | Do | Done when |
|---|---|---|
| Fri 18:00–19:30 | Watch challenge videos, shortlist 2 | — |
| Fri 19:30–21:00 | Ask partner reps what they actually want. Pick the demo moment, work backward. Fill `SPEC.md` (have an agent interview you). Write how a naive agent fails. | `SPEC.md` + demo script |
| Fri 21:00–23:30 | Integrator: layout, contracts, walking skeleton on `main` with fake data, preview deploy. Use the stack we know. | `main` runs the demo screen |
| **Fri 23:59** | Preliminary submission: name, punchline, track/challenges, repo link | Draft saved |
| Fri 24:00–Sat 12:00 | ~2h rounds, merge at the end of each. Sleep shifts: 2 sleep 01–06, 2 sleep 04–09. | `main` green each round |
| Sat 12:00–18:00 | Real pieces wired. **Real data through the demo path by 16:00.** Test with 2–3 real users/mentors/partner reps. One person attends only the relevant workshops. | Real end-to-end run |
| Sat 18:00–Sun 03:00 | Last features, adversarial evals, believable demo data | — |
| **Sun 03:00** | **Feature freeze.** Only demo-path fixes after this. | — |
| Sun 03:00–08:00 | Record video + backup demo recording. Description with GIFs. Rehearse twice from a fresh clone. | Video uploaded |
| **Sun 09:00** | Submit (10:00 is hard) | Submitted |
| Sun 10:30–14:00 | Someone always at the table running a 90-second demo loop; others do review duty. 3-minute top-5 pitch ready. | — |

## Working with agents
- Split by folder, not by feature. Shared files go through the integrator (see `AGENTS.md`).
- One branch per person; parallel agents on one machine use **separate `git clone`s**, not worktrees (sibling worktrees break inside `jomp`, see `setup.md`).
- Contract first: commit `contracts/openapi.yaml` (or shared types) in hour one; frontend runs against a Prism mock until the backend is ready. Only the integrator changes contracts.
- Before merging, check overlap: `git merge-tree --write-tree --name-only main <branch>`. If `main` breaks, fixing it is everyone's only job.
- Enforce rules with hooks/CI, not prose. Pre-commit blocks commits to `main` and scans for secrets.
- Write tests first; a different person or agent reviews. "Done" means it was run (see `AGENTS.md`).
- Minimal MCP set: database, Playwright, the one sponsor MCP in use.
- Record every decision in `DECISIONS.md`; agents re-read it each round.

## Failure modes
1. Branches drift 12h+ → Saturday-night integration hell.
2. Agent claims "done" without running anything.
3. Scope creep: the next feature always looks one prompt away.
4. Vibe-coded feature instead of a real problem.
5. Architecture change midway; whole team stuck researching.
6. Last-hour video panic.
7. Demo fails live (missing env var, wifi) → fresh-clone rehearsal + recorded backup.
8. Keys leaked in the public repo; force-push or `reset --hard` destroys a teammate's work.
9. Empty table during peer review.

## Submission checklist
- [ ] Name, punchline (≤300), description (≤3000) with GIFs and the failure-mode/eval story
- [ ] Track + up to 5 challenges (partner + stacked tech prizes: Verda, Modal, NVIDIA, Cloudinary, Gemini)
- [ ] Public repo, README with run instructions, no secrets (`mise run secrets`)
- [ ] Demo URL live; video uploaded; ≤5 images
- [ ] Verda "best use": process documented
- [ ] Rotate every API key after the event

## Sources
- <https://joxo.ai/blog/hackathon-plan-with-coding-agents>
- <https://code.claude.com/docs/en/best-practices>
- <https://kuchta.dev/posts/junction-2024>
- <https://blog.jetbrains.com/ai/2026/06/how-to-win-a-hackathon-notes-from-the-judging-table/>
- <https://simonwillison.net/2025/Oct/7/vibe-engineering/>
