# Contributing

Thanks for looking at FinanceOps Agent.

## Principles

1. **Deterministic tools own financial truth** — do not move reconciliation math into prompts.
2. **Mutations require human approval** — never auto-post journals in demos or defaults.
3. **Every investigation must be auditable** — plan, tools, evidence, verification, decision.
4. **Eval before flourish** — if you change matching/anomaly logic, update tests + `eval.run_eval`.

## Local loop

```bash
cd backend && uv sync && uv run pytest -q && uv run python -m eval.run_eval
cd ../frontend && npm run lint
```

## Design

Read [docs/DESIGN.md](docs/DESIGN.md) before large architectural changes.
