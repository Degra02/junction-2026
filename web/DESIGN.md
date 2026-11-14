# Design System: Decode the Noise — Context-Aware Propaganda Analysis

Synthesized per Google Stitch `taste-design` and `DECISIONS.md` (D1–D17).

## 1. Visual Theme & Atmosphere
An editorial investigative OSINT workspace — calm, forensic, and evidence-first, combining the story-comparison clarity of **Ground News** with the technical precision of a **VIGINUM** intelligence report.
- **Density:** 6/10 ("Investigative Desk") — airy enough for a non-technical reader on the summary and reasons, switching smoothly into structured tabular density inside peer coverage, score math, and evaluation metrics.
- **Variance:** 5/10 ("Structured Asymmetric") — left-aligned hero and asymmetric two-column analysis workspace (`minmax(0, 1.55fr) minmax(320px, 1fr)` on desktop, single-column stack below `1024px`).
- **Motion:** 4/10 ("Restrained Responsive") — live pulse only on the active running pipeline step; smooth transform/opacity reveals when expanding combiner math or jumping to a verbatim document span.
- **Core Ethical Constraint (D4):** Never display a binary "Propaganda / Not propaganda" verdict or red/green traffic-light judgement. Confidence scores represent measured alignment with documented manipulation or coordination signals, always paired with evidence counts and verbatim sources, or an explicit **"Not enough evidence"** abstention.

## 2. Color Palette & Roles

### Light Mode (Default)
- **Newsprint Slate** (`#F8FAFC`) — Primary page canvas (`--bg-canvas`)
- **Archival Sheet** (`#FFFFFF`) — Elevated surface for primary containers (`--bg-surface`)
- **Subtle Well** (`#F1F5F9`) — Inset wells, inactive tracks, and code/quote blocks (`--bg-subtle`)
- **Charcoal Ink** (`#0F172A`) — Primary reading text and numerals (`--fg-primary`)
- **Muted Steel** (`#475569`) — Secondary descriptions, outlet metadata, and captions (`--fg-secondary`)
- **Quiet Slate** (`#64748B`) — Timestamps, axis labels, and tertiary hints (`--fg-muted`)
- **Hairline Rule** (`#E2E8F0`) — Structural 1px borders and table rules (`--border-subtle`)
- **Strong Rule** (`#CBD5E1`) — Interactive input borders and active dividers (`--border-strong`)
- **Archival Cobalt** (`#1D4ED8`) — Single primary accent for CTAs, active SSE steps, confidence bars, focus rings, and selected evidence citations (`--accent`)
- **Cobalt Wash** (`#EFF6FF`) — Highlight background for active verbatim document spans (`--accent-soft`)

### Dark Mode (`.dark`)
- **Night Desk** (`#090D16`) — Primary page canvas (`--bg-canvas`)
- **Slate Ledger** (`#111827`) — Primary container surface (`--bg-surface`)
- **Deep Well** (`#1E293B`) — Inset wells, tracks, and quote blocks (`--bg-subtle`)
- **Crisp Paper** (`#F1F5F9`) — Primary text (`--fg-primary`)
- **Silver Slate** (`#94A3B8`) — Secondary text (`--fg-secondary`)
- **Dim Steel** (`#64748B`) — Tertiary metadata (`--fg-muted`)
- **Dark Hairline** (`#1E293B`) — 1px structural borders (`--border-subtle`)
- **Dark Strong Rule** (`#334155`) — Input borders (`--border-strong`)
- **Signal Cobalt** (`#3B82F6`) — Primary accent (`--accent`)
- **Dark Cobalt Wash** (`rgba(59, 130, 246, 0.16)`) — Active verbatim span highlight (`--accent-soft`)

