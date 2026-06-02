# DESIGN.md — the UI contract (frozen in Phase 0)

The dashboard is the product surface a small-business owner touches, so it must
look **intentionally designed**, not generic AI/SaaS. This file is the brief and
the discipline; the concrete art direction (fonts, palette, tokens) lives in
`docs/STYLE.md`, decided in Phase 0. Freeze this in Phase 0.

## Audience & job-to-be-done
A busy, non-technical small-business owner, glancing on a laptop or phone between
shifts. They need to grasp **"is this week better or worse, and what should I do
about it"** in ~15 seconds, then optionally read deeper. Clarity and trust beat
cleverness. Density is fine *if* well-organized; confusion is not.

## Aesthetic direction — comes from STYLE.md (do not invent it here)
The concrete art direction is decided in **Phase 0** and frozen in `docs/STYLE.md`.
The ui-engineer **consumes** STYLE.md; it does not pick fonts/colors at build time.
Art direction is a reviewable *decision* (Phase 0); building screens is *execution*
(Phase 1).

The discipline STYLE.md must satisfy (enforced when it's written):
- A clear, characterful point of view from the trustworthy-but-distinctive end (editorial/print-report, refined-utilitarian, warm-premium-hospitality) — NOT playful-toy, NOT maximalist-chaos, NOT default SaaS.
- No generic AI aesthetics: **no Inter / Roboto / Arial / system fonts**, do **not** default to Space Grotesk, no purple-gradient-on-white cliché.
- No undifferentiated dashboard-template look (evenly spaced cards, timid grey palette, no point of view).

## Tokens (defined in STYLE.md — apply them, don't redefine)
STYLE.md fixes the color ramp, semantic severity/trend tokens, the display/body
type pairing, the spacing scale, radius, and elevation. In Phase 1, wire those into
CSS variables / the Tailwind theme and use them **exclusively** — no hard-coded hex,
no one-off spacing, no fonts outside STYLE.md.

## Motion (React + Motion library)
One well-orchestrated load beats scattered micro-interactions:
- Staggered reveal of the brief's action items on load (highest priority first).
- A satisfying trend indicator animating in.
- Restrained hover on interactive evidence. Tasteful — a tool, not a toy.

## Required screens / components
1. **Header bar** — business selector + week selector + the headline verdict (avg stars this week, trend vs last week) made *visually unmissable*.
2. **The brief** — ranked action items as the centerpiece. Each: severity tag (severity tokens), headline, why-it-matters, recommended action, and an expandable **evidence** drawer with supporting review quotes. Priority obvious from visual weight, not just a number.
3. **Theme overview** — a real data-viz of the week's themes (counts + sentiment). recharts is fine but restyle it to the chosen aesthetic — no default chart look.
4. **Trend** — avg-stars this week vs prior, as a small sparkline/delta, not a paragraph.
5. **Email draft** — the optional drafted email in a copy-ready card with a copy button.
6. **Schedule settings** — a panel for cadence (weekly/biweekly/off), day of week, and email mode (auto-send vs. draft-only), wired to the `ScheduleSettings` contract with a clear save state. This is what makes the product *recurring*. Real care, kept simple.
7. **Run status** — a small surface (reads `RunRecord`s) showing the last run's status (success/partial/failed) and when the next is due, so a failed automated run is visible, not silent. A "based on partial data" flag when `Brief.partial` is true.
8. **Empty/sparse state** — when `ThemeReport.sufficient` is False, a designed, friendly "not enough reviews this week to call it" state. First-class, not an error.

## Quality bar
- Responsive: reads well on phone and laptop.
- Accessibility floor: real contrast ratios, focus states, semantic HTML, aria where needed. Trust depends on it.
- Builds against fixture `Brief` + `ThemeReport` + `ScheduleSettings` + `RunRecord` JSON, then switches to the API seam at integration with no component changes.

The test: a stranger shown the dashboard for 15 seconds can say what kind of week
the business had and what the owner should do first.
