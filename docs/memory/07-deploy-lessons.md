---
tags: [deploy, aws, serverless, lessons]
---
# Deploy lessons — what broke on the real AWS deploy (and how to avoid it next time)

BizBrief was deployed to real AWS (SAM stack `bizbrief`, us-east-1) on 2026-06-17.
The deploy hit several blockers that the local/mock work could not surface. This
file is the checklist to read BEFORE the next `sam deploy` (or before deploying a
similar serverless stack) so we don't rediscover them one error at a time.

The detailed dated entries are in `00-decisions.md`; this is the fast reference.

## Pre-deploy checklist (do these first, in order)

1. **`sam validate --lint`** — catches CloudFormation structural errors (e.g. the
   circular-dependency bug below) before any AWS call. Always run it after
   editing `template.yaml`.
2. **Vendor + import-check** — `make lambda-deps` then import every handler with
   the vendored tree on `sys.path`, AND with optional deps hidden, to catch
   missing-package import crashes (the dotenv bug below).
3. **Docker running** — `sam build` compiles deps in a container; it fails fast
   without Docker.
4. **Probe IAM** — confirm the deployer can actually create the resource types
   (see IAM section). Cheaper than a mid-deploy rollback.

## Bugs that bit us (each would fail a deploy)

### 1. SAM S3-trigger circular dependency  → caught by `sam validate --lint`
Using SAM's `Events: S3` sugar on a function whose bucket is defined in the same
template creates a cycle: Bucket → Function → auto-generated Lambda::Permission →
Bucket. **Fix:** wire the trigger explicitly — `RawBucket.NotificationConfiguration`
+ a standalone `AWS::Lambda::Permission` using a *static* `!Sub` bucket ARN as
`SourceArn` (NOT `!Ref`). Also: in `Globals`, set bucket env vars to static
`!Sub` names, not `!Ref` — a `!Ref` to the bucket drags every function into the
cycle. **Lesson:** never `!Ref` an S3-event bucket from the function that it triggers.

### 2. DynamoDB Decimal → `TypeError: Decimal not JSON serializable`
boto3's DynamoDB resource returns ALL numbers as `decimal.Decimal`. `json.dumps`
on query results crashes; arithmetic on them misbehaves. **Fix:** normalize at the
read boundary — `storage._undecimalize()` recurses and converts Decimal→int/float,
applied in `get_reviews()`. **Lesson:** anything read from DynamoDB must be
un-decimalized before json/serialization/math. (Caught by the moto e2e run, not
unit tests.)

### 3. `Runtime.ImportModuleError: No module named 'dotenv'`
`pipeline/analyze.py` and `brief.py` imported `python-dotenv` at module top. It's
installed locally but NOT packaged in Lambda (no `.env` there — the key comes from
Secrets Manager). The handler crashed on cold-start import before any logic ran.
**Fix:** make the import optional — `try: from dotenv import load_dotenv / except
ModuleNotFoundError:` with a no-op fallback. **Lesson:** any top-level third-party
import in vendored code must either be in `infra/lambdas/requirements.txt` or be
optional. Before deploy, scan vendored modules for non-stdlib/non-anthropic
imports. (`httpx` is fine — it ships transitively with `anthropic`.)

### 4. Pre-existing log groups collide with template-managed ones
On the FIRST deploy, Lambda auto-creates `/aws/lambda/<fn>` log groups with
infinite retention. When you later add explicit `AWS::Logs::LogGroup` resources
(for retention), CloudFormation fails because the group already exists. **Fix:**
delete the auto-created groups (`aws logs delete-log-group ...`) before the
redeploy. **Lesson:** define log groups in the template from day one (with
`DependsOn` from each function) so Lambda never auto-creates them.

## IAM: least-privilege deploy is whack-a-mole — plan for it

We scoped the deployer down from AdministratorAccess to least-privilege, then hit
missing permissions ONE AT A TIME across multiple deploys:
`s3:TagResource` → `s3:DeleteBucket` → `s3:PutLifecycleConfiguration` →
(later, for hardening) `logs:*`, `sns:*`, `cloudwatch:PutMetricAlarm`.

**Lessons / shortcuts for next time:**
- For the S3 bucket actions specifically, just grant `"s3:*"` SCOPED to the
  resource ARNs (`aws-sam-cli-managed-default*`, `bizbrief-*`). This ends the
  S3 whack-a-mole without any account-wide reach. Granular per-action S3 lists
  are not worth the iteration cost.
- The deployer also needs a read-only `VerifyAndInspect` block (dynamodb
  Query/Get/Scan, logs read, cloudwatch metrics read, sqs ReceiveMessage) so it
  can VERIFY runs after deploy — the deploy-only perms don't include reads.
- The managed bootstrap stack (`aws-sam-cli-managed-default`) needs S3 create +
  **tag + delete** on its bucket; if it fails it can get stuck in
  `ROLLBACK_FAILED` — empty the bucket then `delete-stack` to clear it.
- A `ROLLBACK_COMPLETE` stack CANNOT be updated; it must be deleted before retry.

## Deploy prompt gotcha
`sam deploy --guided` mixes yes/no, text, and path prompts. Bracketed `[default]`
prompts (Stack Name, SAM configuration file `[samconfig.toml]`, configuration
environment `[default]`) want **Enter**, NOT `Y`. Typing `Y` at the config-file
prompt makes SAM treat `Y` as a filename and error. After the first guided deploy,
`samconfig.toml` is saved and subsequent deploys run non-interactively.

## Secrets / public-repo hygiene (this repo is PUBLIC: zkaplan1103/Business-Brief)
- The AWS account ID is sensitive metadata — keep it OUT of tracked files; use
  `<ACCOUNT_ID>` placeholders. See [[no-commit-secrets-and-account-config]].
- IAM policies live in the AWS console only, never committed.
- Sweep every staged diff for `sk-ant-`, `AKIA`, the account ID, and real
  `BIZBRIEF_API_KEY` values before any push.

## What worked well (keep doing)
- Secrets Manager from the start (key fetched at cold start via
  `secrets_provider.ensure_anthropic_key()`; no plaintext env var).
- The moto local-e2e run (`make local-e2e`) caught the Decimal bug pre-deploy.
- Staged deploy with explicit human breakpoints (account/creds, Docker, the
  deploy itself, billing) — the human only acted where genuinely required.
- `sam validate --lint` as a gate caught the circular dependency before spend.
