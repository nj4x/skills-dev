# Python Standards Reference

Validate Python code against modern idioms (Python 3.10+), pydantic v2, DRY discipline, SQL-injection safety, and the trading-system's established patterns. Use this as the reference for AI-assisted review of `PROJECT_TYPE = Python` projects.

---

## 1. DRY & Reusable Methods

The goal is *the right* abstraction, not zero duplication. A wrong abstraction is more expensive to unwind than the duplication it replaced.

- **Rule of three (Sandi Metz / AHA — "Avoid Hasty Abstractions")**: wait for the **third** occurrence before extracting. Two near-identical blocks may diverge; three reveal the stable shape.
- **Extract once the pattern is stable**: prefer small, single-responsibility helpers over a parameterized mega-function with five flags that each branch internally.
- **When an abstraction is wrong, re-inline then re-extract correctly** — do not bolt another parameter onto a leaky helper.

```python
# DON'T — premature mega-helper with mode flags (the wrong abstraction)
def process(data, *, validate=False, audit=False, notify=False, dry_run=False):
    if validate: ...
    if audit: ...
    if notify: ...        # each caller uses a different subset → flags multiply
    if dry_run: ...

# DO — small single-responsibility helpers, composed by the caller
def validate_order(order: Order) -> None: ...
def audit_order(order: Order, *, status: str) -> None: ...
def notify_operator(order: Order) -> None: ...
```

```python
# DON'T — extract after the SECOND occurrence; the two paths diverge next sprint
# DO — let it duplicate until the third call proves the shape is stable, then extract
```

---

## 2. Boilerplate Reduction

- **`@dataclass(frozen=True, slots=True)`** for plain internal records (no validation, no serialization needs). Reserve pydantic for **trust boundaries** (external input, API payloads, config files).
- **`contextlib.contextmanager`** for setup/teardown pairs instead of repeated try/finally.
- **Decorators** for cross-cutting concerns: audit logging, retry, timeout.

```python
# DO — frozen slotted dataclass for an internal value object
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    as_of: datetime
```

```python
# DO — contextmanager for a setup/teardown pair
from contextlib import contextmanager

@contextmanager
def db_cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
```

```python
# DO — decorator for a cross-cutting concern (retry with backoff)
import functools, time

def retry(times: int = 3, backoff: float = 0.5):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except TransientError:
                    if attempt == times - 1:
                        raise
                    time.sleep(backoff * (2 ** attempt))
        return wrapper
    return deco
```

---

## 3. Pydantic v2 Idioms

- **`Annotated` types for reusable validators** — define the constraint once, reuse it everywhere.
- **`field_validator` / `model_validator` (v2 style)** — never the legacy `@validator` / `@root_validator`.
- **Shared `AppModel` base** with strict config.
- **`EmailStr`** from pydantic for email fields.
- **`extra="forbid"`** on external-input models. Never `extra="ignore"` on a trust-boundary model — it silently hides schema drift.

```python
# DO — reusable Annotated validator
from typing import Annotated
from pydantic import AfterValidator

def _is_ticker(v: str) -> str:
    if not v.isupper() or not (1 <= len(v) <= 5):
        raise ValueError("ticker must be 1-5 uppercase chars")
    return v

Ticker = Annotated[str, AfterValidator(_is_ticker)]
```

```python
# DO — v2 field_validator / model_validator, shared strict base, EmailStr
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, model_validator

class AppModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

class OrderRequest(AppModel):
    symbol: Ticker
    qty: int
    operator_email: EmailStr

    @field_validator("qty")
    @classmethod
    def _positive_qty(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("qty must be positive")
        return v

    @model_validator(mode="after")
    def _check_consistency(self) -> "OrderRequest":
        ...
        return self
```

```python
# DON'T — legacy v1 validators (removed/deprecated in v2)
from pydantic import validator, root_validator

class OrderRequest(BaseModel):
    @validator("qty")          # ❌ legacy — use @field_validator
    def positive(cls, v): ...

    @root_validator            # ❌ legacy — use @model_validator
    def check(cls, values): ...
```

```python
# DON'T — extra="ignore" on a trust-boundary model hides schema drift
class Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")   # ❌ unknown fields swallowed silently
```

---

## 4. SQL / DB Access Patterns

### 4a. Injection Safety (critical)

- **Values: always `%s` parameters** — never f-strings, `%`-formatting, or `+` concatenation for values. String-interpolated values are SQL injection.
- **Identifiers: `psycopg2.sql.Identifier(name)`** for dynamic table/column names. `sql.SQL(...)` is for **literal SQL fragments only**, not for values or untrusted identifiers.
- **Repository pattern**: centralize queries in a module so query strings are defined once, not duplicated per call site.
- **JSONB serialization**: `psycopg2.extras.Json(value)` (or `json.dumps`) for dict/list values — not ad-hoc per-call serialization.

