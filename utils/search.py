"""
Internet search utilities for the Full Internet Analyst.
Supports Perplexity Sonar API (primary) with DuckDuckGo fallback.

Search functions return raw web findings. The conversational LLM layer
(which maintains chat history) lives in the page, not here.
"""

from datetime import date

from openai import OpenAI
from settings import USE_PERPLEXITY, PERPLEXITY_API_KEY

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
PERPLEXITY_MODEL = "sonar"


def search_perplexity(query: str) -> dict:
    """
    Search using Perplexity's Sonar API (OpenAI-compatible).
    Returns a dict with 'answer' (str) and 'citations' (list of URLs).
    """
    client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url=PERPLEXITY_BASE_URL)

    response = client.chat.completions.create(
        model=PERPLEXITY_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a football research assistant. Search the web for current, "
                    "factual information about the player or topic mentioned. "
                    "Return factual findings with statistics and data points. "
                    "Do not provide opinions or analysis."
                ),
            },
            {"role": "user", "content": query},
        ],
    )

    answer = response.choices[0].message.content
    citations = getattr(response, "citations", []) or []

    return {"answer": answer, "citations": citations}


def search_duckduckgo(query: str, max_results: int = 10) -> dict:
    """
    Search using DuckDuckGo (free, no API key needed).
    Appends 'football soccer stats' to the query to keep results on-topic.
    Returns a dict with 'answer' (str) and 'citations' (list of URLs).
    """
    from ddgs import DDGS

    # Append football context to disambiguate player names (e.g. "Jude" → Bible)
    football_query = f"{query} football soccer player stats {date.today().year}"

    results = []
    with DDGS() as ddgs:
        for result in ddgs.text(football_query, max_results=max_results):
            results.append(result)

    if not results:
        return {"answer": "No results found.", "citations": []}

    snippets = []
    citations = []
    for r in results:
        title = r.get("title", "")
        body = r.get("body", "")
        href = r.get("href", "")
        snippets.append(f"{title}: {body}")
        if href:
            citations.append(href)

    answer = "\n\n".join(snippets)
    return {"answer": answer, "citations": citations}


def search_internet(query: str) -> dict:
    """
    Search the internet using the best available provider.
    Uses Perplexity if USE_PERPLEXITY is true, otherwise falls back to DuckDuckGo.
    Returns a dict with 'answer' (str), 'citations' (list), and 'provider' (str).
    """
    if USE_PERPLEXITY and PERPLEXITY_API_KEY:
        result = search_perplexity(query)
        result["provider"] = "Perplexity"
    else:
        result = search_duckduckgo(query)
        result["provider"] = "DuckDuckGo"

    return result
