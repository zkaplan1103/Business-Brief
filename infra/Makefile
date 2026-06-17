# BizBrief serverless — build / local-invoke / deploy helpers.
# Run from the infra/ directory. Requires the AWS SAM CLI for build/deploy.
.PHONY: lambda-deps build local-ingest local-analyze local-e2e validate deploy delete clean

# Vendor the shared pipeline code next to the handlers so Lambda's import paths
# resolve (Lambda has no editable install of the repo). Copies are git-ignored.
lambda-deps:
	rm -rf lambdas/pipeline lambdas/reliability
	cp -r ../pipeline lambdas/pipeline
	cp -r ../reliability lambdas/reliability
	find lambdas/pipeline lambdas/reliability -name '__pycache__' -type d -exec rm -rf {} +

build: lambda-deps
	sam build

validate:
	sam validate --lint

# Local invoke — no AWS account needed beyond Docker. Metrics emission is a
# no-op locally (BIZBRIEF_METRICS_DISABLED=1) so it runs without CloudWatch.
local-ingest: build
	BIZBRIEF_METRICS_DISABLED=1 sam local invoke IngestFunction \
		--event events/s3_upload.json

local-analyze: build
	BIZBRIEF_METRICS_DISABLED=1 sam local invoke AnalyzeFunction \
		--event events/analyze.json

# Full ingest -> analyze -> brief end-to-end against in-process mock S3 +
# DynamoDB (moto). No AWS account, no Docker, no SAM. Needs ANTHROPIC_API_KEY
# (the analyze stage calls Claude; reruns hit the idempotency cache and are free).
#   make local-e2e                         # default business/week
#   make local-e2e ARGS="--business B007IAE5WY --week 2017-W38"
local-e2e:
	cd .. && uv run --group local-aws python infra/local_run.py $(ARGS)

deploy: build
	sam deploy --guided

delete:
	sam delete

clean:
	rm -rf .aws-sam lambdas/pipeline lambdas/reliability
