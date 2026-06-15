// Fixture data for Phase 1 UI development.
// Components build against these shapes; Phase 2 swaps in the real API.

import type { Brief, ThemeReport, ScheduleSettings, RunRecord, BusinessMeta, EvalData } from './types'

export const FIXTURE_BUSINESS: BusinessMeta = {
  business_id: 'biz_goldenharvest',
  business_name: 'Golden Harvest Café',
  weeks: ['2024-W28', '2024-W29', '2024-W30', '2024-W31'],
}

export const FIXTURE_THEME_REPORT: ThemeReport = {
  business_id: 'biz_goldenharvest',
  week: '2024-W31',
  review_count: 42,
  avg_stars: 3.8,
  prev_avg_stars: 4.1,
  sufficient: true,
  partial: false,
  themes: [
    {
      theme_id: 'th_slow_service',
      label: 'Slow service at peak hours',
      sentiment: 'negative',
      review_ids: ['r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7'],
      count: 7,
      sample_quotes: [
        'Waited 25 minutes for a coffee on a Saturday morning.',
        'Staff seemed overwhelmed during the lunch rush.',
        'Love the food but the wait times are killing it for me.',
      ],
    },
    {
      theme_id: 'th_food_quality',
      label: 'Inconsistent food quality',
      sentiment: 'mixed',
      review_ids: ['r8', 'r9', 'r10', 'r11', 'r12'],
      count: 5,
      sample_quotes: [
        'The avocado toast was perfect last week, soggy this time.',
        "Hit or miss depending on who's in the kitchen.",
      ],
    },
    {
      theme_id: 'th_ambiance',
      label: 'Cozy, welcoming atmosphere',
      sentiment: 'positive',
      review_ids: ['r13', 'r14', 'r15', 'r16', 'r17', 'r18'],
      count: 6,
      sample_quotes: [
        'Best little corner to work from in the neighborhood.',
        'The warm lighting and plants make it feel like home.',
        'Always come back for the vibe.',
      ],
    },
    {
      theme_id: 'th_wifi',
      label: 'Unreliable WiFi',
      sentiment: 'negative',
      review_ids: ['r19', 'r20', 'r21'],
      count: 3,
      sample_quotes: [
        "WiFi drops every 20 minutes — can't get work done.",
        'Password works once, then nothing.',
      ],
    },
  ],
}

export const FIXTURE_BRIEF: Brief = {
  business_id: 'biz_goldenharvest',
  business_name: 'Golden Harvest Café',
  week: '2024-W31',
  summary:
    'This week saw a dip in average rating from 4.1 to 3.8 stars. Service speed during peak hours and food consistency are your two most actionable issues — fixing either would directly recover lost stars. The ambiance is a genuine differentiator; protect it.',
  trend: 'down',
  partial: false,
  generated_by: 'claude-haiku-4-5-20251001',
  email_draft:
    `Hi [Owner],\n\nYour BizBrief brief for the week of July 29 – Aug 4, 2024 is ready.\n\nThe headline: your rating dipped from 4.1 → 3.8 this week. Seven reviewers flagged slow service at peak hours as the main driver. A simple staffing tweak on weekend mornings could recover this quickly.\n\nYour top three actions:\n1. Add one staff member to the floor on Sat/Sun 9–11am.\n2. Standardize the avocado toast prep with a laminated spec card.\n3. Contact your ISP about the WiFi drops — several remote workers mentioned it.\n\nThe full brief with evidence is in your dashboard.\n\nBest,\nBizBrief`,
  action_items: [
    {
      rank: 1,
      theme_id: 'th_slow_service',
      headline: 'Peak-hour service is losing you stars',
      why_it_matters:
        '7 reviews this week cited long waits. Slow service has the highest impact on ratings in food & bev and is directly fixable.',
      recommended_action:
        'Schedule one additional staff member on Saturday and Sunday mornings (9–11am) for the next two weekends and track if wait complaints drop.',
      evidence_review_ids: ['r1', 'r2', 'r3', 'r4', 'r5'],
      severity: 'high',
    },
    {
      rank: 2,
      theme_id: 'th_food_quality',
      headline: 'Inconsistent dishes erode repeat visits',
      why_it_matters:
        '5 reviewers noted quality varying by visit. Inconsistency breaks the trust that drives repeat customers.',
      recommended_action:
        'Create a one-page prep spec for your top 3 selling items. Post it in the kitchen and have staff sign off daily.',
      evidence_review_ids: ['r8', 'r9', 'r10'],
      severity: 'medium',
    },
    {
      rank: 3,
      theme_id: 'th_wifi',
      headline: 'WiFi drops are alienating your remote-worker regulars',
      why_it_matters:
        'Remote workers are a reliable weekday revenue base. Repeated WiFi failures send them to competitors.',
      recommended_action:
        'Call your ISP and request a line check. If the issue persists, consider a mesh extender (~$80) to stabilize coverage.',
      evidence_review_ids: ['r19', 'r20', 'r21'],
      severity: 'low',
    },
  ],
}

export const FIXTURE_SCHEDULE: ScheduleSettings = {
  business_id: 'biz_goldenharvest',
  cadence: 'weekly',
  day_of_week: 'mon',
  email_mode: 'draft_only',
}

export const FIXTURE_RUNS: RunRecord[] = [
  {
    run_id: 'run_001',
    business_id: 'biz_goldenharvest',
    week: '2024-W31',
    status: 'success',
    started_at: '2024-08-05T07:00:00Z',
    finished_at: '2024-08-05T07:02:14Z',
    total_cost_usd: 0.043,
    batches_total: 5,
    batches_failed: 0,
    note: null,
  },
  {
    run_id: 'run_000',
    business_id: 'biz_goldenharvest',
    week: '2024-W30',
    status: 'partial',
    started_at: '2024-07-29T07:00:00Z',
    finished_at: '2024-07-29T07:03:01Z',
    total_cost_usd: 0.038,
    batches_total: 5,
    batches_failed: 1,
    note: '1/5 batches failed after retries; brief produced from 4 batches',
  },
]

// Offline fallback for the Eval tab — mirrors eval/results.json so the tab
// renders without the API. Real numbers from the live 3-model scored run.
export const FIXTURE_EVAL: EvalData = {
  available: true,
  business_id: 'B007IAE5WY',
  week: '2017-W38',
  business_name: 'Salux Nylon Japanese Beauty Skin Bath Wash Cloth/towel',
  review_count: 17,
  golden_themes: 5,
  note: 'Quality-vs-cost comparison from the live 3-model eval. Costs are first-run charges (reruns hit the idempotency cache at $0). Golden set signed off by owner.',
  generated_at: '2026-06-15',
  rows: [
    { model: 'claude-haiku-4-5-20251001', label: 'Haiku', cost_usd: 0.004541, label_f1: 0.6000, label_precision: 0.6000, label_recall: 0.6000, evidence_overlap: 0.8167, sentiment_accuracy: 1.0, matched_themes: 3, total_golden_themes: 5 },
    { model: 'claude-sonnet-4-6', label: 'Sonnet', cost_usd: 0.016911, label_f1: 0.1818, label_precision: 0.1667, label_recall: 0.2000, evidence_overlap: 1.0, sentiment_accuracy: 1.0, matched_themes: 1, total_golden_themes: 5 },
    { model: 'claude-opus-4-8', label: 'Opus', cost_usd: 0.089985, label_f1: 0.5000, label_precision: 0.4286, label_recall: 0.6000, evidence_overlap: 0.9259, sentiment_accuracy: 1.0, matched_themes: 3, total_golden_themes: 5 },
  ],
}
