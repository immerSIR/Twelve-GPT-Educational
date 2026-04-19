"""Twelve Earpiece API client for football data analysis."""

import requests

from settings import TWELVE_EARPIECE_API_KEY

_EARPIECE_URL = "https://earpiece-gateway-api.twelve.football/query"
_TIMEOUT = 60


def query_earpiece(
    query: str,
    conversation_id: int | None = None,
    chat_id: int | None = None,
) -> dict:
    """Query the Twelve Earpiece API and return its response.

    Parameters
    ----------
    query : str
        The natural-language football question.
    conversation_id : int | None
        Re-use an existing conversation for context continuity.
    chat_id : int | None
        Re-use an existing chat within a conversation.

    Returns
    -------
    dict
        On success: ``{"response": str, "conversation_id": int, "chat_id": int}``
        On failure: ``{"error": str}``
    """
    params: dict = {"query": query}
    if conversation_id is not None:
        params["conversation_id"] = conversation_id
    if chat_id is not None:
        params["chat_id"] = chat_id

    try:
        resp = requests.post(
            _EARPIECE_URL,
            params=params,
            headers={
                "accept": "application/json",
                "Authorization": f"Bearer {TWELVE_EARPIECE_API_KEY}",
            },
            data="",
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "response": data.get("response", ""),
            "conversation_id": data.get("conversation_id"),
            "chat_id": data.get("chat_id"),
        }
    except requests.Timeout:
        return {"error": "Earpiece API timed out"}
    except requests.HTTPError as exc:
        return {"error": f"Earpiece API HTTP {exc.response.status_code}"}
    except Exception as exc:
        return {"error": f"Earpiece API error: {exc}"}


def format_earpiece_for_context(earpiece_response: dict) -> str:
    """Format an Earpiece response as a labelled context block for the LLM prompt."""
    if "error" in earpiece_response:
        return ""
    text = earpiece_response.get("response", "")
    if not text:
        return ""
    # Truncate to keep token budget manageable
    if len(text) > 3000:
        text = text[:3000] + "..."
    return f"--- Twelve data analysis (from Earpiece API) ---\n{text}"
