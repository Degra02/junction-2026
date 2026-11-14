# Design system

An investigative newsroom tool: paper and ink, one accent, data in mono, every number next to its source. References: Linear and Vercel for chrome and density, the FT and Stripe Press for reading type, Perplexity and ChatGPT Deep Research for the live run.

## Principles
- **Say less.** One short line per idea. No marketing sentences, no "seamlessly", no restating what a control shows. A heading is 1–4 words; helper text is one line or nothing.
- **Content over chrome.** No decorative icons in headings, no icon on every label, no gradients on text, no emoji, no glass on reading surfaces.
- **Hierarchy by type and space, not boxes.** Hairline rules (`border-t border-[var(--border-subtle)]`) separate rows; avoid cards inside cards.
- **Show the work.** A running analysis shows what it is doing now, what it found so far, and how long it took, inline (never behind a button).
- **D4.** Never label anything "Propaganda", "Fake", "Safe", "Verified"; scores are confidences per dimension or "Not enough evidence". No red/green verdict colours: red is for failed requests and stages only.

## Type
| Role | Font | Use |
|---|---|---|
| UI | Geist (`font-sans`, default) | Everything not listed below |
| Display / reading | Newsreader (`.display` or `font-serif`) | Page titles, the analysed article's title and paragraphs, the explanation summary |
| Data | Geist Mono (`.font-mono-num`) | Durations, counts in tables, domains, IDs, log-odds, small percentages |
| Headline numbers | Geist with `.tabular`, `font-semibold tracking-tight` | The two score percentages and other single big figures |

Sizes: body `text-sm` (14px), secondary `text-[13px]`, meta `text-xs` (12px), micro `text-[11px]` for tags only. Section headings `text-sm font-medium` (sans) or `.display text-xl` for a page-level title. No uppercase tracked-out eyebrows.

## Colour tokens (`src/index.css`, light and `.dark`)
- Surfaces: `--bg-canvas` (page), `--bg-surface` (cards), `--bg-subtle` (wells, tracks), `--bg-hover` (row hover).
- Text: `--fg-primary`, `--fg-secondary`, `--fg-muted`.
- Lines: `--border-subtle` (default), `--border-strong` (inputs, hover).
- `--accent` (indigo): links, focus, active state, the single-actor series. `--indigo` (violet): the coordinated series.
- `--teal`: protective/metadata (wire agency, supported claim). `--caution`: documented network, capped language, uncalibrated weights. `--danger`: failed stage or request only.
- `--mark` / `--mark-strong`: highlighter for verbatim passages in the document and quotes.
- Primary buttons are ink (`--btn-primary-*`), not accent.

## Shape and depth
- Radius: cards `rounded-xl`, buttons/inputs `rounded-lg`, tags `rounded-md`, favicons 4px. No `rounded-3xl`; `rounded-full` only for dots and avatars.
- Borders over shadows: cards use `.editorial-card` (1px border, hairline shadow). Popovers `.glass-popover`. Sticky chrome `.glass-panel`.
- Spacing: 4px grid; card padding `p-4 sm:p-5`; vertical rhythm `space-y-6` between page sections.

## Shared building blocks
- `buttonClass(variant, size)` and `tagClass(tone, {mono})` in `src/lib/ui.ts`; never hand-roll button or tag classes.
- `<Favicon domain>` / `<FaviconStack domains>` (`components/ui/Favicon.tsx`) next to every outlet domain.
- `<AnimatedNumber value format>` for headline numbers that should count up once.
- `data-spotlight` on a bordered surface: the border and surface light up under the pointer (one global listener in `AppShell`). Use on interactive cards only (input, presets, source rows), not on every block.
- `.shimmer` on text that names work in progress ("Searching other coverage"); `.live-dot` for a running indicator; `.progress-indeterminate` for an unknown-length bar.

## Motion
- Enter: opacity + 4–8px rise, `GENTLE_SPRING`/`SPATIAL_SPRING` (`src/lib/motion.ts`); lists stagger 30–50ms.
- Effects only on transform/opacity; the backdrop glow follows the pointer through `transform` with a lag.
- `prefers-reduced-motion` disables animations, the cursor glow and spotlight.

## Invariants
- Slice `document.paragraphs` by code points (`sliceCodePoints` / `segmentParagraph` in `src/lib/spans.ts`), never `String.prototype.slice`.
- SSE: named listeners for `snapshot`, `queue`, `step`, `done` (`useAnalysisStream.ts`); close on `done`.
- Never invent metrics: `/metrics` shows "not published yet" while `/api/metrics` is 404.
