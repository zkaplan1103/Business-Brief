"""
Build the simulated data behind the static demo (web/src/demo-data.json).

Everything here is invented. The businesses are fictional, every review id is
made up, and no model or API is called. The output matches the API responses in
docs/CONTRACTS.md section 6 and web/src/types.ts, so the dashboard renders it
exactly as it would render live data.

The script is deterministic. Rerun it after editing the tables below:

    uv run python scripts/make_demo_data.py
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "src" / "demo-data.json"
WEEKS = [f"2026-W{n}" for n in range(40, 46)]
MIN_REVIEWS = 5        # Config.min_reviews_for_brief in CONTRACTS.md section 4
STARS = {"positive": 4.7, "mixed": 3.3, "negative": 1.9}
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
HAIKU, SONNET, OPUS = "claude-haiku-4-5-20251001", "claude-sonnet-4-6", "claude-opus-4-8"

# Each theme: label, sentiment, review count per week (one per WEEKS entry),
# quotes, and for negative or mixed themes the action the brief recommends.
BUSINESSES = [
    {
        "id": "demo-fernhollow-bakery",
        "name": "Fernhollow Bakery",
        "schedule": ("weekly", "mon"),
        "partial_weeks": {"2026-W43"},
        "themes": [
            ("Long waits at the weekend counter", "negative", [3, 5, 7, 6, 3, 2], [
                "Twenty minutes in line for two croissants on Saturday.",
                "The weekend queue goes out the door and barely moves.",
                "Love the bread but I can't wait this long every Sunday.",
                "Only one person at the till during the morning rush.",
            ], ("Weekend lines are costing you regulars",
                "Wait complaints are the most common negative theme, and they cluster on Saturday and Sunday mornings.",
                "Put a second person on the register from 8 to 11am Saturday and Sunday for the next two weekends.",
                "high")),
            ("Pastries sell out before noon", "mixed", [2, 3, 4, 4, 3, 2], [
                "Almond croissants were gone by 10am again.",
                "Great selection early, empty shelves by lunch.",
                "Came at 11 and half the case was sold out.",
            ], ("Popular pastries run out too early",
                "Customers who arrive late leave without buying, and some say they won't come back.",
                "Double the almond croissant bake on weekends and post a sold out sign online before people make the trip.",
                "medium")),
            ("Excellent sourdough and croissants", "positive", [8, 9, 7, 8, 10, 11], [
                "Best sourdough in town. The crust is perfect.",
                "The croissants are flaky and buttery every time.",
                "Worth the drive for the country loaf alone.",
            ], None),
            ("Warm, friendly staff", "positive", [4, 4, 3, 4, 5, 6], [
                "The staff remember my order and always say hello.",
                "Friendly team even when it's packed.",
            ], None),
            ("Online orders not ready on time", "negative", [0, 1, 3, 2, 1, 0], [
                "Ordered ahead online and they hadn't started it.",
                "Pickup time came and went, still waited ten minutes.",
            ], ("Online pickup times are slipping",
                "Pre-orders are your most loyal customers. A missed pickup time undoes the reason they ordered ahead.",
                "Print online orders on a separate ticket rail and start them 15 minutes before the pickup time.",
                "medium")),
        ],
    },
    {
        "id": "demo-gearloop-bikes",
        "name": "Gearloop Bike Repair",
        "schedule": ("weekly", "tue"),
        "partial_weeks": set(),
        "themes": [
            ("Repairs take longer than quoted", "negative", [4, 4, 5, 3, 2, 2], [
                "Quoted two days, got my bike back after a week.",
                "Nobody called to say the part was delayed.",
                "Good work but the turnaround keeps slipping.",
            ], ("Turnaround times keep slipping",
                "Missed promise dates are the most common complaint and the easiest to fix with communication.",
                "Text every customer the day a quote will slip, with the new date, before they have to ask.",
                "high")),
            ("Honest, knowledgeable mechanics", "positive", [6, 5, 7, 6, 8, 7], [
                "They told me I didn't need the part the other shop quoted.",
                "Explained the whole repair and showed me the worn chain.",
                "Finally a shop that doesn't upsell.",
            ], None),
            ("Prices higher than expected", "mixed", [2, 3, 2, 3, 2, 3], [
                "Fair work but the labor rate surprised me.",
                "A bit pricey for a basic tune up.",
            ], ("Price surprises at pickup",
                "Customers accept the price when they see it up front and resent it when they don't.",
                "Post the three most common service prices at the counter and on the website this week.",
                "medium")),
            ("Hard to reach by phone", "negative", [1, 2, 2, 3, 1, 1], [
                "Called four times, nobody picked up.",
                "Voicemail is full every time I try.",
            ], ("Phone calls go unanswered",
                "Callers who can't get through assume the shop is closed and go elsewhere.",
                "Clear the voicemail and set a message that points to online booking and texting.",
                "low")),
        ],
    },
    {
        "id": "demo-saltmarsh-yoga",
        "name": "Saltmarsh Yoga Studio",
        "schedule": ("biweekly", "sun"),
        "partial_weeks": set(),
        "themes": [
            ("Calm space and great teachers", "positive", [5, 6, 2, 5, 6, 7], [
                "The evening flow class is the best part of my week.",
                "Teachers give real adjustments, not just cues.",
                "Beautiful light in the main room.",
            ], None),
            ("Classes overbooked", "negative", [3, 4, 1, 4, 3, 2], [
                "Mats were six inches apart in the 6pm class.",
                "Booked a spot and there was no room when I arrived.",
                "Too crowded to do a full sun salutation.",
            ], ("Peak classes are overcrowded",
                "Crowding is the top complaint from members, and the ones who mention it rate the studio lowest.",
                "Cap the 6pm class at 22 mats and open a waitlist in the booking app.",
                "high")),
            ("Changing room needs attention", "mixed", [1, 2, 0, 2, 2, 1], [
                "Showers are great but the lockers are always broken.",
                "Changing room gets messy by the evening.",
            ], ("Changing room upkeep",
                "It is not driving cancellations yet, but it comes up every week.",
                "Add a mid-afternoon clean to the staff checklist and replace the two broken lockers.",
                "low")),
        ],
    },
    {
        "id": "demo-copperpot-diner",
        "name": "Copperpot Diner",
        "schedule": ("weekly", "mon"),
        "partial_weeks": set(),
        "themes": [
            ("Hearty breakfast, generous portions", "positive", [7, 6, 8, 7, 7, 8], [
                "Pancakes the size of the plate.",
                "Best hash browns in the neighborhood.",
                "Huge portions for the price.",
            ], None),
            ("Cold food at busy times", "negative", [2, 3, 3, 4, 5, 3], [
                "Eggs came out lukewarm on Sunday.",
                "Food sat at the pass while servers were swamped.",
                "My coffee went cold before the food arrived.",
            ], ("Food is reaching tables cold",
                "Lukewarm plates are the top complaint at weekend brunch, the diner's busiest service.",
                "Add heat lamps at the pass and have the expo call runners when a ticket is up for over a minute.",
                "high")),
            ("Friendly, fast servers", "positive", [4, 5, 4, 3, 4, 5], [
                "Our server kept the coffee coming without asking.",
                "Fast and friendly even on a packed Saturday.",
            ], None),
            ("Noisy dining room", "mixed", [1, 1, 2, 2, 2, 1], [
                "Great food, but we couldn't hear each other talk.",
                "Gets very loud during brunch.",
            ], ("Brunch noise level",
                "Some guests say they won't bring family back because it is too loud to talk.",
                "Turn the music down during brunch and try felt pads under the chairs.",
                "low")),
        ],
    },
]


def week_monday(week: str) -> date:
    year, wk = week.split("-W")
    return date.fromisocalendar(int(year), int(wk), 1)


def slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text.lower()).strip("_")[:40]


def build_week(biz: dict, wi: int, prev_avg: float | None) -> tuple[dict, dict]:
    week = WEEKS[wi]
    themes, n_reviews, star_sum = [], 0, 0.0
    for ti, (label, sentiment, counts, quotes, _) in enumerate(biz["themes"]):
        count = counts[wi]
        if not count:
            continue
        ids = [f"{biz['id']}-{week}-r{n_reviews + k + 1:02d}" for k in range(count)]
        n_reviews += count
        star_sum += STARS[sentiment] * count
        rotated = quotes[wi % len(quotes):] + quotes[:wi % len(quotes)]
        themes.append({
            "theme_id": f"theme_{ti:02d}_{slug(label)}", "label": label,
            "sentiment": sentiment, "review_ids": ids, "count": count,
            "sample_quotes": rotated[:3],
        })
    themes.sort(key=lambda t: -t["count"])
    avg = round(star_sum / n_reviews, 2)
    sufficient = n_reviews >= MIN_REVIEWS
    partial = week in biz["partial_weeks"]
    report = {
        "business_id": biz["id"], "week": week, "review_count": n_reviews,
        "avg_stars": avg, "prev_avg_stars": prev_avg,
        "themes": themes if sufficient else [], "sufficient": sufficient, "partial": partial,
    }
    trend = "flat" if prev_avg is None or abs(avg - prev_avg) <= 0.1 else ("up" if avg > prev_avg else "down")
    brief = {
        "business_id": biz["id"], "business_name": biz["name"], "week": week,
        "summary": "", "trend": trend, "action_items": [], "email_draft": None,
        "partial": partial, "generated_by": "simulated",
    }
    if not sufficient:
        brief["summary"] = (
            f"Not enough reviews this week to produce a meaningful brief "
            f"({n_reviews} received; {MIN_REVIEWS} required). "
            f"Check back next week once more feedback has come in."
        )
        return report, brief

    actions = {f"theme_{ti:02d}_{slug(t[0])}": t[4] for ti, t in enumerate(biz["themes"]) if t[4]}
    items = sorted(
        (t for t in themes if t["theme_id"] in actions),
        key=lambda t: (SEVERITY_ORDER[actions[t["theme_id"]][3]], -t["count"]),
    )[:5]
    for rank, t in enumerate(items, start=1):
        headline, why, action, severity = actions[t["theme_id"]]
        brief["action_items"].append({
            "rank": rank, "theme_id": t["theme_id"], "headline": headline,
            "why_it_matters": why, "recommended_action": action,
            "evidence_review_ids": t["review_ids"][:5], "severity": severity,
        })

    top_pos = next((t for t in themes if t["sentiment"] == "positive"), None)
    move = {"up": "up from", "down": "down from", "flat": "about level with"}[trend]
    opening = (f"{n_reviews} reviews came in this week, averaging {avg:.1f} stars"
               + (f", {move} {prev_avg:.1f} last week." if prev_avg is not None else "."))
    parts = [opening]
    if items:
        parts.append(f"The issue to fix first is {items[0]['label'].lower()}.")
    if top_pos:
        parts.append(f"Customers keep praising {top_pos['label'].lower()}, so protect that while you fix the rest.")
    brief["summary"] = " ".join(parts)

    if not partial and brief["action_items"]:
        lines = [f"{i['rank']}. {i['recommended_action']}" for i in brief["action_items"][:3]]
        brief["email_draft"] = (
            f"Subject: Your week at {biz['name']}\n\nHi [Name],\n\n{opening}\n\n"
            "This week's actions:\n" + "\n".join(lines)
            + "\n\nThe full brief with the review evidence is in your dashboard.\n\n— Your BizBrief"
        )
    return report, brief


def build() -> dict:
    out: dict = {"businesses": [], "briefs": {}, "schedules": {}, "runs": {}}
    calls = {HAIKU: 0, SONNET: 0, OPUS: 0}
    stage_calls = {"analyze": 0, "brief": 0}
    total_cost = 0.0
    for bi, biz in enumerate(BUSINESSES):
        out["businesses"].append({"business_id": biz["id"], "business_name": biz["name"], "weeks": WEEKS})
        out["briefs"][biz["id"]] = {}
        cadence, day = biz["schedule"]
        out["schedules"][biz["id"]] = {"business_id": biz["id"], "cadence": cadence,
                                       "day_of_week": day, "email_mode": "draft_only"}
        runs, prev_avg = [], None
        for wi, week in enumerate(WEEKS):
            report, brief = build_week(biz, wi, prev_avg)
            out["briefs"][biz["id"]][week] = {"brief": brief, "themeReport": report}
            prev_avg = report["avg_stars"]

            batches = max(1, math.ceil(report["review_count"] / 20)) if report["sufficient"] else 0
            failed = 1 if report["partial"] else 0
            # Analyze calls route mostly to Haiku. Every third one is harder.
            model = OPUS if (bi + wi) % 9 == 0 else SONNET if (bi + wi) % 3 == 0 else HAIKU
            if batches:
                calls[model] += batches - failed
                calls[HAIKU] += 1 if report["partial"] else 2   # brief + email draft
                stage_calls["analyze"] += batches - failed
                stage_calls["brief"] += 1 if report["partial"] else 2
            cost = {HAIKU: 0.0046, SONNET: 0.017, OPUS: 0.09}[model] * (batches - failed) + 0.003 * bool(batches)
            total_cost += cost
            start = datetime.combine(week_monday(week) + timedelta(days=7), datetime.min.time(),
                                     tzinfo=timezone.utc) + timedelta(hours=7)
            runs.append({
                "run_id": f"demo_{biz['id'][5:12]}_{week}",
                "business_id": biz["id"], "week": week,
                "status": "partial" if failed else "success",
                "started_at": start.isoformat().replace("+00:00", "Z"),
                "finished_at": (start + timedelta(seconds=40 + 9 * report["review_count"])).isoformat().replace("+00:00", "Z"),
                "total_cost_usd": round(cost, 4), "batches_total": batches, "batches_failed": failed,
                "note": f"{failed}/{batches} batches failed after retries; brief produced from {batches - failed}" if failed
                        else None if report["sufficient"]
                        else f"Insufficient reviews ({report['review_count']} < {MIN_REVIEWS}); no brief produced.",
            })
        out["runs"][biz["id"]] = runs[::-1]   # newest first, like GET /api/runs

    per_call = {HAIKU: (0.0046, 610, 1450, 3100, 900), SONNET: (0.017, 1480, 2900, 3300, 950),
                OPUS: (0.09, 3900, 6800, 3400, 1000)}
    by_model = {}
    for m, n in calls.items():
        cost, lat, p95, tin, tout = per_call[m]
        cache_read = 0 if m == HAIKU else 2274 * n
        by_model[m] = {
            "calls": n, "total_cost_usd": round(cost * n, 4), "avg_latency_ms": lat, "p95_latency_ms": p95,
            "total_input_tokens": tin * n, "total_output_tokens": tout * n,
            "cache_read_tokens": cache_read, "cache_creation_tokens": 0 if m == HAIKU else 2274,
            "prompt_cache_saved_usd": round(cache_read * (3.0 if m == SONNET else 15.0) * 0.9 / 1e6, 4),
        }
    total_calls = sum(calls.values())
    out["metrics"] = {
        "total_cost_usd": round(sum(v["total_cost_usd"] for v in by_model.values()), 4),
        "total_calls": total_calls,
        "by_model": by_model,
        "by_stage": {
            "analyze": {"calls": stage_calls["analyze"], "total_cost_usd": round(total_cost * 0.8, 4), "avg_latency_ms": 1240},
            "brief": {"calls": stage_calls["brief"], "total_cost_usd": round(total_cost * 0.2, 4), "avg_latency_ms": 820},
        },
        "routing_mix": {k: round(100 * calls[m] / total_calls, 1)
                        for k, m in (("haiku_pct", HAIKU), ("sonnet_pct", SONNET), ("opus_pct", OPUS))},
        "idempotency_skips": 37,
        "days_covered": 7 * len(WEEKS),
        "generated_at": "2026-11-16T07:00:00Z",
    }
    return out


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