```python
# DO — values parameterized, identifiers via sql.Identifier
from psycopg2 import sql

query = sql.SQL("SELECT * FROM {t} WHERE {c} = %s").format(
    t=sql.Identifier(table),
    c=sql.Identifier(col),
)
cur.execute(query, (value,))
```

```python
# DON'T — f-string / concatenation for values OR identifiers (injection)
cur.execute(f"SELECT * FROM {table} WHERE {col} = '{value}'")   # ❌ CRITICAL
cur.execute("SELECT * FROM orders WHERE id = " + order_id)      # ❌ CRITICAL
```

```python
# DO — JSONB values wrapped once, repository centralizes the query
from psycopg2.extras import Json

class AuditRepository:
    _INSERT = sql.SQL(
        "INSERT INTO audit_events (operation, detail) VALUES (%s, %s)"
    )

    def record(self, cur, operation: str, detail: dict) -> None:
        cur.execute(self._INSERT, (operation, Json(detail)))
```

---

### 4b. Cursor Factory and Row Access

**Choosing a cursor factory** — set once at the connection level, not per-cursor:

| Need | Factory | Row access |
|---|---|---|
| Max speed, positional columns | `cursor()` (default) | `row[0]`, `row[1]` |
| Both `row["col"]` AND `row[0]` | `DictCursor` | both work |
| Direct `json.dumps(row)` without conversion | `RealDictCursor` | `row["col"]` only — `row[0]` raises `KeyError` |
| Dot-access `row.col_name`, immutable, hashable | `NamedTupleCursor` | `row.col`, `row[0]`, `row._asdict()` |
| Millions of rows, low RAM | Named server-side cursor | any of the above |

```python
# DO — set cursor_factory once at connection level
import psycopg2, psycopg2.extras

conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
# all cursors on this connection are now RealDictCursor
```

**Critical: `RealDictCursor` rows do NOT support integer indexing.**

```python
# DON'T — integer indexing on a RealDictCursor row (KeyError, not IndexError)
with get_conn() as conn:          # get_conn() uses RealDictCursor
    with conn.cursor() as cur:
        cur.execute("SELECT halted FROM amon_breaker_state WHERE id = 1")
        row = cur.fetchone()
return bool(row[0])               # ❌ KeyError: 0 — swallowed as "DB unreachable"

# DO — access by column name
return bool(row["halted"])        # ✓
```

**Two-column queries with the same aliased name collapse in `RealDictCursor`** — the second key overwrites the first. Always use explicit `AS` aliases when selecting multiple aggregates.

```python
# DON'T — both columns alias to "count", second overwrites first in RealDictRow
cur.execute("SELECT COUNT(DISTINCT date), COUNT(*) FROM t WHERE x = %s", (v,))
row = cur.fetchone()
days, total = row[0], row[1]     # ❌ KeyError: 0; and only one key exists anyway

# DO — explicit aliases + named access
cur.execute(
    "SELECT COUNT(DISTINCT date) AS days, COUNT(*) AS total FROM t WHERE x = %s",
    (v,),
)
row = cur.fetchone()
days, total = row["days"], row["total"]   # ✓
```

**Test mocks must return dict-like objects when testing code that uses `get_conn()`.**

```python
# DON'T — mock returns a tuple; column-name access raises TypeError (caught as fail-open)
class _Cur:
    def fetchone(self): return (None,)    # ❌ wrong shape; masks real bug in tests

# DO — mock returns a dict matching real RealDictCursor output
class _Cur:
    def fetchone(self): return {"latest_cached_at": None}  # ✓
```

---

### 4c. Error Handling for DB Operations

- **Catch specific `psycopg2.errors.*` classes** (available since psycopg2 2.8) rather than broad `DatabaseError`. Error names match PostgreSQL condition names exactly.
- **Always call `conn.rollback()`** after any exception before reusing the connection — after a DB error the connection is in aborted-transaction state and every subsequent command raises `InFailedSqlTransaction` until rollback.
- **Log `exc.diag` fields for structured error metadata** (`constraint_name`, `table_name`, `column_name`, `pgcode`) instead of parsing the error string, which is not stable across PG versions.
- **Retry strategy by exception class**: `OperationalError` (connection lost) → retry with backoff; `TransactionRollbackError` (serialization failure) → retry the entire transaction; `IntegrityError` subclasses → surface to caller, do not retry.

