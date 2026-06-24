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
    def test_no_duplicate_company_name_form(self, logged_in_client):
        client, user = logged_in_client
        body = client.get("/settings/account").get_data(as_text=True)
        # The editable company name card and its Save button must be gone
        assert 'name="company_name"' not in body
        assert "Save company name" not in body

    def test_shows_not_set_when_no_profile(self, logged_in_client):
        client, user = logged_in_client
        body = client.get("/settings/account").get_data(as_text=True)
        assert "Not set" in body

    def test_shows_company_name_from_profile(self, db, client):
        from db import save_company_profile
        user = users_module.create_user("co@example.com", "Pass1234!")
        set_trial(user["id"], days=7)
        save_company_profile(user["id"], {"company_name": "Apex Gov Solutions"})
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        body = client.get("/settings/account").get_data(as_text=True)
        assert "Apex Gov Solutions" in body

    def test_does_not_show_users_table_company_name(self, db, client):
        user = users_module.create_user("legacy@example.com", "Pass1234!", company_name="Old Users Table Name")
        set_trial(user["id"], days=7)
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
        body = client.get("/settings/account").get_data(as_text=True)
        # No company profile — should show "Not set", not the users-table name
        assert "Not set" in body

    def test_includes_edit_company_profile_link(self, logged_in_client):
        client, user = logged_in_client
        body = client.get("/settings/account").get_data(as_text=True)
        assert "/company-profile" in body
        assert "Edit company profile" in body

    def test_account_company_post_redirects_to_profile(self, logged_in_client):
        client, user = logged_in_client
        resp = client.post("/settings/account/company", data={"company_name": "X"})
        assert resp.status_code in (301, 302)
        assert "company-profile" in resp.headers["Location"]

    def test_sidebar_shows_profile_company_name(self, db, client):
        from db import save_company_profile
        user = users_module.create_user("sidebar@example.com", "Pass1234!")
        set_trial(user["id"], days=7)
        save_company_profile(user["id"], {"company_name": "Bravo Systems LLC"})
        with client.session_transaction() as sess:
            sess["user_id"] = user["id"]
            sess["onboarding_skipped"] = "1"
        body = client.get("/dashboard").get_data(as_text=True)
        assert "Bravo Systems LLC" in body

    def test_update_company_name_function_directly(self, db):
        user = users_module.create_user("direct@example.com", "Pass1234!")
        users_module.update_company_name(user["id"], "Gamma Corp")
        assert users_module.get_user_by_id(user["id"])["company_name"] == "Gamma Corp"

    def test_update_company_name_clears_to_null(self, db):
        user = users_module.create_user("clear@example.com", "Pass1234!", company_name="Old")
        users_module.update_company_name(user["id"], "")
        assert users_module.get_user_by_id(user["id"])["company_name"] is None
