# BizBrief — Deploy Runbook (staged, with human breakpoints)

This is the working checklist for getting BizBrief live on AWS. It splits the
deploy into stages tagged either:

- **`[CODE — Claude]`** — I do this in the repo. No action from you.
- **`[BREAKPOINT — you]`** — requires a human with AWS console / billing / a
  real key. I stop, explain exactly what to do and why, and wait.

We walk it top to bottom. After each breakpoint you tell me to continue.

**Legend:** ☐ not started · ⏳ in progress · ✅ done

---

## Stage 0 — Code hardening & validation  `[CODE — Claude]`  ✅

Done before you touch anything:

- ✅ Secrets Manager hardening: API key no longer a plaintext Lambda env var.
  Handlers fetch it at cold start via `secrets_provider.ensure_anthropic_key()`;
  template stores it in `AWS::SecretsManager::Secret` and grants the analyze +
  brief functions `secretsmanager:GetSecretValue`.
- ✅ Circular-dependency fix (explicit S3 notification + Lambda permission).
- ✅ DynamoDB `Decimal` normalization fix.
- ✅ `sam validate --lint` passes; handlers import with vendored code; 215 tests
  + moto e2e green.

Nothing for you here. This is the state of `main` right now.

---

## Stage 1 — AWS account & credentials  `[BREAKPOINT — you]`  ☐

**What to do:**

1. If you don't have an AWS account: create one at https://aws.amazon.com
   (needs a credit card; this deploy costs cents — see Stage 7).
2. Create an IAM identity for deploying. Easiest secure path:
   - AWS Console → **IAM** → **Users** → Create user (e.g. `bizbrief-deployer`).
   - Attach policy **`AdministratorAccess`** for a personal project (simplest),
     or a scoped policy if this is a shared account (see "why" below).
   - Create an **access key** for that user (Security credentials → Create
     access key → "Command Line Interface").
3. Configure the CLI locally:
   ```bash
   aws configure
   # AWS Access Key ID:     <paste>
   # AWS Secret Access Key: <paste>
   # Default region name:   us-east-1     # pick your region
   # Default output format: json
   ```
4. Verify:
   ```bash
   aws sts get-caller-identity
   ```

**Why this is yours, not mine:** I can't create cloud accounts or hold cloud
credentials — that's a hard line. The access key is a long-lived secret tied to
your billing; it must live only on your machine in `~/.aws/credentials`.

**Why AdministratorAccess (or why not):** the deploy creates Lambda, S3,
DynamoDB, SQS, CloudWatch, Secrets Manager, IAM roles, and a CloudFormation
stack. On a personal account, admin is the no-friction choice. On a shared/work
account, scope it to those services + `cloudformation:*` instead — tell me and
I'll write the exact least-privilege policy JSON.

**When done:** paste me the output of `aws sts get-caller-identity` (it's safe —
it shows your account ID and user ARN, no secrets) and say "continue." I'll
re-run my pre-flight checks and move to Stage 2.

---

## Stage 2 — Pre-flight verification  `[CODE — Claude]`  ☐

Once your creds are set, I will (no action from you):

- Confirm `aws sts get-caller-identity` succeeds and note the account ID/region.
- Confirm your `ANTHROPIC_API_KEY` is real in `.env` (the secret seed value).
- Re-run `sam validate --lint`.
- Sanity-check the chosen region supports everything (it all does in standard
  regions; I'll flag if you picked an exotic one).

If anything's off, I fix or tell you. Otherwise → Stage 3.

---

## Stage 3 — Start Docker  `[BREAKPOINT — you]`  ☐

**What to do:** launch Docker Desktop and wait for it to be ready:
```bash
open -a Docker          # then wait ~30s
docker info >/dev/null 2>&1 && echo "Docker ready"
```

**Why this is yours:** `sam build` compiles the Lambda dependencies
(`anthropic` + its transitive deps) inside a Lambda-like Linux container so the
binaries match the runtime. That needs the Docker daemon, which is a desktop app
on your machine — I can't reliably launch or keep it running.

**When done:** say "continue."

---

## Stage 4 — Build  `[CODE — Claude]`  ☐

I run (no action from you):
```bash
cd infra
make build        # vendors pipeline/ + reliability/, then sam build
```
I'll report success or fix any packaging error. → Stage 5.

---

## Stage 5 — Deploy  `[BREAKPOINT — you]`  ☐

This is the step that creates billable infrastructure, so you drive it.

**What to do:**
```bash
cd infra
make deploy       # sam deploy --guided
```
Answer the prompts (first time only — saved to `samconfig.toml` after):

| Prompt | Answer |
|---|---|
| Stack Name | `bizbrief` |
| AWS Region | (your region) |
| Parameter Stage | `prod` (or `dev`) |
| Parameter AnthropicApiKey | paste your real `sk-ant-...` key |
| Confirm changes before deploy | `Y` |
| Allow SAM CLI IAM role creation | **`Y`** (required) |
| Disable rollback | `N` |
| Save arguments to samconfig.toml | `Y` |

**Why this is yours:** (1) it spends real money and provisions real resources —
that's an explicit human authorization, not something I should trigger; (2) you
type your real API key into the prompt, which then lands in Secrets Manager. I
never see or hold that key.

**Why the key prompt is still safe now:** unlike before, the key goes into
Secrets Manager (via the `AnthropicSecret` resource), not a plaintext Lambda env
var. The functions read it at runtime with a scoped `GetSecretValue` permission.

**When done:** paste me the **Outputs** table SAM prints (or run
`aws cloudformation describe-stacks --stack-name bizbrief --query "Stacks[0].Outputs" --output table`)
and say "continue."

---

## Stage 6 — Trigger & verify  `[CODE — Claude]`  ☐

With creds + a deployed stack, I can run this end-to-end myself:

- Build the review upload file from `data/processed/reviews.jsonl`.
- `aws s3 cp` it to `uploads/<business>/<week>.jsonl` → fires the Lambda chain.
- Tail the logs, query DynamoDB for the written records, fetch the rendered
  brief from S3, and confirm the CloudWatch dashboard has metrics.

I report what landed. You only step in if AWS rejects something
permission-related (then it's a Stage-1 IAM tweak).

> If you'd rather run the trigger yourself, the commands are in
> [DEPLOY.md §6–§7](DEPLOY.md). Either works.

---

## Stage 7 — Confirm the dashboard & costs  `[BREAKPOINT — you]`  ☐

**What to do:** open the `DashboardURL` from the stack outputs in your browser
and confirm you see cost / spend-by-model / latency / throughput widgets
populating. Glance at AWS Billing to confirm spend is in the expected range
(cents).

**Why this is yours:** it's your console session and your billing view — I can't
see either. This is the "it's real and I can point to it" moment for the résumé
bullet.

**When done:** you're live. Optionally → Stage 8.

---

## Stage 8 — Production hardening follow-ups  `[mixed]`  ☐

Already done: ✅ Secrets Manager. Remaining (from DEPLOY.md §10), I can code,
you deploy:

- ☐ CloudWatch Logs retention on each function (cost control) — `[CODE]`
- ☐ Alarm on DLQ depth > 0 (failed-run paging) — `[CODE]`
- ☐ Restrict who can write to the raw bucket — `[CODE]`
- ☐ GitHub Action for `sam build && sam deploy` on merge — `[CODE]` + you add
  AWS creds as repo secrets `[BREAKPOINT]`

Tell me which you want and I'll add them.

---

## Where we are right now

**Stage 0 ✅ complete. Next action: yours — Stage 1 (AWS account & credentials).**

Do Stage 1, paste me `aws sts get-caller-identity`, and say "continue."
```
