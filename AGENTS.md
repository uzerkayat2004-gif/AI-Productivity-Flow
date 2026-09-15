# Voice Flow Agent Workflow

These instructions apply to the entire Voice Flow repository.

## Model roles

- The primary agent owns task understanding, planning, architecture decisions, risk assessment, and final review.
- Use the primary frontier model for planning and review only. Do not use it for routine implementation when delegation is available.
- Delegate implementation to a GPT-5.6 Terra sub-agent.
- If a smaller approved implementation model such as Luna becomes available, it may be used for small, well-scoped mechanical tasks. Until then, use Terra.

## Required workflow for build and change requests

1. The primary agent inspects the relevant code and produces a concise implementation plan.
2. The primary agent delegates the bounded implementation task to a Terra sub-agent, with acceptance criteria, relevant file paths, constraints, and required tests.
3. The Terra agent implements the change and runs focused verification.
4. The primary agent reviews the diff, checks architectural fit, and runs or requests any additional verification needed.
5. If the review finds issues, send targeted corrections back to Terra when practical. The primary agent should directly edit only when delegation is unavailable, the fix is extremely small, or immediate intervention is needed to prevent damage.
6. The primary agent gives the user the final outcome, verification results, and any remaining risks.

## Delegation boundaries

- Keep planning and final approval with the primary agent.
- Give each implementation agent a concrete, bounded task; do not delegate vague product decisions.
- Avoid having multiple agents edit the same files concurrently.
- Preserve user changes and inspect the working tree before editing.
- Do not commit, push, publish, deploy, send messages, or perform destructive actions unless the user explicitly requests it.
- For tiny read-only questions, reviews, or one-line non-code changes, delegation is optional when it would add more overhead than it saves.

## Verification expectations

- The implementation agent runs the narrowest relevant tests, lint checks, or manual validation.
- The primary agent independently reviews all changed files before accepting the work.
- Treat the live codebase as the source of truth; handoff documents and line-number references may be stale.