```python
import psycopg2.errors as pgerr

try:
    cur.execute("INSERT INTO t (id) VALUES (%s)", (dup_id,))
    conn.commit()
except pgerr.UniqueViolation:
    conn.rollback()
    # handle duplicate key — idempotent upsert or caller error
except pgerr.ForeignKeyViolation as exc:
    conn.rollback()
    logger.warning("FK violation: constraint=%s", exc.diag.constraint_name)
    raise
except psycopg2.OperationalError:
    conn.rollback()
    # retry with backoff or re-raise
    raise
```

```python
# DON'T — catch broad Exception and swallow the connection state
try:
    cur.execute(...)
except Exception:
    pass                    # ❌ connection now in aborted state; next execute fails
```

---

### 4d. Batch Inserts and RETURNING

**Never use `executemany()` for bulk inserts** — it generates one round-trip per row, same as a loop of `execute()`. Benchmark on 32,500 rows: `executemany` ≈ 125 s, `execute_values` ≈ 1.5 s, `copy_expert` ≈ 0.46 s.

```python
# DO — execute_values for bulk inserts (~85x faster than single execute)
from psycopg2.extras import execute_values

execute_values(
    cur,
    "INSERT INTO order_proposals (symbol, qty, created_at) VALUES %s",
    [(r.symbol, r.qty, r.created_at) for r in proposals],
    page_size=500,
)
```

```python
# DO — execute_values with RETURNING to atomically retrieve generated IDs
ids = execute_values(
    cur,
    "INSERT INTO t (a, b) VALUES %s RETURNING id",
    rows,
    fetch=True,
)
```

```python
# DO — RETURNING instead of a follow-up SELECT or MAX() query
cur.execute(
    "INSERT INTO monitoring_cycles (scan_window) VALUES (%s) RETURNING cycle_id",
    (scan_window,),
)
cycle_id = cur.fetchone()["cycle_id"]   # single round-trip, atomic
```

```python
# DON'T — follow-up SELECT to retrieve what was just inserted
cur.execute("INSERT INTO t (a) VALUES (%s)", (val,))
cur.execute("SELECT MAX(id) FROM t")    # ❌ race-prone, extra round-trip
```

```python
# DO — copy_expert (COPY FROM STDIN) for maximum bulk ingest throughput
import io, csv

buf = io.StringIO()
writer = csv.writer(buf)
for row in data:
    writer.writerow(row)
buf.seek(0)
cur.copy_expert("COPY t (a, b, c) FROM STDIN WITH CSV", buf)
```

---

### 4e. Transaction Discipline

- **Keep transactions short** — long-running transactions hold row locks and block autovacuum from reclaiming dead tuples.
- **Commit as soon as a logical unit of work is complete** — psycopg2 starts a transaction on the first `execute()` call; a SELECT left open holds a snapshot and increases table bloat.
- **Use savepoints for partial rollback** within a single transaction, rather than aborting the entire transaction on a risky sub-operation.
- **Use `autocommit = True`** for DDL and PostgreSQL maintenance commands (`CREATE INDEX CONCURRENTLY`, `VACUUM`) which cannot run inside a transaction.

```python
# DO — savepoint for a risky sub-operation inside a larger transaction
cur.execute("SAVEPOINT sp1")
try:
    cur.execute("INSERT INTO risky_table ...")
    cur.execute("RELEASE SAVEPOINT sp1")
except psycopg2.DatabaseError:
    cur.execute("ROLLBACK TO SAVEPOINT sp1")
    # outer transaction continues
```

```python
# DO — autocommit for DDL
conn.autocommit = True
cur.execute("CREATE INDEX CONCURRENTLY idx_symbol ON orders (symbol)")
conn.autocommit = False   # restore for subsequent transactional work
```

---

## 5. Error Handling & Result Patterns

- **Typed exception hierarchy**: module root exception → domain groups → specific exceptions that carry structured data.
- **`Result` return type** for **expected** non-exceptional outcomes (validation failures, lookups that may miss). Reserve exceptions for the genuinely exceptional.
- **Never `except Exception: pass`** — log at WARNING at minimum, with context (`exc_info=True` or `logger.exception`).
- **Catch the narrowest exception** you can actually handle.
- **Don't copy-paste the same try/log/re-raise** — extract to a decorator or context manager.
- **Exception messages use `ErrorCode` enum members, not bare strings.** No raw DB exception text in user-visible or audited output — map to codes, log the detail separately.

