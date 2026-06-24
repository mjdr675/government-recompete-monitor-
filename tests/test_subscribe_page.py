"""Tests for R-07: improved /subscribe page."""
import pytest
import db as db_module
import users as users_module
from users import set_trial


@pytest.fixture()
def db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module.init_db()
    return db_path


@pytest.fixture()
def client(db):
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


class TestSubscribePage:
    def test_subscribe_accessible_without_login(self, client):
        resp = client.get("/subscribe")
        assert resp.status_code == 200

    def test_subscribe_shows_price(self, client):
        resp = client.get("/subscribe")
        assert b"49" in resp.data

    def test_subscribe_shows_checkout_cta(self, client):
        # The subscribe page now uses self-serve Stripe Payment Links (plan CTA
        # buttons) instead of a server-side /create-checkout-session form.
        resp = client.get("/subscribe")
        assert b"btn-cta-primary" in resp.data

    def test_subscribe_shows_feature_list(self, client):
        resp = client.get("/subscribe")
        body = resp.data.decode()
        assert "contract" in body.lower()
        assert "alert" in body.lower()

    def test_subscribe_shows_expired_banner_when_param_set(self, client):
        resp = client.get("/subscribe?expired=1")
        body = resp.data.decode()
        assert "trial has ended" in body.lower() or "expired" in body.lower()

    def test_subscribe_shows_cancel_anytime(self, client):
        resp = client.get("/subscribe")
        body = resp.data.decode()
        assert "cancel" in body.lower()

    def test_subscribe_shows_stripe_trust_signal(self, client):
        resp = client.get("/subscribe")
        body = resp.data.decode()
        assert "stripe" in body.lower()
