## Hexmaster code review plan

Review the Hexmaster repo with a focus on security and production reliability, then produce a prioritized set of findings and concrete remediation steps (with optional patches).

### Scope and focus

- Review all Python code under `src/hexmaster/` (bot, services, DB layer, utilities) with emphasis on **security** (secrets exposure, permission boundaries, data leakage) and **reliability** (startup/shutdown, error handling, rate limits, external dependencies, DB schema management).

### What to inspect (starting points)

- Bot entrypoint and wiring: `src/hexmaster/bot/main.py`
- Configuration + logging: `src/hexmaster/config.py`, `src/hexmaster/logging.py`
- Cogs:
  - `src/hexmaster/bot/cogs/stockpile_cog.py`
  - `src/hexmaster/bot/cogs/setup_cog.py`
  - `src/hexmaster/bot/cogs/priority_cog.py`
  - `src/hexmaster/bot/cogs/health.py`
- Services:
  - `src/hexmaster/services/ocr_service.py`
  - `src/hexmaster/services/war_service.py`
  - `src/hexmaster/services/stockpile_service.py`
- DB bootstrap and schema sync: `src/hexmaster/db/init.py`, `src/hexmaster/db/schema_sync.py`
- Repositories/utilities:
  - `src/hexmaster/db/repositories/stockpile_repository.py`
  - `src/hexmaster/db/repositories/settings_repository.py`
  - `src/hexmaster/utils/discord_utils.py`

### Review output to produce

- A written review organized by severity:
  - **P0 (must fix before production)**
  - **P1 (should fix soon)**
  - **P2 (nice to have)**
- For each finding, include:
  - impact (security/reliability)
  - where it occurs (file/function)
  - recommended change(s)
  - trade-offs / rollout notes

### Key areas to evaluate next (to complete repo-wide coverage)

- DB models + constraints and any raw SQL usage: `src/hexmaster/db/models.py`
- Seeding and data ingestion scripts / seed behavior: `src/hexmaster/db/seed_reference.py`
- Remaining utilities (geo/datetime) to ensure no unsafe assumptions:
  - `src/hexmaster/utils/geo_utils.py`
  - `src/hexmaster/utils/datetime_utils.py`
- Tests that reveal intended behavior and safety expectations: `tests/system/test_bot_cogs.py`

### Optional remediation plan (if you want code changes after the review)

- Replace `print()` with structured logging and ensure exceptions are logged server-side while users receive sanitized messages.
- Gate global command sync (`tree.sync`) behind a config flag to avoid startup rate-limit risk.
- Rework schema management:
  - remove destructive/opaque startup migrations from `schema_sync.py` (notably `UPDATE priority SET guild_id = 0 ...` and primary-key rewrites at runtime)
  - move to explicit migrations or, at minimum, make startup schema sync strictly additive and safe.
- Harden external HTTP usage (OCR/WarAPI): timeouts, retries/backoff, shared `aiohttp.ClientSession` lifecycle, and clear error taxonomy.
- Add a clear permission model for commands (especially anything that exposes DB/system info), and avoid surfacing raw exception text to Discord users.