```python
# DO — typed hierarchy carrying structured data
class TradingError(Exception):                       # module root
    """Base for all trading-system errors."""

class DataSourceError(TradingError):                 # domain group
    """Market/data adapter failures."""

class StaleQuoteError(DataSourceError):              # specific
    def __init__(self, symbol: str, age_s: float):
        super().__init__(ErrorCode.STALE_QUOTE)
        self.symbol = symbol
        self.age_s = age_s
```

```python
# DO — Result for expected outcomes (validation / lookup)
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    value: object | None = None
    error_code: "ErrorCode | None" = None

def lookup_position(symbol: str) -> Result:
    row = repo.find(symbol)
    if row is None:
        return Result(ok=False, error_code=ErrorCode.POSITION_NOT_FOUND)
    return Result(ok=True, value=row)
```

```python
# DON'T — swallow exceptions silently
try:
    provider_call()
except Exception:
    pass                       # ❌ failure disappears

# DO — narrow catch, logged with context
try:
    provider_call()
except DataSourceError as exc:
    logger.warning("provider call failed: %s", exc, exc_info=True)
    raise
```

```python
# DON'T — raw DB text leaks into audited/user-visible output
return {"error": str(db_exc)}                        # ❌ leaks internals (m-2 pattern)

# DO — map to a code; log detail separately
logger.warning("db write failed", exc_info=True)
return {"error_code": ErrorCode.AUDIT_WRITE_FAILED.value}
```

---

## 6. Project Structure & Import Hygiene

- **src layout**: packages live under `src/`.
- **`__all__` declared on every public module** (and public `__init__.py`).
- **`TYPE_CHECKING` imports** for type-only cross-module references to break circular imports.
- **`from __future__ import annotations`** makes all annotations lazy strings (eliminates most import cycles).
- **Module-internal symbols prefixed with `_`** (single underscore).
- **No cross-adapter / cross-module type imports** — shared DTOs live in a neutral module (e.g. `adapters/types.py`, `schemas/common.py`), never imported sideways between sibling adapters.

```python
# DO — lazy annotations + TYPE_CHECKING for type-only refs
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:                         # not imported at runtime → no cycle
    from trading.portfolio import Portfolio

__all__ = ["MarketAdapter", "build_adapter"]

def attach(portfolio: "Portfolio") -> None: ...

def _internal_helper() -> None: ...       # underscore = module-private
```

```python
# DON'T — sibling adapters importing each other's types (creates coupling + cycles)
# adapters/email_adapter.py
from adapters.broker_adapter import BrokerNotification   # ❌ cross-adapter type import

# DO — shared DTO in a neutral module
# adapters/types.py
@dataclass(frozen=True, slots=True)
class Notification: ...
# both adapters import from adapters.types
```

---

## 7. Type Hints (Modern Syntax)

- **Built-in generics** (PEP 585, Python 3.9+): `list[str]`, `dict[str, int]`, `tuple[str, ...]`.
- **Union syntax** (PEP 604): `str | None` not `Optional[str]`; `str | int` not `Union[str, int]`.
- **Abstract collections** from `collections.abc`: `Sequence`, `Mapping`, `Iterator` — **not** `typing.List` / `typing.Dict` / `typing.Iterator` (deprecated since 3.9).
- **`Annotated[T, ...]`** (PEP 593) for constraint metadata.
- **Avoid `Any`** — use `Protocol`, `object`, or a precise type.

```python
# DO — modern syntax
from collections.abc import Sequence, Mapping, Iterator

def summarize(quotes: Sequence[Quote]) -> dict[str, float]: ...
def stream() -> Iterator[Event]: ...
def find(symbol: str) -> Position | None: ...
```

```python
# DON'T — deprecated typing generics + Optional/Union
from typing import List, Dict, Optional, Union, Iterator   # ❌

def summarize(quotes: List[Quote]) -> Dict[str, float]: ... # ❌
def find(symbol: str) -> Optional[Position]: ...            # ❌ use `Position | None`
def pick(x: Union[str, int]) -> None: ...                   # ❌ use `str | int`
```

```python
# DON'T — Any erases all type safety
def handle(payload: Any) -> Any: ...                        # ❌

# DO — Protocol for structural typing
from typing import Protocol

class SupportsExecute(Protocol):
    def execute(self, sql: str, params: tuple) -> None: ...
```

---

## 8. Testing Patterns

