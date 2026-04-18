# Contributing

Guidelines for developing on the Calendar Planning Agent project.

---

## Branching Strategy

We use a **trunk-based** workflow with `main` as the single long-lived branch.

### Branch naming

```
<type>/<short-description>
```

| Type | Use for |
|---|---|
| `feat/` | New functionality (e.g. `feat/free-slot-computation`) |
| `fix/` | Bug fixes (e.g. `fix/overlap-detection-off-by-one`) |
| `refactor/` | Code restructuring with no behavior change |
| `test/` | Adding or updating tests only |
| `docs/` | Documentation changes only |
| `infra/` | CI, Docker, CloudFormation, deploy scripts |

Rules:
- Always branch off `main`.
- Keep branches short-lived — merge within a few days.
- Delete the branch after merging.

---

## Commits

### Commit message format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `infra`

**Scopes** (match project modules):
- `validator` — `src/validator/`
- `calendar-api` — `src/calendar_api/`
- `orchestration` — `src/orchestration/`
- `heuristics` — `src/orchestration/heuristics/`
- `llm-client` — `src/llm_client/`
- `frontend` — `src/frontend/`
- `config` — `config/`
- `ci` — `.github/workflows/`
- `infra` — `infrastructure/`

### Examples

```
feat(validator): implement 4 hard-constraint checks

Add overlap, self-overlap, working-hours, and deadline validation
to validate_schedule(). Includes intervals_overlap() helper.
```

```
fix(heuristics): handle subtask longer than any free slot
```

```
test(calendar-api): add free-slot computation edge case tests
```

### Commit rules

- One logical change per commit. Don't mix unrelated changes.
- Write the subject line in imperative mood ("add", "fix", "remove" — not "added", "fixes").
- Keep the subject under 72 characters.
- Use the body to explain **why**, not what (the diff shows the what).
- Never commit secrets, tokens, or credentials (`.env`, `token.json`, `credentials.json`).
- Run `pytest` before committing. Don't push commits that break existing tests.

---

## Pull Requests

### Opening a PR

1. Push your branch and open a PR against `main`.
2. PR title should follow the same conventional commit format: `feat(scope): description`.
3. Fill in the PR template:
   - **Summary** — 1-3 bullet points describing the change.
   - **Test plan** — how to verify the change works.
4. Keep PRs focused. One feature, one fix, or one refactor per PR.
   - If a PR grows beyond ~400 lines of diff, consider splitting it.

### Review process

- All PRs require at least one review before merging.
- Reviewers should check:
  - Tests pass and cover the new/changed behavior.
  - No secrets or credentials in the diff.
  - Calendar API code is add-only (no update/delete calls).
  - Heuristics and validator remain pure functions (no LLM or API calls).
  - State types in `state.py` are updated if the change adds new fields.

### Merging

- Use **squash merge** into `main` to keep history clean.
- Ensure CI is green before merging.
- Delete the source branch after merge.
- Never force-push to `main`.

---

## Development Workflow

### Setting up

```bash
git clone <repo-url> && cd calendar_planning_agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY at minimum
```

### Day-to-day

```bash
# 1. Start from an up-to-date main
git checkout main && git pull

# 2. Create a feature branch
git checkout -b feat/my-feature

# 3. Develop — run the app in mock mode
CALENDAR_MODE=mock streamlit run src/app.py

# 4. Run tests before committing
pytest -v

# 5. Commit and push
git add <files>
git commit -m "feat(scope): description"
git push -u origin feat/my-feature

# 6. Open a PR against main
```

### Implementation order

Follow the phased approach from `PROGRAMMER_MANUAL.md`:

1. **Phase 1** — Pure-logic modules first: `validator/constraints.py`, `free_slots.py`, `mock_calendar.py`, heuristics.
2. **Phase 2** — LLM integration: `llm_client/client.py`, orchestration nodes that call the LLM.
3. **Phase 3** — Graph wiring and frontend: `graph.py`, `app.py`, frontend components.

This order matters — later modules depend on earlier ones. Don't skip ahead.

---

## Code Standards

### Style

- Follow PEP 8.
- Use type hints on all function signatures.
- Use `from __future__ import annotations` at the top of every module (already present in all files).
- Prefer explicit imports over star imports.

### Architecture rules

- **Validator and heuristics are pure functions.** No LLM calls, no API calls, no side effects. This keeps them fast and fully unit-testable.
- **Calendar API is add-only.** Never call `events().update()` or `events().delete()`. This is a safety invariant.
- **All LLM calls go through `src/llm_client/client.py`.** Don't instantiate the Anthropic client elsewhere.
- **State flows through `AgentState`.** If a node needs new data, add a field to `AgentState` in `state.py` first.
- **Mock mode must always work.** Every code path that touches Google Calendar must have a `CALENDAR_MODE=mock` branch.

### Testing

- Every implemented function needs corresponding tests.
- Tests must not make real API calls (LLM or Google). Mock external dependencies.
- Use fixtures from `tests/conftest.py` for shared test data.
- Run the full suite with `pytest -v` before pushing.

---

## Security

- Never commit `.env`, `token.json`, or `credentials.json`. They are in `.gitignore`.
- Never log or print API keys, OAuth tokens, or refresh tokens.
- If you add a new secret or credential, add it to `.env.example` with a placeholder value and to `.gitignore`.
- Review diffs for accidental secret exposure before pushing.
