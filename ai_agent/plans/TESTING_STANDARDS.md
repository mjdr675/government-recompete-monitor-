# TESTING STANDARDS
# Rules for writing and maintaining tests in this project

---

## 1. Test Count Rule

The test count must increase with every task that changes application code.
It may never decrease. If a refactor breaks existing tests, fix the tests before committing.

Current baseline: 84 tests (as of Task 044).
Target by milestone:
- M1: ≥ 130 tests
- M2: ≥ 200 tests
- M3: ≥ 280 tests
- M4: ≥ 350 tests (≥ 80% coverage)

---

## 2. What to Test

Every task must include tests for:

| Change type | What to test |
|---|---|
| New DB function | Returns correct result, handles None/empty, no SQL injection |
| New route | 200 on valid input, 400/403/404 on invalid, auth required |
| New analytics query | Correct aggregation, empty DB returns safe defaults |
| New Celery task | Task runs without error, correct output stored |
| New email | Email queued with correct recipient, subject, body |
| New AI call | Correct prompt built, response parsed, fallback on API error |
| New form | Valid submit succeeds, invalid submit returns error, CSRF checked |
| New model/table | Row inserts, row updates, uniqueness constraints enforced |

---

## 3. Test File Organization

```
tests/
├── test_app.py          — Flask route tests (add route tests here)
├── test_auth.py         — Auth and session tests
├── test_db.py           — Database function tests
├── test_analytics.py    — Analytics query tests
├── test_hubspot_service.py
├── test_memory.py       — AI agent repo memory tests
├── test_patcher.py      — AI agent patcher tests
├── test_queue_manager.py
├── test_recovery.py
├── test_loop.py
├── test_eng_memory.py
└── integration/         — Integration tests (PostgreSQL, full flows)
    └── test_flows.py
```

Add tests to the most relevant existing file. Create a new file only if a new
major subsystem is added (e.g., `test_capture.py` for capture workspace).

---

## 4. Test Isolation Rules

- **Never use the live `contracts.db`** — all tests use `tmp_path` fixtures
- Monkey-patch `db.DB_PATH` per test:
  ```python
  @pytest.fixture
  def db_path(tmp_path, monkeypatch):
      path = str(tmp_path / "test.db")
      monkeypatch.setattr("db.DB_PATH", path)
      init_db()
      return path
  ```
- Flask test client: use the `app.test_client()` fixture, not a real server
- External APIs (SAM.gov, Anthropic, Stripe, HubSpot): always mock with `unittest.mock.patch`
- Redis/Celery: use `task.apply()` (eager mode) in tests, not async dispatch
- Never share state between tests — each test gets a fresh DB

---

## 5. Naming Conventions

```python
def test_<function_or_route>_<scenario>():
    ...

# Examples:
def test_get_contracts_min_value_filter():
def test_get_contracts_returns_empty_when_no_matches():
def test_login_returns_redirect_on_success():
def test_login_returns_error_on_wrong_password():
def test_create_watchlist_requires_auth():
def test_upsert_contract_handles_missing_internal_id():
```

---

## 6. What NOT to Test

- Third-party library internals (SQLAlchemy internals, Flask internals)
- Trivial getters/setters with no logic
- Template HTML structure (test route returns 200, not that `<h1>` exists)
- Log output (test behavior, not log messages)
- Exact error message strings (test that an error is returned, not its exact text)

---

## 7. Mocking External Services

### Anthropic API
```python
from unittest.mock import patch, MagicMock

def test_ai_analysis_generated(db_path):
    mock_response = MagicMock()
    mock_response.content[0].text = "Analysis text"
    with patch("anthropic.Anthropic.messages.create", return_value=mock_response):
        result = generate_analysis("contract_id")
    assert result is not None
```

### SAM.gov API
```python
with patch("requests.get") as mock_get:
    mock_get.return_value.status_code = 200
    mock_get.return_value.json.return_value = {"entityData": [...]}
    result = lookup_by_uei("ABC123456789")
assert result["legal_name"] == "Expected Corp"
```

### Stripe
```python
with patch("stripe.checkout.Session.create") as mock_stripe:
    mock_stripe.return_value = MagicMock(url="https://checkout.stripe.com/...")
    resp = client.post("/create-checkout-session")
assert resp.status_code == 303
```

---

## 8. Test for Security Properties

Every new route that modifies data must have:
```python
def test_<route>_requires_auth(client):
    resp = client.post("/route", data={...})
    assert resp.status_code == 302  # redirect to login
    assert "/login" in resp.headers["Location"]

def test_<route>_viewer_cannot_write(client_as_viewer):
    resp = client_as_viewer.post("/route", data={...})
    assert resp.status_code == 403
```

Every new route that accesses org data must have:
```python
def test_<route>_cannot_access_other_org_data(client_org_a, org_b_data):
    resp = client_org_a.get(f"/resource/{org_b_data.id}")
    assert resp.status_code == 404  # not 403 — don't reveal existence
```

---

## 9. Running Tests

```bash
# All tests (unit + integration):
pytest -q

# Unit tests only (fast, SQLite):
pytest -q --ignore=tests/integration

# Integration tests only (PostgreSQL required):
pytest tests/integration -m integration

# With coverage:
pytest --cov=. --cov-report=term-missing -q
```

Tests must pass before any commit. Exit code 0 required (exit code 5 = no tests
collected is also acceptable for new files that don't yet have tests).

---

## 10. Test Fixtures Reference

Reuse these fixtures — do not rewrite them:

```python
# In conftest.py (or at top of test file):
@pytest.fixture
def app():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test"
    return app

@pytest.fixture
def client(app, db_path):
    # Returns authenticated test client (pre-registered user)
    with app.test_client() as c:
        c.post("/register", data={"email": "test@test.com", "password": "password123", "confirm": "password123"})
        yield c
```

See existing `tests/test_auth.py` and `tests/test_app.py` for canonical fixture patterns.
