## Hexmaster code review report

### Scope

- Reviewed Python code under `src/hexmaster/` with emphasis on **security** (secrets exposure, permission boundaries, data leakage) and **reliability** (startup/shutdown, error handling, rate limits, external dependencies, DB schema management).

### Files reviewed (high-signal set)

- Bot entrypoint: `src/hexmaster/bot/main.py`
- Config/logging: `src/hexmaster/config.py`, `src/hexmaster/logging.py`
- Cogs: `src/hexmaster/bot/cogs/stockpile_cog.py`, `src/hexmaster/bot/cogs/setup_cog.py`, `src/hexmaster/bot/cogs/priority_cog.py`, `src/hexmaster/bot/cogs/health.py`
- Services: `src/hexmaster/services/ocr_service.py`, `src/hexmaster/services/war_service.py`, `src/hexmaster/services/stockpile_service.py`
- DB bootstrapping/schema management: `src/hexmaster/db/init.py`, `src/hexmaster/db/schema_sync.py`, `src/hexmaster/db/models.py`, `src/hexmaster/db/seed_reference.py`
- Utilities/tests: `src/hexmaster/utils/discord_utils.py`, `src/hexmaster/utils/datetime_utils.py`, `src/hexmaster/utils/geo_utils.py`, `tests/system/test_bot_cogs.py`

---

## P0 (must fix before production)

### 1) Destructive runtime schema “migrations” on every startup

- **Impact**: reliability + data integrity risk. Startup DDL/DML is hard to reason about, can partially apply, and can corrupt data or fail unexpectedly in production.
- **Where**: `src/hexmaster/db/schema_sync.py` (`sync_schema`)
- **Evidence / notes**:
  - Performs DDL changes at runtime (ALTER TABLE / CREATE TABLE).
  - Includes data mutation and PK manipulation inside a `DO $$ ... $$` block (including `UPDATE priority SET guild_id = 0 WHERE guild_id IS NULL`, dropping and re-adding primary keys).
  - Swallows failures with `print(...)` and notices, making failures easy to miss.
- **Recommendation**:
  - Move schema evolution to explicit migrations (Alembic) executed out-of-band.
  - If you must keep a startup check, restrict it to **safe, additive** operations only (no `UPDATE`, no PK drop/re-add, no “repair” logic).
  - Treat any failed schema step as a startup-failing error unless explicitly configured otherwise.
- **Trade-offs**:
  - Alembic adds operational steps (migration run on deploy) but greatly improves safety and reproducibility.

### 2) User-facing error messages include raw exception text

- **Impact**: security (information disclosure) + reliability (no consistent error taxonomy).
- **Where**:
  - `src/hexmaster/bot/cogs/stockpile_cog.py` (multiple `send_error(... f"... {str(e)}")`)
  - `src/hexmaster/bot/cogs/setup_cog.py`, `src/hexmaster/bot/cogs/priority_cog.py`
  - `src/hexmaster/bot/cogs/health.py` (some followup sends with raw error string)
- **Why it matters**:
  - Exceptions can include SQL fragments, database URLs, file paths, upstream HTTP responses, stack traces, etc.
  - Even if responses are often ephemeral/admin-only, leakage still happens (screenshots, copied text, logs).
- **Recommendation**:
  - Return **sanitized** user messages (“Operation failed; try again later”) plus a short error code.
  - Log full exceptions server-side with `logger.exception(...)` including context (guild_id, command name, correlation id).
- **Trade-offs**:
  - Slightly worse UX for debugging via Discord, but much better security and operability.

### 3) `Priority` seeding conflict target likely does not match constraints

- **Impact**: reliability (seed failures or unintended behavior); correctness for multi-guild design.
- **Where**:
  - Model: `src/hexmaster/db/models.py` defines composite PK on `Priority` as `(guild_id, codename)`.
  - Seed: `src/hexmaster/db/seed_reference.py` uses `on_conflict_do_nothing(index_elements=[Priority.codename])`.
