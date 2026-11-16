## What changed

<!-- One or two sentences. -->

## Checklist

- [ ] `uv run python -m pytest tests/ -q` passes
- [ ] `cd infra && make local-e2e` passes (offline is fine)
- [ ] `cfn-lint infra/template.yaml` is clean, if the template changed
- [ ] `cd web && npm run lint && npm run build` passes, if the UI changed
- [ ] Screenshots attached for UI changes (desktop and 390px wide)
- [ ] No secrets committed (no API keys, `.env`, or account IDs)
