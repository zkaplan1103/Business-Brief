# STYLE.md — concrete art direction (FROZEN Phase 0, 2026-06-02)

> Produced in Phase 0. The `ui-engineer` CONSUMES this file — it does not invent
> the aesthetic. Do not change values here without editing this file first and
> logging the change in `docs/memory/00-decisions.md`.

---

## Committed direction

- **Direction:** Warm Premium Hospitality — the brief reads like a beautifully
  typeset report from an advisor who knows the owner's world.
- **Why it fits this audience:** The primary user is a small-business owner in
  food, retail, or services — the exact verticals Yelp covers. A hospitality
  register signals "this was made for your world" and builds trust faster than a
  cold utilitarian tool. The warm palette pairs naturally with severity/trend tokens
  (red/green read intuitively against warm neutrals).
- **The one memorable thing:** Cormorant Garamond headlines over a warm ivory
  surface — it reads like a premium report, not a generic dashboard.

---

## Typography

- **Display / headline + big numbers:** Cormorant Garamond (Google Fonts —
  SemiBold 600 for headlines, Regular 400 Italic for pull-quotes and emphasis)
- **Body / UI text:** Figtree (Google Fonts — Regular 400, Medium 500, SemiBold 600)
- **Monospace (data labels, IDs, week strings):** DM Mono (Google Fonts — Regular 400)
- **Type scale (px):** 11 / 13 / 15 / 18 / 24 / 32 / 48 / 64
- **Line height:** display 1.1, body 1.55, UI labels 1.3
- **Letter spacing:** display headlines −0.02em; UI labels +0.04em uppercase

---

## Color tokens (define as CSS vars / Tailwind theme)

```
--bg:           #FAF8F4   warm ivory page background
--surface:      #FFFFFF   card / panel surface
--surface-2:    #F3F0EB   recessed / input background
--border:       #E4DDD3   subtle dividers
--text:         #1C1612   espresso — primary text
--text-muted:   #7A6E64   secondary / meta text

--brand:        #C0694A   terracotta — dominant
--accent-1:     #2C5F4A   forest green — positive trend / CTA
--accent-2:     #E8A23A   warm amber — highlight / partial badge

--sev-high:     #BF3B2F   deep red
--sev-medium:   #C0694A   terracotta (= brand)
--sev-low:      #7A8C6A   muted sage

--trend-up:     #2C5F4A   forest green
--trend-down:   #BF3B2F   deep red
--trend-flat:   #7A6E64   muted warm grey

--focus-ring:   #C0694A40 brand at 25% opacity
--partial-bg:   #FEF3E2   amber tint for partial-data banner
```

Dominant-with-accents: `--brand` carries the UI; `--accent-1` and `--accent-2`
are used sparingly. No evenly-distributed palette.

---

## Spacing, radius, elevation

- **Spacing scale (px):** 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96
- **Radius:** `--radius: 6px` — one token, used everywhere. Not pill, not sharp.
- **Elevation / atmosphere:**
  - Cards: `box-shadow: 0 1px 3px rgba(28,22,18,0.08), 0 0 0 1px var(--border)`
  - Elevated panels (schedule drawer, email draft card):
    `0 4px 16px rgba(28,22,18,0.10), 0 0 0 1px var(--border)`
  - `--bg` (#FAF8F4) vs white `--surface` creates depth without a texture asset.
  - No flat grey cards — every surface lifts via shadow + border.

---

## Motion personality

- **Load (staggered reveal):** Action items enter top-priority-first.
  Each card: `opacity 0→1, translateY +12px→0`, duration `0.35s`, ease `easeOut`,
  stagger `0.07s` between items. Trend indicator delays until cards settle.
- **Trend indicator:** Number counts up from 0 to final value over `0.6s`
  (`easeOutExpo`); directional arrow slides in from opposite direction `0.3s` after.
- **Hover (evidence / action items):** shadow deepens + `translateY −2px`,
  transition `0.15s easeOut`. No color flash. Restrained — a tool, not a toy.
- **Schedule save:** button label transitions "Save" → checkmark → "Saved"
  over `0.4s`; no confetti.

---

## Light / dark

- **Default theme: light.** The warm ivory `--bg` is the designed surface.
  Dark mode is not in scope for v1.