- **Why it matters**:
  - `ON CONFLICT (codename)` requires a unique constraint on `codename` alone; with a composite PK it may fail.
  - Seed logic currently doesn’t specify `guild_id` for priority rows, conflicting with the model.
- **Recommendation**:
  - Decide if `priority` is global or per-guild:
    - **Per-guild**: include `guild_id` in seed data and use `ON CONFLICT (guild_id, codename)`.
    - **Global**: remove `guild_id` from the PK and adjust repository/cog logic accordingly.
- **Trade-offs**:
  - Per-guild is more flexible; global is simpler but limits customization.

---

## P1 (should fix soon)

### 4) Global slash-command sync performed on every boot

- **Impact**: reliability (startup latency, rate limit risk).
- **Where**: `src/hexmaster/bot/main.py` (`setup_hook` runs `await self.tree.sync()`)
- **Recommendation**:
  - Gate global sync behind config/env flag (e.g., `SYNC_COMMANDS=true`) and default it off in production.
  - Provide an admin-only command to sync on demand if needed.

### 5) HTTP reliability gaps: no timeouts, no retries/backoff, session per request

- **Impact**: reliability (hangs, resource churn), security (less controlled failure behavior).
- **Where**:
  - `src/hexmaster/services/ocr_service.py` creates a new `aiohttp.ClientSession()` per call; no explicit timeout.
  - `src/hexmaster/services/war_service.py` creates a new `aiohttp.ClientSession()` per call; no explicit timeout.
- **Recommendation**:
  - Reuse a single `aiohttp.ClientSession` per bot lifecycle and set explicit `ClientTimeout`.
  - Add limited retries with exponential backoff for transient failures (timeouts/5xx).
  - Standardize exceptions returned to cogs to avoid leaking raw upstream text.

### 6) Logging is inconsistent (mix of `print` and logging)

- **Impact**: reliability/operability (harder incident response, missing stack traces).
- **Where**: `print` scattered in `bot/main.py`, `db/schema_sync.py`, `services/war_service.py`, `bot/cogs/stockpile_cog.py`.
- **Recommendation**:
  - Use `logging.getLogger(__name__)` everywhere.
  - For caught exceptions: `logger.exception(...)`.
  - Keep user-facing text separate from operational logs.

### 7) Permissions: “default_permissions” is not a full enforcement boundary

- **Impact**: security (misconfiguration edge cases).
- **Where**: `default_permissions=administrator=True` and `@app_commands.default_permissions(administrator=True)` in cogs.
- **Recommendation**:
  - Add explicit runtime permission checks for sensitive commands (and keep ephemeral responses).
  - Consider a “role allowlist” option in `guild_configs` for finer control.

---

## P2 (nice to have)

### 8) Seed/data file paths are inconsistent

- **Impact**: reliability (surprises across envs).
- **Where**:
  - `src/hexmaster/bot/main.py` uses `data/core/...`
  - `src/hexmaster/bot/cogs/setup_cog.py` checks both `data/Priority.csv` and `data/core/Priority.csv`
- **Recommendation**:
  - Centralize a single data-root path (configurable) and standardize file layout.

### 9) Minor: utility fallbacks may hide missing data

- **Impact**: reliability (silent wrong results).
- **Where**:
  - `src/hexmaster/utils/geo_utils.py` returns `0.0` if required keys are missing.
- **Recommendation**:
  - Consider logging or signaling missing coordinate fields (at least in debug logs).

---

## Suggested implementation order (minimal risk)

1) Stop destructive schema changes on startup (`schema_sync.py`), replace with explicit migrations or a separate one-off repair script.
2) Sanitize user-facing errors; log full exception details server-side.
3) Add HTTP timeouts and reuse sessions for OCR/War API clients; add basic retry/backoff.
4) Gate global command sync behind config.
5) Unify logging.
