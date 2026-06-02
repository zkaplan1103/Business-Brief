---
tags: [data]
---
# Data Engineer memory

## 2026-06-02 — Phase 0 dataset decision

**Status: PENDING MANUAL DOWNLOAD — pause point before Phase 1**

The Yelp Open Dataset requires manual registration and download from
https://www.yelp.com/dataset. It cannot be downloaded programmatically.

**To unblock Phase 1:**
1. Go to https://www.yelp.com/dataset and register/download.
2. Place the extracted files in `data/raw/yelp/` (git-ignored).
3. Key files needed: `yelp_academic_dataset_review.json`,
   `yelp_academic_dataset_business.json`.
4. Confirm license: Yelp Open Dataset is for academic/non-commercial use.
   Record the license URL and confirmation in `docs/memory/00-decisions.md`.

**Alternative:** Amazon Reviews 2023 (McAuley Lab) via Hugging Face
(`McAuley-Lab/Amazon-Reviews-2023`) — accessible programmatically via
`datasets` library. Tradeoff: must reframe "business" as "product seller."

**Schema (target — from CONTRACTS §1):**
review_id, business_id, business_name, stars, text, date, week

The data-engineer normalizes raw Yelp JSON into this shape as reviews.jsonl.
