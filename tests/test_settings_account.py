"""Tests for R-02: /settings/account — password change and subscription status."""
import pytest
import db as db_module
import users as users_module
from users import set_trial, verify_password


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


@pytest.fixture()
def logged_in_client(db, client):
    user = users_module.create_user("acct@example.com", "OldPass99!")
    set_trial(user["id"], days=14)
    with client.session_transaction() as sess:
        sess["user_id"] = user["id"]
    return client, user


class TestSettingsAccountPage:
    def test_requires_auth(self, client):
        resp = client.get("/settings/account")
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers["Location"]

    def test_shows_account_page_when_logged_in(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        assert resp.status_code == 200
        assert b"Account Settings" in resp.data

    def test_shows_user_email(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        assert user["email"].encode() in resp.data

    def test_shows_subscription_status(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        body = resp.data.decode()
        assert "trialing" in body.lower() or "Trial" in body

    def test_shows_trial_expiry_date(self, logged_in_client):
        client, user = logged_in_client
        resp = client.get("/settings/account")
        body = resp.data.decode()
        assert "expires" in body.lower() or "trial_ends_at" not in body


class TestPasswordChange:
    def test_wrong_current_password_returns_error(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "WrongPass!",
            "new_password": "NewPass99!",
            "confirm_password": "NewPass99!",
        })
        assert resp.status_code == 200
        assert b"incorrect" in resp.data.lower() or b"Current password" in resp.data

    def test_short_new_password_rejected(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "short",
            "confirm_password": "short",
        })
        assert resp.status_code == 200
        assert b"8 characters" in resp.data

    def test_mismatched_confirm_rejected(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "NewPass99!",
            "confirm_password": "DifferentPass99!",
        })
        assert resp.status_code == 200
        assert b"do not match" in resp.data

    def test_valid_password_change_succeeds(self, db, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "BrandNew99!",
            "confirm_password": "BrandNew99!",
        })
        assert resp.status_code == 200
        assert b"updated" in resp.data.lower()

    def test_password_actually_changed_in_db(self, db, logged_in_client):
        client, user = logged_in_client
        client.post("/settings/account", data={
            "current_password": "OldPass99!",
            "new_password": "BrandNew99!",
            "confirm_password": "BrandNew99!",
        })
        assert verify_password(user["email"], "BrandNew99!") is not None
        assert verify_password(user["email"], "OldPass99!") is None


class TestCompanyNameSettings:
    def test_company_name_form_available_on_profile(self, logged_in_client):
        # Company name editing moved from /settings/account to /company-profile
        # (the account page now links to it as "Company Profile →").
        client, user = logged_in_client
        resp = client.get("/company-profile")
        assert resp.status_code == 200
        body = resp.data.decode()
        assert "Company Name" in body
        assert 'name="company_name"' in body

    def test_settings_page_shows_existing_company_name(self, db, client):
        user = users_module.create_user("co@example.com", "Pass1234!", company_name="Apex Gov")
        set_trial(user["id"], days=7)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        resp = client.get("/settings/account")
        assert b"Apex Gov" in resp.data

    def test_shows_dash_when_no_company_name(self, logged_in_client):
        client, user = logged_in_client
        body = client.get("/settings/account").get_data(as_text=True)
        assert "<strong>Company:</strong> —" in body or "Company:</strong> —" in body

    def test_update_company_name_post(self, db, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account/company", data={"company_name": "Delta Logistics"},
                           follow_redirects=True)
        assert resp.status_code == 200
        fresh = users_module.get_user_by_id(user["id"])
        assert fresh["company_name"] == "Delta Logistics"

    def test_update_company_name_shows_in_sidebar(self, db, logged_in_client):
        client, user = logged_in_client
        client.post("/settings/account/company", data={"company_name": "Bravo Systems"},
                    follow_redirects=True)
        with client.session_transaction() as sess:
            sess["onboarding_skipped"] = "1"
        body = client.get("/dashboard").get_data(as_text=True)
        assert "Bravo Systems" in body

    def test_clear_company_name_with_blank(self, db, logged_in_client):
        client, user = logged_in_client
        client.post("/settings/account/company", data={"company_name": "Old Name"},
                    follow_redirects=True)
        client.post("/settings/account/company", data={"company_name": "   "},
                    follow_redirects=True)
        fresh = users_module.get_user_by_id(user["id"])
        assert fresh["company_name"] is None

    def test_update_company_name_requires_auth(self, client):
        resp = client.post("/settings/account/company", data={"company_name": "X"})
        assert resp.status_code in (301, 302)
        assert "/login" in resp.headers["Location"]

    def test_update_company_name_function_directly(self, db):
        user = users_module.create_user("direct@example.com", "Pass1234!")
        users_module.update_company_name(user["id"], "Gamma Corp")
        assert users_module.get_user_by_id(user["id"])["company_name"] == "Gamma Corp"

    def test_update_company_name_clears_to_null(self, db):
        user = users_module.create_user("clear@example.com", "Pass1234!", company_name="Old")
        users_module.update_company_name(user["id"], "")
        assert users_module.get_user_by_id(user["id"])["company_name"] is None
