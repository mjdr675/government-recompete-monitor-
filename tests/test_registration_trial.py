"""Test that registration sets a 14-day trial (task F-8)."""
import pytest
from datetime import datetime, timezone
import db as db_module
import users as users_module


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


class TestRegistrationTrial:
    def test_register_sets_trial_ends_at(self, client, db):
        resp = client.post("/register", data={
            "email": "newuser@example.com",
            "password": "password123",
            "confirm": "password123",
        }, follow_redirects=False)
        assert resp.status_code in (302, 303)

        user = users_module.get_user_by_email("newuser@example.com")
        assert user is not None
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["trial_ends_at"] is not None
        trial_end = datetime.fromisoformat(fetched["trial_ends_at"])
        delta = trial_end - datetime.now(timezone.utc)
        assert delta.total_seconds() > 13 * 86400

    def test_register_leaves_subscription_status_trialing(self, client, db):
        client.post("/register", data={
            "email": "trial2@example.com",
            "password": "password123",
            "confirm": "password123",
        })
        user = users_module.get_user_by_email("trial2@example.com")
        fetched = users_module.get_user_by_id(user["id"])
        assert fetched["subscription_status"] == "trialing"
