"""Landing-page contact section + Recompete brand treatment (customer-facing tasks)."""
import pytest
import db as db_module


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    db_module.init_db()
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["WTF_CSRF_ENABLED"] = False
    with app_module.app.test_client() as c:
        yield c


def test_landing_has_contact_section(client):
    body = client.get("/").get_data(as_text=True)
    assert 'id="contact"' in body
    assert "mailto:hello@recompete.us" in body


def test_brand_shows_recompete_not_dot_us(client):
    body = client.get("/").get_data(as_text=True)
    assert "Recompete" in body
    # header brand mark is present, and the brand text no longer reads "Recompete.us"
    assert "brand-mark" in body
    assert "Recompete.us" not in body
