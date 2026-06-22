"""Contract search: robust to real-world queries + partial-word (prefix) matching.

Regression for the bug where company-name searches with punctuation (AT&T, "Booz,
Allen", quotes, parens) raised sqlite OperationalError → HTTP 500. Search now tokenizes
the query into safe terms and prefix-matches each, so those queries work and partial
words ("lockhe" → "Lockheed") match.
"""
import pytest

import db as db_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    db_module.init_db()
    db_module.save_snapshot("2026-06-22", [
        {"internal_id": "S1", "vendor": "AT&T Corp", "agency": "DEFENSE",
         "award_id": "A1", "value": 1_000_000, "recompete_score": 80, "priority": "HIGH"},
        {"internal_id": "S2", "vendor": "Lockheed Martin", "agency": "NAVY",
         "award_id": "A2", "value": 2_000_000, "recompete_score": 85, "priority": "HIGH"},
        {"internal_id": "S3", "vendor": "Booz Allen Hamilton", "agency": "ARMY",
         "award_id": "A3", "value": 500_000, "recompete_score": 60, "priority": "MEDIUM"},
        {"internal_id": "S4", "vendor": "ABC Janitorial Services", "agency": "GSA",
         "award_id": "A4", "value": 250_000, "recompete_score": 55, "priority": "MEDIUM"},
    ])
    return tmp_path


def _vendors(result):
    return sorted(r["vendor"] for r in result["contracts"])


# ── tokenizer ──────────────────────────────────────────────────────────────────
class TestTokens:
    def test_strips_punctuation(self):
        assert db_module.search_tokens("AT&T") == ["at", "t"]
        assert db_module.search_tokens("Booz, Allen") == ["booz", "allen"]

    def test_all_punctuation_is_empty(self):
        assert db_module.search_tokens('"&&()') == []
        assert db_module.search_tokens("   ") == []

    def test_bounded(self):
        assert len(db_module.search_tokens(" ".join(str(i) for i in range(50)))) == 8


# ── search no longer crashes on real-world punctuation ──────────────────────────
class TestNoCrash:
    @pytest.mark.parametrize("q", ['AT&T', 'Booz, Allen', 'quote"here', '(unbalanced',
                                   'C++ developer', "O'Brien", '&&&'])
    def test_special_chars_do_not_error(self, db, q):
        # must not raise (previously sqlite3.OperationalError → 500)
        result = db_module.get_contracts(q=q)
        assert isinstance(result["total"], int)

    def test_company_with_ampersand_is_found(self, db):
        assert _vendors(db_module.get_contracts(q="AT&T")) == ["AT&T Corp"]

    def test_company_with_comma_is_found(self, db):
        assert _vendors(db_module.get_contracts(q="Booz, Allen")) == ["Booz Allen Hamilton"]


# ── partial word (prefix) matching ──────────────────────────────────────────────
class TestPrefix:
    def test_partial_vendor(self, db):
        assert _vendors(db_module.get_contracts(q="lockhe")) == ["Lockheed Martin"]

    def test_partial_keyword(self, db):
        assert _vendors(db_module.get_contracts(q="janitor")) == ["ABC Janitorial Services"]

    def test_multi_token_is_and(self, db):
        # both terms must match the same contract
        assert _vendors(db_module.get_contracts(q="booz allen")) == ["Booz Allen Hamilton"]
        assert db_module.get_contracts(q="booz lockheed")["total"] == 0

    def test_matches_agency(self, db):
        assert _vendors(db_module.get_contracts(q="navy")) == ["Lockheed Martin"]


# ── empty / gibberish behavior ──────────────────────────────────────────────────
class TestEmptyAndGibberish:
    def test_gibberish_returns_no_rows_not_everything(self, db):
        assert db_module.get_contracts(q="zzznomatch")["total"] == 0

    def test_punctuation_only_returns_no_rows(self, db):
        # a query with no usable terms matches nothing (not the whole table)
        assert db_module.get_contracts(q="&&&")["total"] == 0

    def test_blank_query_returns_all(self, db):
        assert db_module.get_contracts(q="")["total"] == 4
