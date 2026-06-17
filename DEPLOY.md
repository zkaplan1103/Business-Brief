# BizBrief — AWS Production Deployment Guide

Deploy BizBrief as a real **event-driven serverless batch pipeline** on AWS:
drop a review file in **S3** → a **Lambda** chain (ingest → analyze → brief)
classifies themes with Claude and writes results to **DynamoDB** + S3, with a
**live CloudWatch dashboard** tracking cost, latency, and throughput.

This is the guide that makes the résumé bullet literally true. After following
it you will have running cloud infrastructure, a dashboard URL, and brief JSON
objects produced by Lambda — not a local mock.

> ⚠️ **This deploys real, billable AWS infrastructure and calls the Anthropic
> API.** Costs are small (see [§8](#8-cost-expectations)) but nonzero. Tear down
> with `make delete` when done ([§9](#9-teardown)).

Everything below is verified against `infra/template.yaml` on `main`. The
template passes `sam validate --lint` (AWS's own linter), the pipeline code
vendors and imports cleanly into the Lambda package, and the handlers have been
run end-to-end against mock S3 + DynamoDB. The one thing only *you* can do is
the real `sam build` + `sam deploy` against your AWS account (needs Docker +
credentials + spend) — that's §4–§5.

---

## Architecture

```
  s3://<raw>/uploads/<business_id>/<week>.jsonl
         │  S3:ObjectCreated event
         ▼
   ┌──────────────┐  async invoke  ┌───────────────┐  async invoke  ┌─────────────┐
   │ IngestLambda │ ─────────────▶ │ AnalyzeLambda │ ─────────────▶ │ BriefLambda │
   └──────┬───────┘                └───────┬───────┘                └──────┬──────┘
          │ put reviews                    │ put ThemeReport               │ put Brief
          ▼                                ▼                               ▼
   ┌──────────────────────── DynamoDB (single table: bizbrief-<stage>) ───────────┐
   │  PK=BIZ#<id>  SK=REVIEW#<week>#<id> | THEMES#<week> | BRIEF#<week>            │
   └──────────────────────────────────────────────────────────────────────────────┘
          │ rendered brief JSON                              all 3 → CloudWatch metrics
          ▼                                                  failed invokes → SQS DLQ
   s3://<briefs>/<business_id>/<week>.brief.json
```

**What's defined in `infra/template.yaml`:** 3 Lambda functions, the S3 trigger,
the DynamoDB table (on-demand), an SQS dead-letter queue, least-privilege IAM
per function, and a 4-widget CloudWatch dashboard. The Lambdas import the same
`pipeline/` + `reliability/` code as the local app, so the **model router,
prompt caching, retry/backoff, cost ceiling, and idempotency cache all carry
over to the cloud unchanged**.

---

## 1. Prerequisites

| Tool | Why | Install |
|---|---|---|
| **AWS account** | hosts the stack | https://aws.amazon.com |
| **AWS CLI v2** | credentials + S3 upload | `brew install awscli` |
| **AWS SAM CLI** | build + deploy | `brew install aws-sam-cli` |
| **Docker** | `sam build` compiles deps in a Lambda-like container | https://docker.com |
| **uv** | vendors the pipeline code before build | already installed for the app |
| **Anthropic API key** | analyze/brief call Claude | https://console.anthropic.com |

Verify:

```bash
aws --version        # aws-cli/2.x
sam --version        # SAM CLI 1.x
docker info          # must be running
```

---

## 2. Configure AWS credentials

You need an IAM identity with permission to create the stack's resources
(CloudFormation, Lambda, S3, DynamoDB, SQS, CloudWatch, IAM roles).

```bash
aws configure
# AWS Access Key ID:     <your key>
# AWS Secret Access Key: <your secret>
# Default region name:   us-east-1        # or your preferred region
# Default output format: json

# Confirm it works and note your account ID:
aws sts get-caller-identity
```

> **IAM scope:** for a personal project, an admin or PowerUser identity is
> simplest. For a locked-down account, the deployer needs `cloudformation:*`
> plus create/update/delete on the resource types above. SAM creates the
> per-function execution roles for you (least-privilege, defined in the template).

---

## 3. How the Anthropic key is handled (Secrets Manager — already wired)

You supply the key **once**, at deploy time, via the `AnthropicApiKey`
parameter. The template does **not** put it in the Lambda environment as
plaintext. Instead it:

1. Stores the value in an `AWS::SecretsManager::Secret`
   (`bizbrief/anthropic-api-key-<stage>`).
2. Exposes only the secret's ARN to the functions (`ANTHROPIC_SECRET_ARN`).
3. Grants the analyze + brief functions a scoped `secretsmanager:GetSecretValue`.

At cold start, `infra/lambdas/secrets_provider.py` fetches the key and places it
in the environment so the shared `reliability.call_model` works unchanged. The
key is never a readable plaintext env var.

**To rotate the key later** (no redeploy needed):
```bash
aws secretsmanager put-secret-value \
  --secret-id bizbrief/anthropic-api-key-prod \
  --secret-string "sk-ant-NEW..."
```
New Lambda cold starts pick it up automatically.

---

## 4. Build

`sam build` packages each Lambda. First, the pipeline code is vendored next to
the handlers (Lambda has no editable install of the repo), then deps from
`requirements.txt` are compiled in a Lambda-like container.

```bash
cd infra
make build        # runs: make lambda-deps (copies pipeline/ + reliability/) && sam build
```

If `sam build` complains about Docker, make sure Docker Desktop is running.

---

## 5. Deploy

```bash
cd infra
make deploy       # runs: sam deploy --guided
```

The guided prompts (first deploy only — answers are saved to `samconfig.toml`):

| Prompt | Answer |
|---|---|
| Stack Name | `bizbrief` |
| AWS Region | `us-east-1` (or yours) |
| Parameter Stage | `prod` (or `dev`) |
| Parameter AnthropicApiKey | `sk-ant-...` (hidden; stored in Secrets Manager, not a plaintext env var) |
| Confirm changes before deploy | `Y` |
| Allow SAM to create IAM roles | `Y` ← required (per-function execution roles) |
| Disable rollback | `N` |
| Save arguments to samconfig.toml | `Y` |

When it finishes, SAM prints the stack **Outputs**. Capture them:

```bash
aws cloudformation describe-stacks --stack-name bizbrief \
  --query "Stacks[0].Outputs" --output table
```

You'll get:
- **RawBucketName** — where you upload review files
- **BriefsBucketName** — where rendered briefs land
- **DashboardURL** — the live CloudWatch dashboard

---

## 6. Trigger the pipeline

Upload a review file to the raw bucket. The key path **must** be
`uploads/<business_id>/<week>.jsonl` — that's what the S3 event filter and the
ingest handler's key parser expect.

```bash
cd /Users/zackkaplan/Developer/BIZBRIEF

# Get the raw bucket name from the stack outputs
RAW=$(aws cloudformation describe-stacks --stack-name bizbrief \
  --query "Stacks[0].Outputs[?OutputKey=='RawBucketName'].OutputValue" --output text)

# Build a review file for one business+week from the processed dataset
#  (any business_id + week present in data/processed/reviews.jsonl works;
#   B007IAE5WY / 2017-W38 has 17 reviews)
uv run python - <<'PY'
import json
biz, week = "B007IAE5WY", "2017-W38"
rows = [json.loads(l) for l in open("data/processed/reviews.jsonl")]
sel = [r for r in rows if r["business_id"] == biz and r["week"] == week]
with open(f"/tmp/{biz}_{week}.jsonl", "w") as f:
    for r in sel:
        f.write(json.dumps(r) + "\n")
print(f"wrote {len(sel)} reviews")
PY

# Upload → fires IngestLambda → AnalyzeLambda → BriefLambda automatically
aws s3 cp /tmp/B007IAE5WY_2017-W38.jsonl \
  "s3://$RAW/uploads/B007IAE5WY/2017-W38.jsonl"
```

The chain runs asynchronously. Within ~30–60s (analyze calls Claude), the brief
is written.

---

## 7. Verify it ran

**Tail the logs** (watch the chain fire stage by stage):

```bash
sam logs --stack-name bizbrief --name AnalyzeFunction --tail
# (Ctrl-C to stop; repeat with IngestFunction / BriefFunction)
```

**Check DynamoDB** for the written records (table is `bizbrief-<stage>` — use
the stage you deployed with):

```bash
STAGE=prod   # or dev, whatever you chose at deploy
aws dynamodb query \
  --table-name "bizbrief-$STAGE" \
  --key-condition-expression "PK = :pk" \
  --expression-attribute-values '{":pk":{"S":"BIZ#B007IAE5WY"}}' \
  --query "Items[].SK.S"
# Expect REVIEW#2017-W38#... entries, THEMES#2017-W38, BRIEF#2017-W38
```

**Fetch the rendered brief** from S3:

```bash
BRIEFS=$(aws cloudformation describe-stacks --stack-name bizbrief \
  --query "Stacks[0].Outputs[?OutputKey=='BriefsBucketName'].OutputValue" --output text)
aws s3 cp "s3://$BRIEFS/B007IAE5WY/2017-W38.brief.json" - | python3 -m json.tool
```

**Open the live dashboard** (cost / spend-by-model / latency / throughput):

```bash
aws cloudformation describe-stacks --stack-name bizbrief \
  --query "Stacks[0].Outputs[?OutputKey=='DashboardURL'].OutputValue" --output text
# open that URL in the console
```

> Metrics appear after the first invocation publishes them. CloudWatch custom
> metrics can take 1–2 minutes to surface on the dashboard.

> **Known limitation:** the dashboard's cost widget reflects the **analyze**
> stage (the dominant model cost — router + caching live here). The **brief**
> stage currently publishes `cost_usd=0` to CloudWatch because `pipeline.brief.run`
> doesn't surface its per-run cost to the handler. Brief-stage spend is small
> relative to analyze, but if you want it on the dashboard, have `brief.run`
> return its `run_cost` total and pass it into `metrics.emit(...)` in
> `handler_brief.py` (it already reads `brief.get("_cost_usd")`).

---

## 8. Cost expectations

Everything here scales to zero — an idle stack costs ~nothing.

| Service | Model | Idle cost |
|---|---|---|
| Lambda | per-request + GB-second | $0 idle |
| DynamoDB | on-demand (PAY_PER_REQUEST) | $0 idle |
| S3 | per-GB stored + requests | cents |
| CloudWatch | dashboard + custom metrics | a few cents/month |
| SQS (DLQ) | per-request | $0 idle |

**The real variable cost is Anthropic inference** — governed by the same model
router + prompt caching + per-run cost ceiling as the local build. A single
17-review week costs roughly the eval numbers: ~$0.005 on Haiku, up to ~$0.09 on
Opus. The router keeps most batches on Haiku.

---

## 9. Teardown

```bash
cd infra
make delete       # sam delete — removes the whole stack
```

> S3 buckets must be empty to delete. If `sam delete` stalls on a non-empty
> bucket, empty it first:
> `aws s3 rm s3://<bucket> --recursive` for both the raw and briefs buckets.

---

## 10. Production hardening checklist

The deploy above is functional and demo-ready. To make it genuinely
production-grade, address these (in priority order):

- [x] **Secrets Manager for the API key** — DONE ([§3](#3-how-the-anthropic-key-is-handled-secrets-manager--already-wired)). Key lives in Secrets Manager, fetched at cold start, never a plaintext env var.
- [ ] **Per-function log retention** — set a `LogGroup` retention (e.g. 30 days) so CloudWatch Logs don't accumulate cost indefinitely.
- [ ] **Alarms on the DLQ** — a CloudWatch alarm on `DeadLetterQueue` depth (>0) so failed runs page you instead of sitting silently.
- [ ] **Reserved/provisioned concurrency** (optional) — if cold-start latency matters; otherwise on-demand is cheaper.
- [ ] **S3 upload validation** — restrict who can write to the raw bucket (the trigger fires on any `uploads/*.jsonl`); add a bucket policy or upload via a signed/authenticated path.
- [ ] **Stage separation** — deploy `dev` and `prod` stacks separately (the `Stage` parameter already namespaces every resource).
- [ ] **CI/CD** — wire `sam build && sam deploy` into a GitHub Action on merge to `main`.

---

## Quick reference

```bash
# prereqs: aws configure done, Docker running
cd infra
make build
make deploy        # guided; supply stack name, region, stage, Anthropic key

# trigger
RAW=$(aws cloudformation describe-stacks --stack-name bizbrief \
  --query "Stacks[0].Outputs[?OutputKey=='RawBucketName'].OutputValue" --output text)
aws s3 cp <file>.jsonl "s3://$RAW/uploads/<business>/<week>.jsonl"

# watch
sam logs --stack-name bizbrief --name AnalyzeFunction --tail

# teardown
make delete
```
