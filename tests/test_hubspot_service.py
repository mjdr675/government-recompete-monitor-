"""
Tests for hubspot_service.py — all HubSpot API calls are mocked so no real
network requests are made.
"""

import importlib
from unittest.mock import MagicMock, call, patch

import pytest
import hubspot_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_contact(contact_id="123"):
    c = MagicMock()
    c.id = contact_id
    return c


def _mock_deal(deal_id="456"):
    d = MagicMock()
    d.id = deal_id
    return d


def _mock_note(note_id="789"):
    n = MagicMock()
    n.id = note_id
    return n


# ---------------------------------------------------------------------------
# _split_name
# ---------------------------------------------------------------------------

def test_split_name_two_words():
    assert hubspot_service._split_name("Jane Smith") == ("Jane", "Smith")


def test_split_name_three_words():
    assert hubspot_service._split_name("Mary Jane Watson") == ("Mary", "Jane Watson")


def test_split_name_one_word():
    assert hubspot_service._split_name("Prince") == ("Prince", "")


def test_split_name_empty():
    assert hubspot_service._split_name("") == ("", "")


def test_split_name_extra_spaces():
    assert hubspot_service._split_name("  John   Doe  ") == ("John", "Doe")


# ---------------------------------------------------------------------------
# upsert_contact — no token
# ---------------------------------------------------------------------------

def test_upsert_contact_no_token(monkeypatch):
    monkeypatch.setattr(hubspot_service, "HUBSPOT_ACCESS_TOKEN", "")
    result = hubspot_service.upsert_contact("test@example.com")
    assert result is None


# ---------------------------------------------------------------------------
# upsert_contact — create new contact
# ---------------------------------------------------------------------------

