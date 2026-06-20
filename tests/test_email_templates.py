"""Tests for email Jinja2 templates."""

import pytest
import db as db_module


@pytest.fixture()
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DB_PATH", db_path)
    db_module._cached_engine.cache_clear()
    monkeypatch.delenv("DATABASE_URL", raising=False)
    db_module.init_db()
    yield db_path
    db_module._cached_engine.cache_clear()


@pytest.fixture()
def app_ctx(test_db):
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["WTF_CSRF_ENABLED"] = False
    flask_app.app.config["RATELIMIT_ENABLED"] = False
    flask_app.app.secret_key = "test-secret"
    with flask_app.app.app_context():
        yield flask_app.app


def test_welcome_html_renders(app_ctx):
    from flask import render_template
    html = render_template(
        "email/welcome.html",
        user_email="test@example.com",
        app_url="https://govrecompete.com",
    )
    assert "test@example.com" in html
    assert "https://govrecompete.com/contracts" in html
    assert "Browse Contracts" in html


def test_welcome_txt_renders(app_ctx):
    from flask import render_template
    txt = render_template(
        "email/welcome.txt",
        user_email="test@example.com",
        app_url="https://govrecompete.com",
    )
    assert "test@example.com" in txt
    assert "https://govrecompete.com/contracts" in txt


def test_welcome_html_has_no_style_blocks(app_ctx):
    from flask import render_template
    html = render_template(
        "email/welcome.html",
        user_email="u@example.com",
        app_url="https://govrecompete.com",
    )
    assert "<style" not in html
