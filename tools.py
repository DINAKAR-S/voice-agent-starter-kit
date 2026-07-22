"""Function tools Maya calls during a call.

Design note: the actual data-access logic lives in plain module-level helpers
(`_load`, `_search`, `_get`). The `@function_tool` methods on `AppointmentTools`
are thin wrappers around them. That split keeps the tools importable, keeps the
LLM-facing schema clean, and -- most usefully -- lets the __main__ self-check
exercise the filtering logic WITHOUT spinning up a LiveKit session.

Property data is read from data/properties.json on every call so the sheet can
be edited without redeploying. It is NEVER stuffed into the system prompt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from livekit.agents import RunContext, function_tool

from config import DEFAULT_TRANSFER_NUMBER

log = logging.getLogger("voice-agent.tools")

DATA_PATH = Path(__file__).parent / "data" / "properties.json"


# --- plain logic (testable, no LiveKit needed) -------------------------------
def _load() -> list[dict]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _compact(p: dict) -> dict:
    """Trim a listing to the fields Maya needs to speak -- fewer tokens."""
    return {
        "id": p["id"],
        "title": p["title"],
        "bhk": p["bhk"],
        "price_inr": p["price_inr"],
        "area": p["area"],
        "city": p["city"],
        "status": p["status"],
    }


def _search(
    bhk: Optional[int] = None,
    max_budget: Optional[int] = None,
    area: Optional[str] = None,
) -> list[dict]:
    """Filter listings. Any argument left as None is ignored."""
    results = []
    for p in _load():
        if bhk is not None and p.get("bhk") != bhk:
            continue
        if max_budget is not None and p.get("price_inr", 0) > max_budget:
            continue
        if area:
            haystack = f"{p.get('area', '')} {p.get('city', '')}".lower()
            if area.lower() not in haystack:
                continue
        results.append(_compact(p))
    return results


def _get(property_id: str) -> Optional[dict]:
    for p in _load():
        if p["id"].lower() == property_id.lower():
            return p
    return None


# --- function tools (what the LLM can call) ----------------------------------
class AppointmentTools:
    """Bundle of Maya's tools. Pass `AppointmentTools().to_tools()` to the
    AgentSession(tools=...) so every language agent shares the same tools."""

    def to_tools(self) -> list:
        """Return the bound function tools for AgentSession/Agent `tools=`."""
        return [
            self.search_properties,
            self.get_property_details,
            self.book_site_visit,
            self.transfer_to_human,
        ]

    @function_tool
    async def search_properties(
        self,
        context: RunContext,
        bhk: Optional[int] = None,
        max_budget: Optional[int] = None,
        area: Optional[str] = None,
    ) -> str:
        """Search Acme Realty listings. Use before quoting any property.

        Args:
            bhk: number of bedrooms (2 or 3). Use 0 for a plot. Omit for any.
            max_budget: maximum price in INR (e.g. 5000000). Omit for any.
            area: locality or city to match (e.g. "Whitefield"). Omit for any.
        """
        matches = _search(bhk=bhk, max_budget=max_budget, area=area)
        log.info("search_properties bhk=%s budget=%s area=%s -> %d hits",
                 bhk, max_budget, area, len(matches))
        if not matches:
            return "No matching properties found. Suggest relaxing budget or area."
        return json.dumps(matches, ensure_ascii=False)

    @function_tool
    async def get_property_details(self, context: RunContext, property_id: str) -> str:
        """Get full details (amenities, exact price, status) for one listing.

        Args:
            property_id: the listing id, e.g. "AC-201".
        """
        prop = _get(property_id)
        if prop is None:
            return f"No property with id {property_id}. Use search_properties first."
        return json.dumps(prop, ensure_ascii=False)

    @function_tool
    async def book_site_visit(
        self,
        context: RunContext,
        name: str,
        phone: str,
        property_id: str,
        date: str,
        time: str,
    ) -> dict:
        """Book a site visit once you have the caller's name, phone, the property
        id, and a date + time they confirmed.

        Args:
            name: caller's name.
            phone: caller's phone number.
            property_id: the listing id to visit, e.g. "AC-201".
            date: visit date, e.g. "2026-07-25".
            time: visit time, e.g. "11:00 AM".
        """
        # In production this posts the booking to n8n (which upserts Supabase and
        # DMs the owner on Telegram). Here we just log it and echo a confirmation
        # so the demo runs with zero external services.
        # TODO: POST to f"{N8N_BASE_URL}/webhook/voice-events" with the booking.
        confirmation = {
            "status": "booked",
            "name": name,
            "phone": phone,
            "property_id": property_id,
            "date": date,
            "time": time,
        }
        log.info("book_site_visit -> %s", confirmation)
        return confirmation

    @function_tool
    async def transfer_to_human(self, context: RunContext) -> dict:
        """Transfer the caller to a human agent when they ask for a person or
        the request is out of scope."""
        # Returns the transfer intent. The telephony layer performs the actual
        # SIP REFER to DEFAULT_TRANSFER_NUMBER.
        # TODO: perform the SIP transfer, e.g. via ctx.api.sip.transfer_sip_participant(...).
        log.info("transfer_to_human -> %s", DEFAULT_TRANSFER_NUMBER)
        return {"action": "transfer", "to": DEFAULT_TRANSFER_NUMBER}


if __name__ == "__main__":
    # Self-check: prove the filtering logic is correct against the sample JSON.
    all_props = _load()
    assert len(all_props) >= 6, f"expected >=6 listings, got {len(all_props)}"

    two_bhk = _search(bhk=2)
    assert two_bhk and all(p["bhk"] == 2 for p in two_bhk), "bhk filter broken"

    cheap = _search(max_budget=5_000_000)
    assert cheap and all(p["price_inr"] <= 5_000_000 for p in cheap), "budget filter broken"

    whitefield = _search(area="Whitefield")
    assert whitefield and all(
        "whitefield" in f"{p['area']} {p['city']}".lower() for p in whitefield
    ), "area filter broken"

    combined = _search(bhk=2, max_budget=5_000_000, area="Whitefield")
    assert all(
        p["bhk"] == 2 and p["price_inr"] <= 5_000_000 for p in combined
    ), "combined filter broken"

    assert _get("AC-201") is not None, "get_property_details lookup broken"
    assert _get("nope") is None, "unknown id should return None"

    print(f"tools.py self-check passed: {len(all_props)} listings, "
          f"{len(two_bhk)} 2BHK, {len(whitefield)} in Whitefield")