@patch("hubspot_service._client")
def test_upsert_contact_creates_when_not_found(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.contacts.search_api.do_search.return_value.results = []
    client.crm.contacts.basic_api.create.return_value = _mock_contact("111")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.upsert_contact(
        "new@example.com", name="Alice Doe", company="Acme", phone="555-0100"
    )

    assert result == "111"
    client.crm.contacts.basic_api.create.assert_called_once()
    client.crm.contacts.basic_api.update.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_contact — update existing contact
# ---------------------------------------------------------------------------

@patch("hubspot_service._client")
def test_upsert_contact_updates_when_found(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    existing = MagicMock()
    existing.id = "222"
    client.crm.contacts.search_api.do_search.return_value.results = [existing]

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.upsert_contact("existing@example.com", name="Bob")

    assert result == "222"
    client.crm.contacts.basic_api.update.assert_called_once()
    client.crm.contacts.basic_api.create.assert_not_called()


# ---------------------------------------------------------------------------
# upsert_contact — API error → returns None, doesn't raise
# ---------------------------------------------------------------------------

@patch("hubspot_service._client")
def test_upsert_contact_handles_api_error(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.contacts.search_api.do_search.side_effect = Exception("API down")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.upsert_contact("error@example.com")

    assert result is None


# ---------------------------------------------------------------------------
# create_deal
# ---------------------------------------------------------------------------

@patch("hubspot_service._client")
def test_create_deal_returns_deal_id(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.deals.basic_api.create.return_value = _mock_deal("999")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.create_deal(
        contact_id="111", pipeline_id="pipeline1", stage_id="stage1", deal_name="Test Deal"
    )

    assert result == "999"


@patch("hubspot_service._client")
def test_create_deal_associates_contact(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.deals.basic_api.create.return_value = _mock_deal("999")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    hubspot_service.create_deal(
        contact_id="111", pipeline_id="p1", stage_id="s1", deal_name="Deal"
    )

    client.crm.associations.v4.basic_api.create.assert_called_once()
    kwargs = client.crm.associations.v4.basic_api.create.call_args
    assert kwargs[1].get("object_type") == "deals" or kwargs[0][0] == "deals"


@patch("hubspot_service._client")
def test_create_deal_no_contact_skips_association(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.deals.basic_api.create.return_value = _mock_deal("999")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    hubspot_service.create_deal(
        contact_id=None, pipeline_id="p1", stage_id="s1", deal_name="Deal"
    )

    client.crm.associations.v4.basic_api.create.assert_not_called()


@patch("hubspot_service._client")
def test_create_deal_handles_api_error(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.deals.basic_api.create.side_effect = Exception("API error")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.create_deal(
        contact_id="111", pipeline_id="p1", stage_id="s1", deal_name="Deal"
    )

    assert result is None


def test_create_deal_no_token():
    hubspot_service.HUBSPOT_ACCESS_TOKEN = ""
    result = hubspot_service.create_deal(
        contact_id="111", pipeline_id="p1", stage_id="s1", deal_name="Deal"
    )
    assert result is None


# ---------------------------------------------------------------------------
# add_note
# ---------------------------------------------------------------------------

@patch("hubspot_service._client")
def test_add_note_returns_note_id(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.objects.notes.basic_api.create.return_value = _mock_note("888")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.add_note("Test note body", deal_id="999", contact_id="111")

    assert result == "888"
    assert client.crm.associations.v4.basic_api.create.call_count == 2


@patch("hubspot_service._client")
def test_add_note_only_deal(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.objects.notes.basic_api.create.return_value = _mock_note("888")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    hubspot_service.add_note("Note", deal_id="999")

    assert client.crm.associations.v4.basic_api.create.call_count == 1


@patch("hubspot_service._client")
def test_add_note_handles_error(mock_client):
    client = MagicMock()
    mock_client.return_value = client
    client.crm.objects.notes.basic_api.create.side_effect = Exception("fail")

    hubspot_service.HUBSPOT_ACCESS_TOKEN = "test-token"
    result = hubspot_service.add_note("Note")

    assert result is None


# ---------------------------------------------------------------------------
# handle_demo_request
# ---------------------------------------------------------------------------

@patch("hubspot_service.create_deal")
@patch("hubspot_service.upsert_contact")
def test_handle_demo_request_calls_both(mock_upsert, mock_deal):
    mock_upsert.return_value = "contact-1"
    mock_deal.return_value = "deal-1"

    contact_id, deal_id = hubspot_service.handle_demo_request(
        email="demo@example.com",
        name="Jane Smith",
        company="Acme",
        phone="555-0100",
        notes="Interested in janitorial contracts",
    )

    assert contact_id == "contact-1"
    assert deal_id == "deal-1"
    mock_upsert.assert_called_once()
    mock_deal.assert_called_once()
    call_kwargs = mock_deal.call_args[1]
    assert call_kwargs["stage_id"] == hubspot_service.HUBSPOT_DEMO_STAGE_ID


@patch("hubspot_service.create_deal")
@patch("hubspot_service.upsert_contact")
def test_handle_demo_request_no_contact_still_creates_deal(mock_upsert, mock_deal):
    mock_upsert.return_value = None
    mock_deal.return_value = None

    contact_id, deal_id = hubspot_service.handle_demo_request(email="x@x.com")
    assert contact_id is None
    assert deal_id is None
    mock_deal.assert_called_once_with(
        contact_id=None,
        pipeline_id=hubspot_service.HUBSPOT_BETA_PIPELINE_ID,
        stage_id=hubspot_service.HUBSPOT_DEMO_STAGE_ID,
        deal_name=f"Demo Request – x@x.com",
    )


# ---------------------------------------------------------------------------
# handle_early_access_signup
# ---------------------------------------------------------------------------

@patch("hubspot_service.upsert_contact")
def test_handle_early_access_sets_lead_source(mock_upsert):
    mock_upsert.return_value = "contact-2"

    result = hubspot_service.handle_early_access_signup("early@example.com")

    assert result == "contact-2"
    call_kwargs = mock_upsert.call_args[1]
    assert "lead_source" in call_kwargs.get("extra_props", {})
    assert call_kwargs["extra_props"]["lead_source"] == hubspot_service.HUBSPOT_EARLY_ACCESS_LEAD_SOURCE


# ---------------------------------------------------------------------------
# handle_stripe_checkout
# ---------------------------------------------------------------------------

@patch("hubspot_service.add_note")
@patch("hubspot_service.create_deal")
@patch("hubspot_service.upsert_contact")
def test_handle_stripe_checkout_creates_contact_deal_note(mock_upsert, mock_deal, mock_note):
    mock_upsert.return_value = "contact-3"
    mock_deal.return_value = "deal-3"

    contact_id, deal_id = hubspot_service.handle_stripe_checkout(
        email="paying@example.com",
        name="Bob Jones",
        stripe_session_id="cs_test_abc",
    )

    assert contact_id == "contact-3"
    assert deal_id == "deal-3"
    call_kwargs = mock_deal.call_args[1]
    assert call_kwargs["stage_id"] == hubspot_service.HUBSPOT_PAYING_STAGE_ID
    mock_note.assert_called_once()
    note_body = mock_note.call_args[1]["body"]
    assert "Beta plan" in note_body
    assert "cs_test_abc" in note_body


@patch("hubspot_service.add_note")
@patch("hubspot_service.create_deal")
@patch("hubspot_service.upsert_contact")
def test_handle_stripe_checkout_no_hubspot_still_returns(mock_upsert, mock_deal, mock_note):
    mock_upsert.return_value = None
    mock_deal.return_value = None

    contact_id, deal_id = hubspot_service.handle_stripe_checkout(email="x@x.com")

    assert contact_id is None
    assert deal_id is None
    mock_note.assert_not_called()
