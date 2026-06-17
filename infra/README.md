# BizBrief — Serverless deployment (AWS SAM)

An event-driven serverless version of the BizBrief pipeline. Dropping a review
file into S3 triggers the full **ingest → analyze → brief** chain on Lambda,
persisting to DynamoDB and rendering the brief JSON back to S3, with cost /
latency / throughput published to a live CloudWatch dashboard.

> **Status: deployable, not deployed.** This is real, complete IaC + handler
> code. It has not been `sam deploy`'d to a live account (running it incurs AWS
> + Anthropic charges). Everything here is structured so it *would* deploy and
> run as-is once an account and credentials are supplied.

## Architecture

```
            ┌─────────────────────────────────────────────────────────────┐
            │                         AWS account                          │
            │                                                              │
  s3://raw/uploads/<biz>/<week>.jsonl                                      │
            │            │ S3 ObjectCreated event                          │
            │            ▼                                                 │
            │     ┌──────────────┐   invoke    ┌──────────────┐   invoke   │
            │     │ IngestLambda │ ──────────▶ │ AnalyzeLambda│ ─────────┐ │
            │     └──────┬───────┘  (Event)    └──────┬───────┘  (Event)  │ │
            │            │ put_reviews                │ put_theme_report  ▼ │
            │            ▼                            ▼          ┌──────────┐
            │     ┌───────────────────────────────────────┐     │BriefLambda│
            │     │            DynamoDB  (bizbrief)         │◀────┴────┬─────┘
            │     │  BIZ#<id> | REVIEW#/THEMES#/BRIEF#<week>│  put_brief│
            │     └───────────────────────────────────────┘           │
            │                                                          ▼
            │                                   s3://briefs/<biz>/<week>.brief.json
            │                                                          │
            │   all 3 Lambdas ── put_metric_data ──▶ CloudWatch ◀── Dashboard
            │   failed async invokes ──────────────▶ SQS dead-letter queue
            └─────────────────────────────────────────────────────────────┘
```

The model router, prompt caching, retry/backoff, cost ceiling and idempotency
cache are **not reimplemented** — the Lambdas import the existing `pipeline/`
and `reliability/` modules, so every cost and reliability property of the local
build carries over unchanged. `lambdas/storage.py` is the only new seam: it
swaps the local JSONL/file world for S3 + DynamoDB.

## Files

| File | Role |
|---|---|
| `template.yaml` | SAM template: 3 functions, S3 trigger, DynamoDB table, SQS DLQ, IAM, CloudWatch dashboard |
| `lambdas/handler_ingest.py` | S3-event-triggered: normalize upload → DynamoDB → invoke analyze |
| `lambdas/handler_analyze.py` | Router + classify loop on DynamoDB reviews → ThemeReport → invoke brief |
| `lambdas/handler_brief.py` | ThemeReport → Brief → DynamoDB + briefs bucket |
| `lambdas/storage.py` | S3 + DynamoDB adapter (single-table design, key helpers) |
| `lambdas/metrics.py` | CloudWatch custom-metric emitter (cost / latency / throughput / cache) |
| `events/*.json` | Sample events for `sam local invoke` |
| `Makefile` | `build`, `local-ingest`, `local-analyze`, `validate`, `deploy`, `delete` |

## DynamoDB single-table design

One table, `bizbrief-<stage>`, on-demand billing (scales to zero — no idle cost):

| PK | SK | Item |
|---|---|---|
| `BIZ#<business_id>` | `REVIEW#<week>#<review_id>` | a normalized Review |
| `BIZ#<business_id>` | `THEMES#<week>` | a ThemeReport |
| `BIZ#<business_id>` | `BRIEF#<week>` | a Brief |

Each access pattern is a single query: all reviews for a business+week is one
`begins_with(SK, "REVIEW#<week>#")`; the report and brief are point reads.

## Run it locally (no AWS account needed)

There are two ways to run the handlers without a real AWS account.

### Option A — full end-to-end on mock AWS (recommended, no Docker)

Runs the entire **ingest → analyze → brief** chain against in-process mocks of
S3 + DynamoDB ([moto]). This exercises the exact handler code and is the
fastest way to prove the pipeline works. The analyze stage calls Claude, so it
needs `ANTHROPIC_API_KEY` (set in the repo `.env`); reruns hit the idempotency
cache and are free.

```bash
# one-time: install the mock-AWS deps
uv sync --group local-aws

cd infra
make local-e2e                                          # default business/week
make local-e2e ARGS="--business B007IAE5WY --week 2017-W38"
```

Under the hood this runs [`infra/local_run.py`](local_run.py): it creates the
mock bucket + table (same schema as `template.yaml`), drops a real review file
into the mock raw bucket, then invokes `handler_ingest` → `handler_analyze` →
`handler_brief` in sequence, and verifies the rendered brief lands in the mock
briefs bucket. The integration is covered by `tests/test_serverless_storage.py`.

### Option B — single handler in a Lambda container (needs Docker + SAM CLI)

Requires Docker running and the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html).

```bash
cd infra
make validate          # lint the template
make local-analyze     # invoke AnalyzeFunction against events/analyze.json
```

`sam local invoke` runs one handler in a Lambda-like container. Its storage
calls hit real S3/DynamoDB, so without credentials it builds + boots the handler
(proving packaging) but errors at the first AWS call. Use Option A for a full
offline run.

[DynamoDB Local]: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.html
[moto]: https://github.com/getmoto/moto

## Deploy it (incurs charges)

```bash
cd infra
make deploy            # sam build && sam deploy --guided
# Prompts for stack name, region, and AnthropicApiKey (NoEcho).
```

Then trigger the pipeline by uploading a file:

```bash
aws s3 cp data/processed/B007IAE5WY_2017-W38.jsonl \
    s3://$(aws cloudformation describe-stacks --stack-name bizbrief \
      --query "Stacks[0].Outputs[?OutputKey=='RawBucketName'].OutputValue" \
      --output text)/uploads/B007IAE5WY/2017-W38.jsonl
```

The brief lands in the briefs bucket within seconds; the dashboard URL is in the
stack outputs (`DashboardURL`). Tear down with `make delete`.

## Cost & safety notes

- **DynamoDB on-demand + Lambda + S3 all scale to zero** — an idle stack costs
  effectively nothing; you pay per request and per GB-second.
- **The real variable cost is Anthropic inference**, governed by the same model
  router + prompt caching + per-run cost ceiling as the local build.
- **Email stays draft-only** in the cloud path exactly as locally — nothing is
  auto-sent (CONTRACTS §5).
- **Least-privilege IAM**: each function gets only the policies it needs
  (ingest can't write briefs; brief can't read the raw bucket).
