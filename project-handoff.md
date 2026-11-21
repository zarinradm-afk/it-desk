

## 2026-11-21 validation update
- Added ticket title validation: trim, require non-empty, max 200 characters.
- Added regression coverage in tests/test_login_flow.py.
- Verification: pytest => 13 passed, 1 warning; compileall passed.



## 2026-11-21 ticket filters and deadlines
- Added stored ticket due dates with priority SLA: urgent 4h, high 24h, normal 48h, low 72h.
- Added search by title and filters for status, priority, and overdue tickets.
- Added additive SQLite migration for tickets.due_at.
- Verification: pytest => 14 passed, 1 warning; compileall passed; Docker /health => 200.