### Semantic Functional Accents (Metadata Only — Never Verdict Traffic Lights)
- **Caution Amber** (`#B45309` light / `#F59E0B` dark) — Uncalibrated prior-weights notice, VIGINUM `known_network` badge, language support cap notice.
- **Corroboration Teal** (`#0F766E` light / `#14B8A6` dark) — Completed pipeline ticks and negative log-odds contributions pointing away from manipulation (e.g., recognized wire agency, corroborated claim).
- **Failure Crimson** (`#B91C1C` light / `#F87171` dark) — Reserved strictly for HTTP/stage execution errors (`status === "failed"` or `step.state === "failed"`), never for content scores.

## 3. Typography Rules
- **Display & UI Sans:** `Plus Jakarta Sans Variable` (`--font-sans`) — Tight tracking (`-0.025em`) on headings, crisp weight contrast (`600`/`700`), relaxed reading line-height (`1.62`) on document paragraphs capped at `68ch`.
- **Technical & Tabular Mono:** `JetBrains Mono Variable` (`--font-mono`) with `font-variant-numeric: tabular-nums` — Mandatory for all confidence percentages, log-odds contributions (`+1.40`, `-0.50`), Wilson 95% intervals (`[0.71, 0.92]`), coverage fractions, domain registration dates, tracking IDs (`G-...`), and stage durations.
- **Banned:** `Inter`, generic browser serifs (`Times New Roman`, `Georgia`), all-caps tracked-out eyebrow clichés on every section, gradient headline text.

## 4. Component Stylings
- **Buttons:** Crisp `0.5rem` (`8px`) radius, flat fill (`--accent` with white text for primary; `--bg-surface` with `--border-strong` for secondary), `-1px` active press feedback, `2px` offset focus-visible ring. No outer glows.
- **Containers & Dividers:** Moderate `0.75rem` (`12px`) radius with `1px solid var(--border-subtle)` and zero heavy drop shadows; high-density inner sections (coverage rows, breakdown bars, metrics tables) use hairline top borders rather than nested cards-in-cards.
- **Dimension Score Panels:** Equal two-up grid for *Signs of propaganda in the content itself* (`single`) and *Signs of a coordinated campaign* (`coordinated`). Shows percentage in `JetBrains Mono`, evidence item count, and a neutral-track cobalt bar. When `abstained: true`, displays **"Not enough evidence"** at primary heading weight with `score.reason` directly beneath.
- **Citation Pills (`[s1]`, `[c2]`):** Compact inline monospace buttons next to every explanation reason; clicking highlights the corresponding evidence item and scrolls/flashes the exact Unicode code-point span in the Document Reader or peer quote in Coverage View.
- **Skeletons & Stepper:** Live SSE stepper shows real stage progress notes (`step.detail`) and durations; no generic full-screen circular spinners.

## 5. Layout Principles
- Max container width `1280px` with responsive horizontal padding (`clamp(1rem, 3vw, 2rem)`).
- Left-aligned asymmetric Hero on `/`: headline + punchline and live pipeline architecture summary paired with the primary input composer and real VPS preset chips.
- Two-column desktop workspace on `/analyses/:id`: analytical synthesis on the left (scores, summary & linked reasons, Ground News peer coverage, combiner math) and sticky verbatim Document Reader + Pipeline Trace on the right.
- Strict single-column collapse below `1024px` (`lg`), zero horizontal overflow at `375px`, `min-h-[100dvh]` root shell, minimum `36px–44px` interactive targets.

## 6. Anti-Patterns (Strictly Forbidden)
- Never label any article or post "Propaganda", "Fake News", "Safe", or "Verified" (D4).
- Never invent or hardcode evaluation metrics, response times, or uptime numbers; when `/api/metrics` returns `404`, state honestly that the evaluation run has not been published yet while showing live `/api/stats` counts.
- Never slice `document.paragraphs` with UTF-16 `String.prototype.slice`; always index Unicode code points via `Array.from(paragraph)`.
- Never attach SSE handlers only to `EventSource.onmessage` (backend emits named `snapshot`, `queue`, `step`, `done` events).
- No emojis in UI chrome, no neon purple/blue gradients, no 3-equal-marketing-card filler rows.
