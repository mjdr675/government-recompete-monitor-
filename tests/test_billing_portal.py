"""Tests for POST /billing/portal route (task F-2)."""
import pytest
from unittest.mock import MagicMock
import db as db_module
import users as users_module
import payments as payments_module


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(db, monkeypatch):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


class TestBillingPortal:
    def test_redirects_unauthenticated_to_login(self, client):
        resp = client.post("/billing/portal")
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"]

    def test_redirects_to_index_when_no_stripe_customer(self, client, db):
        user = users_module.create_user("portal@example.com", "pass123")
        _login(client, user["id"])
        resp = client.post("/billing/portal")
        assert resp.status_code == 302
        assert "/" in resp.headers["Location"]

    def test_redirects_to_portal_url_when_customer_exists(self, client, db, monkeypatch):
        user = users_module.create_user("portal2@example.com", "pass123")
        users_module.set_subscription(user["id"], "cus_portal", "active")
        _login(client, user["id"])

        mock_portal = MagicMock()
        mock_portal.url = "https://billing.stripe.com/session/test"
        calls = []

        def fake_portal(customer_id, return_url):
            calls.append({"customer_id": customer_id, "return_url": return_url})
            return mock_portal

        monkeypatch.setattr(payments_module.service, "create_billing_portal_session", fake_portal)
        resp = client.post("/billing/portal")
        assert resp.status_code == 303
        assert resp.headers["Location"] == "https://billing.stripe.com/session/test"
        assert calls == [{"customer_id": "cus_portal", "return_url": "http://localhost/"}]

    def test_redirects_to_index_on_stripe_error(self, client, db, monkeypatch):
        user = users_module.create_user("portal3@example.com", "pass123")
        users_module.set_subscription(user["id"], "cus_err", "active")
        _login(client, user["id"])

        def raise_exc(customer_id, return_url):
            raise Exception("API error")

        monkeypatch.setattr(payments_module.service, "create_billing_portal_session", raise_exc)
        resp = client.post("/billing/portal")
        assert resp.status_code == 302
        assert "/" in resp.headers["Location"]
