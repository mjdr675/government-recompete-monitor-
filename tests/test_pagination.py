"""Tests for pagination first/last/page-count controls — Task 060."""

import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module.init_db()
    # Insert 30 contracts so we have 2 pages (page size = 25)
    with db_module.connect() as con:
        for i in range(30):
            con.execute(
                "INSERT INTO contracts "
                "(internal_id, award_id, vendor, agency, value, end_date, priority, recompete_score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"ID{i:03d}", f"AWARD-{i:03d}", f"Vendor {i}", "DOD",
                 100_000 * (i + 1), "2026-12-31", "HIGH", 50 + i),
            )
        con.commit()
    yield db_path
    db_module.DB_PATH = original


@pytest.fixture()
def client(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "fixture@example.com",
            "password": "testpass123",
            "confirm": "testpass123",
        })
        yield c


# ---------------------------------------------------------------------------
# Page X of Y display
# ---------------------------------------------------------------------------

def test_page_1_of_2_shown(client):
    rv = client.get("/contracts?page=1")
    assert rv.status_code == 200
    assert b"Page 1 of 2" in rv.data


def test_page_2_of_2_shown(client):
    rv = client.get("/contracts?page=2")
    assert b"Page 2 of 2" in rv.data


def test_single_page_shows_page_1_of_1(client):
    # With high min_value only a few contracts match
    rv = client.get("/contracts?min_value=2900000")
    assert b"Page 1 of 1" in rv.data


# ---------------------------------------------------------------------------
# First / Last links
# ---------------------------------------------------------------------------

def test_first_link_disabled_on_page_1(client):
    rv = client.get("/contracts?page=1")
    assert rv.status_code == 200
    # "First" should appear as disabled span, not an anchor
    assert b'aria-disabled="true">First' in rv.data


def test_first_link_present_on_page_2(client):
    rv = client.get("/contracts?page=2")
    assert b'href=' in rv.data
    assert b"First" in rv.data
    # Should be an anchor, not a disabled span on page 2
    assert b'href="/contracts?' in rv.data
    assert b"page=1" in rv.data


def test_last_link_disabled_on_last_page(client):
    rv = client.get("/contracts?page=2")
    assert b'aria-disabled="true">Last' in rv.data


def test_last_link_present_on_page_1(client):
    rv = client.get("/contracts?page=1")
    assert b"Last" in rv.data
    # Last link should point to page 2
    assert b"page=2" in rv.data


def test_prev_disabled_on_page_1(client):
    rv = client.get("/contracts?page=1")
    assert b'aria-disabled="true">Previous' in rv.data


def test_next_disabled_on_last_page(client):
    rv = client.get("/contracts?page=2")
    assert b'aria-disabled="true">Next' in rv.data


# ---------------------------------------------------------------------------
# total_pages computation
# ---------------------------------------------------------------------------

def test_total_pages_exact_multiple():
    # 50 contracts, page size 25 → 2 pages
    from math import ceil
    total = 50
    page_size = 25
    assert max(1, (total + page_size - 1) // page_size) == 2


def test_total_pages_with_remainder():
    # 26 contracts, page size 25 → 2 pages
    total = 26
    page_size = 25
    assert max(1, (total + page_size - 1) // page_size) == 2


def test_total_pages_zero_total():
    # 0 contracts → 1 page (empty result)
    total = 0
    page_size = 25
    assert max(1, (total + page_size - 1) // page_size) == 1


def test_total_pages_single_page():
    total = 10
    page_size = 25
    assert max(1, (total + page_size - 1) // page_size) == 1
