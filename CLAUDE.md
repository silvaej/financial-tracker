# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commit messages

Brief, imperative, prefixed with a type tag: `(feat) <description>`, `(fix) <description>`, `(chore) <description>`, etc. No `Co-Authored-By` trailer.

## Stack

FastAPI backend rendering server-side HTML via Jinja2, progressively enhanced with HTMX (no client-side JS framework, no JSON API). PostgreSQL via SQLAlchemy 2.0 (typed `Mapped`/`mapped_column` models), Alembic for migrations. Poetry for Python dependency management. Tailwind CSS (standalone CLI, no Node/npm) for styling. Docker Compose for local dev (`db`, `web`, `tailwind` services).

## Commands

Start everything via Docker Compose (installs deps, builds CSS, runs migrations, seeds sample data if the DB is empty, starts the server):

```
docker compose up --build
```

Then, in a second terminal, run Compose's file-sync watcher so edits to `app/`/`alembic/` actually reach the containers and trigger Tailwind's rebuild / uvicorn's `--reload`:

```
docker compose watch
```

Both are needed for local dev on Windows/Mac: `web` and `tailwind` intentionally have **no bind mount** (see below), so without `watch` running, file edits never reach the containers at all. `docker compose watch` also handles rebuilding the image automatically when `pyproject.toml`/`poetry.lock` change.

App is served at http://localhost:8000. Postgres is exposed on localhost:5432 (credentials in `.env` / `.env.example`).

Add/update a Python dependency (regenerates `poetry.lock`, which the Dockerfile installs from — rebuild the image after):

```
poetry add <package>
docker compose up --build
```

Create a migration after changing `app/models.py`:

```
docker compose run --rm web alembic revision --autogenerate -m "describe change"
docker compose run --rm web alembic upgrade head
```

(`alembic upgrade head` also runs automatically on `web` container start.)

Running without Docker (e.g. against local Postgres or SQLite for a quick check): `poetry install`, set `DATABASE_URL`, run `poetry run uvicorn app.main:app --reload`. Swap in a `sqlite:///./dev.db` URL to avoid needing Postgres at all — SQLAlchemy/Alembic don't care which dialect as long as `psycopg2` isn't imported at that path. You'll also need the `tailwindcss` standalone binary on PATH (or run it via `docker compose run --rm tailwind` against the same mounted volume) to regenerate `app/static/css/style.css`.

### Lint, type-check, test

```
poetry run ruff check .            # lint (import order, bugbear, pyupgrade, etc.)
poetry run ruff format .           # format
poetry run mypy app tests          # type-check (strict-ish: disallow_untyped_defs)
poetry run djlint app/templates --profile jinja --reformat   # format Jinja/HTML
poetry run djlint app/templates --profile jinja --check      # check only
poetry run pytest                  # test suite
```

Or via Docker, e.g. `docker compose run --rm web poetry run pytest`.

`tests/conftest.py` overrides the `get_db` FastAPI dependency with an in-memory SQLite session (StaticPool, so all connections in a test share the same DB) — tests never touch Postgres and don't need `psycopg2` importable. `Base.metadata.create_all`/`drop_all` run around every test via an autouse fixture, so each test starts from a clean schema. When adding a route, add a test that posts/gets through the `client` fixture and asserts on the rendered HTML fragment (there's no JSON to assert on — see Architecture below).

mypy is configured with `disallow_untyped_defs`, so every function (including router handlers and pytest fixtures) needs a full signature — annotate `-> HTMLResponse` (or whatever) even though FastAPI doesn't require it at runtime.

## Domain

Modeled after a personal "ledger" budgeting workflow (income arrives on recurring payout dates, gets routed between accounts, and pays bills), not a generic transaction list:

