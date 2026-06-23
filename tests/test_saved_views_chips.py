"""Tests for Phase 1 discovery UX: active-filter chips + quick-view presets.

Covers the pure helpers in views.py (active_filter_chips, quick_views,
_format_chip_value) and their integration into the /contracts page.
"""
from urllib.parse import parse_qs, urlparse

import pytest

import db as db_module
from views import (
    SAVED_VIEWS,
    QUICK_VIEW_KEYS,
    active_filter_chips,
    quick_views,
    _format_chip_value,
)


# ---------------------------------------------------------------------------
# _format_chip_value
# ---------------------------------------------------------------------------

class TestFormatChipValue:
    def test_days_suffix(self):
        assert _format_chip_value("days", "90") == "90 days"

    def test_priority_title_case(self):
        assert _format_chip_value("priority", "CRITICAL") == "Critical"

    def test_status_open(self):
        assert _format_chip_value("status", "open") == "Open only"

    def test_status_expired(self):
        assert _format_chip_value("status", "expired") == "Expired"

    def test_min_value_millions(self):
        assert _format_chip_value("min_value", "1000000") == "$1M+"

    def test_min_value_multiple_millions(self):
        assert _format_chip_value("min_value", "5000000") == "$5M+"

    def test_min_value_thousands(self):
        assert _format_chip_value("min_value", "500000") == "$500K+"

    def test_min_value_non_numeric_falls_back(self):
        assert _format_chip_value("min_value", "abc") == "abc"

    def test_plain_value_passthrough(self):
        assert _format_chip_value("agency", "DEFENSE") == "DEFENSE"


# ---------------------------------------------------------------------------
# active_filter_chips
# ---------------------------------------------------------------------------

class TestActiveFilterChips:
    def test_no_filters_returns_empty(self):
        assert active_filter_chips({}) == []

    def test_blank_values_ignored(self):
        assert active_filter_chips({"q": "", "agency": "  ", "state": ""}) == []

    def test_single_filter_chip(self):
        chips = active_filter_chips({"category": "Cleaning"})
        assert len(chips) == 1
        assert chips[0]["key"] == "category"
        assert chips[0]["label"] == "Category"
        assert chips[0]["value"] == "Cleaning"

    def test_remove_url_drops_only_that_filter(self):
        chips = active_filter_chips({"category": "Cleaning", "state": "TX"})
        by_key = {c["key"]: c for c in chips}
        # Removing category keeps state, drops category
        cat_q = parse_qs(urlparse(by_key["category"]["remove_url"]).query)
        assert "category" not in cat_q
        assert cat_q.get("state") == ["TX"]
        # Removing state keeps category, drops state
        st_q = parse_qs(urlparse(by_key["state"]["remove_url"]).query)
        assert "state" not in st_q
        assert st_q.get("category") == ["Cleaning"]

    def test_remove_url_for_only_filter_is_bare_contracts(self):
        chips = active_filter_chips({"state": "TX"})
        assert chips[0]["remove_url"] == "/contracts"

    def test_state_category_agency_all_present(self):
        chips = active_filter_chips(
            {"state": "TX", "category": "IT", "agency": "DEFENSE"}
        )
        keys = {c["key"] for c in chips}
        assert keys == {"state", "category", "agency"}

    def test_chip_order_is_stable(self):
        # Insertion order of args should not affect chip order (driven by _CHIP_LABELS)
        chips = active_filter_chips(
            {"status": "open", "q": "lawn", "category": "Grounds"}
        )
        keys = [c["key"] for c in chips]
        assert keys == ["q", "category", "status"]

    def test_sort_and_dir_preserved_in_remove_url(self):
        chips = active_filter_chips(
            {"category": "IT", "sort": "value", "dir": "asc"}
        )
        q = parse_qs(urlparse(chips[0]["remove_url"]).query)
        assert q.get("sort") == ["value"]
        assert q.get("dir") == ["asc"]

    def test_page_reset_on_filter_removal(self):
        chips = active_filter_chips(
            {"category": "IT", "state": "TX", "page": "3"}
        )
        for chip in chips:
            q = parse_qs(urlparse(chip["remove_url"]).query)
            assert "page" not in q

    def test_mode_toggles_preserved(self):
        chips = active_filter_chips(
            {"category": "IT", "discover": "1", "in_pipeline": "1"}
        )
        q = parse_qs(urlparse(chips[0]["remove_url"]).query)
        assert q.get("discover") == ["1"]
        assert q.get("in_pipeline") == ["1"]

    def test_non_filter_param_not_shown_as_chip(self):
        chips = active_filter_chips({"sort": "value", "dir": "desc"})
        assert chips == []

    def test_days_value_formatted(self):
        chips = active_filter_chips({"days": "90"})
        assert chips[0]["value"] == "90 days"


# ---------------------------------------------------------------------------
# quick_views
# ---------------------------------------------------------------------------

class TestQuickViews:
    def test_returns_list_of_id_label(self):
        qv = quick_views()
        assert isinstance(qv, list)
        assert all("id" in v and "label" in v for v in qv)

    def test_all_quick_keys_exist_in_saved_views(self):
        for key in QUICK_VIEW_KEYS:
            assert key in SAVED_VIEWS, f"QUICK_VIEW_KEYS references missing preset {key}"

    def test_labels_match_saved_views(self):
        for v in quick_views():
            assert v["label"] == SAVED_VIEWS[v["id"]]["label"]

    def test_skips_missing_keys(self, monkeypatch):
        import views as views_module
        monkeypatch.setattr(views_module, "QUICK_VIEW_KEYS",
                            ["expiring-soon", "__does-not-exist__"])
        qv = views_module.quick_views()
        ids = [v["id"] for v in qv]
        assert "__does-not-exist__" not in ids
        assert "expiring-soon" in ids


# ---------------------------------------------------------------------------
# /contracts integration
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret-key"
    with flask_app.app.test_client() as c:
        c.post("/register", data={
            "email": "chips@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        yield c
    db_module._cached_engine.cache_clear()


class TestContractsPageIntegration:
    def test_quick_views_render(self, client):
        rv = client.get("/contracts")
        assert rv.status_code == 200
        assert b"Quick views:" in rv.data
        assert b"/views/expiring-soon" in rv.data

    def test_all_views_link_present(self, client):
        rv = client.get("/contracts")
        assert b'href="/views"' in rv.data

    def test_active_filter_chip_renders(self, client):
        rv = client.get("/contracts?category=Cleaning")
        assert rv.status_code == 200
        assert b"Active filters:" in rv.data
        assert b"Cleaning" in rv.data

    def test_no_active_filters_no_chip_row(self, client):
        rv = client.get("/contracts")
        assert b"Active filters:" not in rv.data

    def test_state_chip_remove_link(self, client):
        rv = client.get("/contracts?state=TX&category=IT")
        assert rv.status_code == 200
        # The remove link for state should preserve category
        assert b"Active filters:" in rv.data
        body = rv.data.decode()
        assert "category=IT" in body
