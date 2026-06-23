# Task 108 — Add structured JSON log format to app.py

**Epic:** E05
**Milestone:** M3
**Sprint:** G-3
**Complexity:** S
**Status:** QUEUED

## Objective

Replace the current ad-hoc log format with structured JSON lines so Railway log drain
(and Sentry breadcrumbs) can parse fields without regex scraping.

## Requirements

- In `app.py`, replace the existing `RotatingFileHandler` / `StreamHandler` log
  configuration with a `logging.Formatter` subclass that emits JSON:
  ```python
  import json as _json

  class _JsonFormatter(logging.Formatter):
      def format(self, record: logging.LogRecord) -> str:
          payload = {
              "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
              "level": record.levelname,
              "logger": record.name,
              "msg": record.getMessage(),
          }
          if record.exc_info:
              payload["exc"] = self.formatException(record.exc_info)
          return _json.dumps(payload)
  ```
- Apply `_JsonFormatter` to all handlers attached to the root logger (both the
  `StreamHandler` writing to stdout and the `RotatingFileHandler` if present).
- In `tasks.py`, apply the same formatter to the root logger at module level so
  Celery worker output is also structured.
- Existing `logger.info(...)` / `logger.error(...)` calls are unchanged — only the
  formatter changes.
- Do NOT change log levels or remove existing handlers.

## Acceptance Criteria

- [ ] `app.py` logger emits JSON lines (each log record is valid JSON)
- [ ] JSON output contains `ts`, `level`, `logger`, `msg` keys
- [ ] `exc` key appears when an exception is logged with `exc_info=True`
- [ ] All existing tests still pass (log format does not affect route behaviour)

## Hard Dependencies

- Task 101: Sentry initialized — recommended complete first (G-1)

## DB Changes

None.

## API Changes

None.

## Frontend Changes

None.

## New Dependencies

None.

## Testing

Add 2 tests to `tests/test_app.py`:
- `test_json_log_format_emits_valid_json`: create a `_JsonFormatter` instance, call
  `format()` on a fabricated `LogRecord`, parse the result with `json.loads()` — assert
  no parse error and `"level"` key present.
- `test_json_log_format_includes_exc_key`: create `LogRecord` with `exc_info` set to
  a caught exception tuple; assert `"exc"` key in parsed JSON.

## Suggested Commit Message

`feat: add structured JSON log format to app.py and tasks.py (Task 108)`