- **Channel** — a bank account, e-wallet, or credit card (`name`, `color`). User-managed (add/rename/recolor/delete), not hardcoded — this is what lets the app work for anyone's actual accounts rather than one specific bank setup.
- **PayoutPeriod** — a recurring pay date (e.g. "15th", "30th") with its own `income_amount` and a `receiving_channel` — the channel that payout's income lands in first.
- **Expense** — a recurring bill: `name`, `amount`, tied to one `PayoutPeriod` and one `Channel` (which channel it's paid from).
- **Transfer** — an explicit, user-entered money move between two channels *for a specific payout period* (`from_channel`, `to_channel`, `amount`). This is how money routes onward from a period's receiving channel to wherever it actually needs to end up (e.g. a savings account, a second wallet used to pay credit cards).
- **`crud.channel_balances(db, payout_period_id)`** (`app/crud.py`) is the core calculation: for a given payout period, each channel's net = its `income_amount` (only if it's that period's `receiving_channel`) + incoming transfers − outgoing transfers − expenses tagged to it. This is the generalized replacement for a fixed cash-flow diagram — since channels/routing are user-defined rather than hardcoded, there's no single fixed diagram shape; instead every payout period gets a computed balance table from whatever transfers/expenses exist. Note this means "remainder" amounts (e.g. "whatever's left after other transfers") are **not** auto-derived — every transfer amount is explicit and user-edited, same as any other field.
- **Goal, CreditLine, Asset** — tables exist (`app/models.py`) for future Goals/Credit/Assets sections, but have no routes, CRUD functions, or templates yet. Don't build UI against them without first adding the corresponding `crud.py` functions and routers, following the pattern below.

## Architecture

- **Request flow**: `GET /` renders the Expenses page (`app/templates/expenses.html`) — the only fully built section so far. `GET /overview`, `/goals`, `/credit`, `/assets` all hit a single catch-all `placeholder` route in `app/main.py` rendering `placeholder.html` ("coming soon") — add a real route+template ahead of the catch-all when building one of those out. There is no JSON API and no client-side state; the DOM is the state, same as before.
- **Fragment contract — whole-page re-render**: unlike a typical HTMX app that swaps small fragments, every mutating route across `app/routers/channels.py`, `payout_periods.py`, `expenses.py`, and `transfers.py` re-renders and returns the *entire* `partials/expenses_page.html` fragment (via a shared `_render_page()` helper in each router) targeting `#expenses-page` with `outerHTML`. This is deliberate: channels and payout periods feed `<select>` dropdowns and computed balances all over the page, so a full-page-content re-render keeps everything consistent without juggling many separate swap targets. The page is small enough that this has no real performance cost. `crud.expenses_page_data(db)` is the single function that assembles all the context (channels, payout periods, expenses, and a `payout_data` list of `{period, transfers, balances}` per period) that both `GET /` and every mutating route render from — keep using it rather than re-deriving context ad hoc in a new route.
- **DB access**: `app/database.py` provides `get_db()` (a FastAPI dependency yielding a `Session`); routers depend on it and delegate all queries to `app/crud.py` — routers should stay thin (parse form input via `app/schemas.py` Pydantic models, call `crud`, render a template).
- **Optional FK form fields**: HTML `<select>` "no selection" options submit as an empty string, not an absent field — `int | None = Form(None)` on a route parameter does NOT accept `""` and will 422. See `payout_periods.py`'s `_parse_channel_id()` helper (`str = Form("")` in the signature, converted to `int | None` manually) for the pattern to copy wherever an optional FK is selectable in a form.
- **Models vs. migrations**: `app/models.py` is the source of truth for schema; `alembic/versions/0001_initial.py` was rewritten (not layered with a new revision) to match, since this project has no deployed data yet — once there's real deployed data, switch to additive migrations instead of editing this one.
- **Styling**: `app/static/css/input.css` defines the ledger palette/fonts via Tailwind v4's `@theme` (e.g. `--color-ink`, `--color-accent`, `--font-serif` for Fraunces, `--font-mono` for IBM Plex Mono) plus a `@layer components` block of reusable classes (`.card`, `.section`, `.pill`, `.led` table, `.field`, `.badge`, etc.) mirroring the original mockup's own hand-written CSS class names — use these existing classes in new templates rather than inlining new utility combinations or `style="..."` attributes (djlint's `H021` rule flags inline styles). `app/static/css/style.css` is the compiled, gitignored output; don't hand-edit it. `app/templates/macros.html` has a `channel_badge(channel, size)` macro (colored initials badge) — import and reuse it (`{% import "macros.html" as macros %}`) anywhere a channel is displayed rather than re-deriving initials.
- **Dependencies**: `pyproject.toml`/`poetry.lock` are the source of truth. The Dockerfile runs `poetry install` with `POETRY_VIRTUALENVS_CREATE=false`, installing straight into the image's system Python rather than a venv inside the container. `requirements.txt` at the repo root exists only for Vercel's Python builder (see CI/Deployment below) — it's generated, not hand-edited: `poetry export -f requirements.txt --output requirements.txt --without-hashes` (needs `poetry-plugin-export`, installed alongside Poetry itself with `pip install poetry poetry-plugin-export` — it's a Poetry CLI plugin, not a project dependency, so it doesn't belong in `pyproject.toml`). Regenerate it any time `poetry.lock` changes; CI fails if it's out of sync.
- **Local dev file sync**: `web`/`tailwind` in `docker-compose.yml` deliberately have no `.:/code` bind mount — on Windows (and often Mac) hosts, in-container watchers (Tailwind's `--watch`, uvicorn's `--reload`) don't reliably see filesystem-event notifications through a bind mount, so edits silently fail to trigger a rebuild/reload even though the file content itself would be up to date. `develop.watch` (`docker compose watch`) works around this by pushing changes into the container through the Docker engine instead, which the in-container watchers *do* see. Keep source changes under the watched paths (`app/`, `alembic/`) — anything outside those needs an image rebuild (`pyproject.toml`/`poetry.lock` already trigger one automatically via a `rebuild` watch action).

## CI / Deployment

- **CI**: `.github/workflows/ci.yml` runs on every push/PR — `ruff check`, `ruff format --check`, `mypy app tests`, `djlint --check`, `pytest`, and a `requirements.txt` drift check (`poetry export` output must match the committed file). `migrate-prod` (pushes to `main`) and `migrate-staging` (pushes to `dev`) each run `alembic upgrade head` against `secrets.PROD_DATABASE_URL` / `secrets.STAGING_DATABASE_URL` respectively.
- **Deploy**: Vercel, connected via its GitHub git integration (set up once in the Vercel dashboard — not something this repo's code controls) — production deploys from `main`, preview deploys per PR/branch. `api/index.py` re-exports `app.main:app` as the ASGI entrypoint Vercel's Python runtime auto-detects. `vercel.json`'s `buildCommand` re-runs the same standalone-`tailwindcss`-binary compile step used in the `Dockerfile`/`docker-compose.yml` (no Node/npm involved), `regions` pins the function to `sin1` (Singapore) to stay co-located with the Neon DB region, and `rewrites` routes every path — including `/static/*` — to that one function, since static files are served by the app's own `StaticFiles` mount rather than Vercel's static hosting.
- **Staging**: `dev` gets its own DB (a Neon branch off the prod database, same schema, isolated data) and its own `DATABASE_URL`, set as a Vercel Preview env var scoped specifically to the `dev` branch (Vercel Hobby plan's way of doing per-branch environments — Pro adds first-class custom environments). Other preview branches (feature branches off `dev`) currently have no `DATABASE_URL` override and inherit whatever the general Preview scope is set to, if anything — deliberately not solved further until it's actually needed. `app/seed.py`'s `seed_if_empty()` populates realistic sample data into staging — run automatically by the `seed-staging` CI job after `migrate-staging`. It's per-table idempotent (checks each model's row count independently before inserting), so it's safe to re-run: already-populated tables are left alone, but a newly added model that's still empty gets seeded on the next run. The same `python -m app.seed` step also runs locally as part of `docker compose up`'s `web` command (after `alembic upgrade head`, before `uvicorn` starts) and in the `Dockerfile`'s `CMD`, so local dev gets the same sample data on a fresh DB for free.
- **Known gap**: SQLAlchemy's pooled `create_engine()` (`app/database.py`) isn't tuned for Vercel's short-lived serverless invocations yet — revisit (e.g. `NullPool`) if connection exhaustion becomes an actual problem; Neon's pooled connection string (used for `DATABASE_URL` everywhere) mitigates this for now. The `migrate-*` CI jobs and Vercel's deploy aren't ordered relative to each other, so a push doesn't guarantee the migration lands before/after the new code goes live.
