import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

HUBSPOT_ACCESS_TOKEN = os.getenv("HUBSPOT_ACCESS_TOKEN")
HUBSPOT_BETA_PIPELINE_ID = os.getenv("HUBSPOT_BETA_PIPELINE_ID", "default")
HUBSPOT_DEMO_STAGE_ID = os.getenv("HUBSPOT_DEMO_STAGE_ID", "appointmentscheduled")
HUBSPOT_PAYING_STAGE_ID = os.getenv("HUBSPOT_PAYING_STAGE_ID", "closedwon")
HUBSPOT_EARLY_ACCESS_LEAD_SOURCE = os.getenv("HUBSPOT_EARLY_ACCESS_LEAD_SOURCE", "Early Access")


def _client():
    from hubspot import HubSpot
    return HubSpot(access_token=HUBSPOT_ACCESS_TOKEN)


def _split_name(full_name: str) -> tuple[str, str]:
    parts = (full_name or "").strip().split(None, 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0] if parts else "", "")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def upsert_contact(
    email: str,
    name: str = "",
    company: str = "",
    phone: str = "",
    notes: str = "",
    extra_props: dict | None = None,
) -> str | None:
    """Create or update a HubSpot contact by email. Returns contact ID or None on error."""
    if not HUBSPOT_ACCESS_TOKEN:
        logger.warning("HUBSPOT_ACCESS_TOKEN not set; skipping HubSpot contact upsert")
        return None
    try:
        from hubspot.crm.contacts.models import (
            Filter,
            FilterGroup,
            PublicObjectSearchRequest,
            SimplePublicObjectInput,
            SimplePublicObjectInputForCreate,
        )

        firstname, lastname = _split_name(name)
        props: dict = {
            "email": email,
            "firstname": firstname,
            "lastname": lastname,
            "company": company,
            "phone": phone,
        }
        if notes:
            props["notes_last_contacted"] = notes
        if extra_props:
            props.update(extra_props)
        props = {k: v for k, v in props.items() if v}

        client = _client()
        search_req = PublicObjectSearchRequest(
            filter_groups=[FilterGroup(filters=[Filter(property_name="email", operator="EQ", value=email)])]
        )
        result = client.crm.contacts.search_api.do_search(search_req)

        if result.results:
            contact_id = result.results[0].id
            client.crm.contacts.basic_api.update(contact_id, SimplePublicObjectInput(properties=props))
            logger.info("Updated HubSpot contact %s", contact_id)
            return contact_id

        contact = client.crm.contacts.basic_api.create(
            SimplePublicObjectInputForCreate(properties=props)
        )
        logger.info("Created HubSpot contact %s", contact.id)
        return contact.id

    except Exception:
        logger.exception("HubSpot upsert_contact failed for %s", email)
        return None


def create_deal(
    contact_id: str | None,
    pipeline_id: str,
    stage_id: str,
    deal_name: str,
) -> str | None:
    """Create a HubSpot deal and associate it with a contact. Returns deal ID or None."""
    if not HUBSPOT_ACCESS_TOKEN:
        return None
    try:
        from hubspot.crm.associations.v4.models import AssociationSpec
        from hubspot.crm.deals.models import SimplePublicObjectInputForCreate as DealInput

        client = _client()
        deal = client.crm.deals.basic_api.create(
            DealInput(properties={
                "dealname": deal_name,
                "pipeline": pipeline_id,
                "dealstage": stage_id,
            })
        )
        deal_id = deal.id
        logger.info("Created HubSpot deal %s", deal_id)

        if contact_id:
            client.crm.associations.v4.basic_api.create(
                object_type="deals",
                object_id=deal_id,
                to_object_type="contacts",
                to_object_id=contact_id,
                association_spec=[AssociationSpec(
                    association_category="HUBSPOT_DEFINED",
                    association_type_id=3,
                )],
            )
            logger.info("Associated deal %s with contact %s", deal_id, contact_id)

        return deal_id

    except Exception:
        logger.exception("HubSpot create_deal failed (contact_id=%s)", contact_id)
        return None


def add_note(
    body: str,
    deal_id: str | None = None,
    contact_id: str | None = None,
) -> str | None:
    """Create a HubSpot note and associate it with a deal and/or contact."""
    if not HUBSPOT_ACCESS_TOKEN:
        return None
    try:
        from hubspot.crm.associations.v4.models import AssociationSpec
        from hubspot.crm.objects.notes.models import SimplePublicObjectInputForCreate as NoteInput

        client = _client()
        ts = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        note = client.crm.objects.notes.basic_api.create(
            NoteInput(properties={"hs_note_body": body, "hs_timestamp": ts})
        )
        note_id = note.id
        logger.info("Created HubSpot note %s", note_id)

        if deal_id:
            client.crm.associations.v4.basic_api.create(
                object_type="notes",
                object_id=note_id,
                to_object_type="deals",
                to_object_id=deal_id,
                association_spec=[AssociationSpec(
                    association_category="HUBSPOT_DEFINED",
                    association_type_id=214,
                )],
            )
        if contact_id:
            client.crm.associations.v4.basic_api.create(
                object_type="notes",
                object_id=note_id,
                to_object_type="contacts",
                to_object_id=contact_id,
                association_spec=[AssociationSpec(
                    association_category="HUBSPOT_DEFINED",
                    association_type_id=202,
                )],
            )
        return note_id

    except Exception:
        logger.exception("HubSpot add_note failed")
        return None


# ---------------------------------------------------------------------------
# High-level handlers (one per user-facing event)
# ---------------------------------------------------------------------------

def handle_demo_request(
    email: str,
    name: str = "",
    company: str = "",
    phone: str = "",
    notes: str = "",
) -> tuple[str | None, str | None]:
    """
    HubSpot flow for /demo form submission.
    Returns (contact_id, deal_id); either may be None if HubSpot is unavailable.
    """
    contact_id = upsert_contact(email, name=name, company=company, phone=phone, notes=notes)
    deal_id = create_deal(
        contact_id=contact_id,
        pipeline_id=HUBSPOT_BETA_PIPELINE_ID,
        stage_id=HUBSPOT_DEMO_STAGE_ID,
        deal_name=f"Demo Request – {company or email}",
    )
    return contact_id, deal_id


def handle_early_access_signup(email: str) -> str | None:
    """
    HubSpot flow for early access list signup.
    Returns contact_id or None if HubSpot is unavailable.
    """
    return upsert_contact(
        email,
        extra_props={"lead_source": HUBSPOT_EARLY_ACCESS_LEAD_SOURCE},
    )


def handle_stripe_checkout(
    email: str,
    name: str = "",
    stripe_session_id: str = "",
) -> tuple[str | None, str | None]:
    """
    HubSpot flow after a successful Stripe checkout.
    Returns (contact_id, deal_id); either may be None if HubSpot is unavailable.
    """
    contact_id = upsert_contact(email, name=name)
    deal_id = create_deal(
        contact_id=contact_id,
        pipeline_id=HUBSPOT_BETA_PIPELINE_ID,
        stage_id=HUBSPOT_PAYING_STAGE_ID,
        deal_name=f"Beta Subscription – {email}",
    )
    if deal_id or contact_id:
        note_body = "Customer subscribed to the Beta plan."
        if stripe_session_id:
            note_body += f" Stripe session: {stripe_session_id}"
        add_note(body=note_body, deal_id=deal_id, contact_id=contact_id)
    return contact_id, deal_id