- **`@pytest.mark.parametrize`** for data-driven tests instead of copy-pasted test bodies.
- **Factory fixtures**: one factory closure, zero copy-paste setup.
- **Fixture scoping**: `function` for mutable state, `session` for expensive setup (DB engine, config).
- **Mock at the boundary**: mock external I/O (SMTP, HTTP, subprocess) in unit tests; use a real DB in integration tests.
- **Test names as specifications**: `test_human_approval_blocks_unapproved_doctrine`, not `test_1`.
- **`conftest.py` teardown**: always log exceptions (don't swallow), never re-raise (a teardown failure shouldn't fail the suite).
- **Static DDL cross-check**: parse migration files with `ast` in a `test_schema_consistency.py` to catch routing-map / column-name drift that mocked-DB tests cannot catch.

```python
# DO — parametrize instead of N near-identical test bodies
import pytest

@pytest.mark.parametrize(
    "symbol, valid",
    [("AAPL", True), ("aapl", False), ("TOOLONG", False), ("", False)],
)
def test_ticker_validation(symbol, valid):
    assert is_valid_ticker(symbol) is valid
```

```python
# DO — factory fixture (one factory, no copy-paste setup)
@pytest.fixture
def make_order():
    def _make(symbol="AAPL", qty=1, side="BUY"):
        return Order(symbol=symbol, qty=qty, side=side)
    return _make

def test_human_approval_blocks_unapproved_doctrine(make_order):
    order = make_order(qty=100)
    ...
```

```python
# DO — conftest teardown logs but never re-raises
@pytest.fixture
def db_engine():
    engine = create_engine(...)
    yield engine
    try:
        engine.dispose()
    except Exception:
        logging.getLogger(__name__).warning("engine dispose failed", exc_info=True)
        # never re-raise from teardown
```

```python
# DO — static DDL cross-check with ast (catches drift mocked tests miss)
import ast, pathlib

def test_schema_consistency():
    tree = ast.parse(pathlib.Path("migrations/0001_init.sql.py").read_text())
    declared_cols = _extract_columns(tree)
    assert declared_cols == ROUTING_MAP_COLUMNS
```

---

## 9. Common Hotspot Patterns (trading-system specific)

Flag these as DRY / safety violations during review. Each has an established shared helper in this codebase.

| Pattern to flag | Suggested fix |
|---|---|
| Repeated audit-event dict with same base keys (`operation`, `capability`, `operator_ref`, `comm_event_id`, `channel`) | extract `_build_audit(request, *, status, **extra)` helper |
| Inline `str.partition(":")` typed-id parsing | use shared `parse_typed_id(s)` from `schemas/common.py` |
| `try: provider_call() except DataSourceError: audit(); return Result.fail(...)` repeated per-method | extract `_provider_call(fn, *args, **audit_extra)` on the adapter base |
| Repeated `_now_utc()` + freshness comparison inline | call `_assert_fresh(freshness_until)` base-class helper |
| Same `kill_switch` / `test_mode` guard sequence in non-`BaseAdapter` subclasses | extract `resolve_audit_hook(config, cls_name)` shared function |
| `from typing import List/Dict/Optional/Iterator` in any file | replace with built-ins / `collections.abc` |
| `except Exception as e: pass` or `except Exception as e:` with unused `e` | log `e` at WARNING with `exc_info=True` |

```python
# DON'T — audit dict copy-pasted across every adapter method
detail = {
    "operation": "send", "capability": cap, "operator_ref": op,
    "comm_event_id": cid, "channel": ch, "status": "ok",
}                                            # ❌ repeated 8 times across the file

# DO — one helper, called everywhere
def _build_audit(request, *, status: str, **extra) -> dict:
    return {
        "operation": request.operation,
        "capability": request.capability,
        "operator_ref": request.operator_ref,
        "comm_event_id": request.comm_event_id,
        "channel": request.channel,
        "status": status,
        **extra,
    }
```

```python
# DON'T — inline typed-id parsing scattered across modules
kind, _, raw = some_id.partition(":")        # ❌ duplicated parsing logic

# DO — shared parser
from schemas.common import parse_typed_id
kind, raw = parse_typed_id(some_id)
```

```python
# DON'T — per-method provider-call boilerplate
def fetch_quote(self, symbol):
    try:
        return self._provider.quote(symbol)
    except DataSourceError:
        self._audit(operation="quote", status="fail")
        return Result(ok=False, error_code=ErrorCode.PROVIDER_FAILED)
# ...repeated verbatim in fetch_chain, fetch_news, fetch_bars

# DO — extract onto the adapter base
def _provider_call(self, fn, *args, **audit_extra) -> Result:
    try:
        return Result(ok=True, value=fn(*args))
    except DataSourceError:
        self._audit(status="fail", **audit_extra)
        return Result(ok=False, error_code=ErrorCode.PROVIDER_FAILED)
```
