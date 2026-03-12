"""
Full Internet Analyst page.
Searches the internet for information about a football player claim/question,
then uses the configured LLM to answer within a conversational context.

Architecture:
  - Perplexity / DuckDuckGo → web search (retrieval only)
  - Configured LLM (OpenAI / Azure / Gemini / LM Studio) → conversational answer
"""

import re
from datetime import date

import streamlit as st
from openai import OpenAI

from utils.page_components import add_common_page_elements
from utils.search import search_internet

from settings import USE_GEMINI, USE_OPENAI, USE_LM_STUDIO

if USE_GEMINI:
    from settings import GEMINI_API_KEY, GEMINI_CHAT_MODEL
elif USE_OPENAI:
    from settings import OPENAI_API_KEY, OPENAI_CHAT_MODEL
elif USE_LM_STUDIO:
    from settings import LM_STUDIO_API_KEY, LM_STUDIO_CHAT_MODEL, LM_STUDIO_API_BASE
else:
    from settings import GPT_BASE, GPT_KEY, GPT_CHAT_MODEL

sidebar_container = add_common_page_elements()
page_container = st.sidebar.container()
sidebar_container = st.sidebar.container()

st.divider()

st.header("Full Internet Analyst")
st.write(
    "Enter a query about a football player. "
    "The tool will search the internet for relevant information and answer based on its findings."
)

_TODAY = date.today().isoformat()
# European football season runs ~August to June.
# Before August → still in the previous season (e.g. March 2026 → 2025/26)
# From August onward → new season has started (e.g. September 2026 → 2026/27)
_YEAR = date.today().year
_SEASON = f"{_YEAR - 1}/{str(_YEAR)[2:]}" if date.today().month < 8 else f"{_YEAR}/{str(_YEAR + 1)[2:]}"

SYSTEM_PROMPT = (
    f"You are a football analyst. Today's date is {_TODAY}. "
    "You answer questions about football players based ONLY on the web search results "
    "provided to you — do not rely on your own knowledge for factual claims. "
    "Each user message includes search results gathered from the internet — use them "
    "as your primary source of truth. Cite specific statistics and facts from the "
    "search results. If the search results contradict your expectations, trust the "
    "search results. If they don't contain enough information to answer, say so clearly "
    "rather than guessing. "
    "Maintain context from the conversation history so follow-up questions work naturally."
)

QUERY_REWRITE_PROMPT = (
    f"You are a search query rewriter. Today's date is {_TODAY}. "
    f"The current European football season is {_SEASON}. "
    "Given a conversation history and a follow-up question, rewrite the follow-up "
    "into a standalone search query that a search engine can understand without any "
    "prior context. Include the full player name, their CURRENT team, the correct "
    "season, and any relevant details. Do not assume a player changed teams recently "
    "— use the team mentioned or implied in the conversation. "
    "Return ONLY the rewritten search query, nothing else."
)


# ---------------------------------------------------------------------------
# LLM call — reuses the same provider-switching pattern as the rest of the app
# ---------------------------------------------------------------------------
def _call_llm(messages: list) -> str:
    """Send messages to the configured LLM and return the response text."""
    if USE_GEMINI:
        import google.generativeai as genai
        from utils.gemini import convert_messages_format

        genai.configure(api_key=GEMINI_API_KEY)
        converted = convert_messages_format(messages)
        model = genai.GenerativeModel(
            model_name=GEMINI_CHAT_MODEL,
            system_instruction=converted["system_instruction"],
        )
        chat = model.start_chat(history=converted["history"])
        response = chat.send_message(content=converted["content"])
        return response.text
    elif USE_OPENAI:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content
    elif USE_LM_STUDIO:
        client = OpenAI(api_key=LM_STUDIO_API_KEY, base_url=LM_STUDIO_API_BASE)
        response = client.chat.completions.create(
            model=LM_STUDIO_CHAT_MODEL,
            messages=messages,
            temperature=0.7,
        )
        return response.choices[0].message.content
    else:
        client = OpenAI(api_key=GPT_KEY, base_url=GPT_BASE)
        response = client.responses.create(
            model=GPT_CHAT_MODEL,
            input=messages,
        )
        return response.output_text


# ---------------------------------------------------------------------------
# Citation helpers
# ---------------------------------------------------------------------------
def _linkify_citations(text: str, citations: list) -> str:
    """Replace [1], [2] markers with clickable markdown links."""
    if not citations:
        return text

    def _replace_ref(match):
        idx = int(match.group(1))
        if 1 <= idx <= len(citations):
            url = citations[idx - 1]
            return f" [[{idx}]]({url})"
        return match.group(0)

    return re.sub(r"\[(\d+)\]", _replace_ref, text)


def _rewrite_query(query: str, conversation_history: list) -> str:
    """
    Use the LLM to rewrite a follow-up question into a standalone search query.
    e.g. "Is he better than last season?" → "Jude Bellingham Real Madrid 2025/26 vs 2024/25 season comparison stats"
    Only rewrites if there is prior conversation context; otherwise returns the query as-is.
    """
    if not conversation_history:
        return query

    # Build a compact summary of the conversation for the rewriter
    messages = [{"role": "system", "content": QUERY_REWRITE_PROMPT}]

    # Include just the user questions and a brief of assistant answers for context
    for msg in conversation_history:
        if msg["role"] == "user":
            messages.append({"role": "user", "content": msg["content"]})
        elif msg["role"] == "assistant":
            # Truncate assistant responses to keep the rewrite call cheap
            truncated = msg["content"][:500]
            messages.append({"role": "assistant", "content": truncated})

    # Explicitly remind the rewriter of the conversation subject to avoid
    # ambiguity (e.g. "Xabi Alonso" defaults to Leverkusen without Real Madrid context)
    first_user_q = next(
        (m["content"] for m in conversation_history if m["role"] == "user"), ""
    )
    first_assistant_a = next(
        (m["content"][:300] for m in conversation_history if m["role"] == "assistant"), ""
    )
    context_hint = (
        f"Conversation context — the original question was: \"{first_user_q}\". "
        f"The answer established: \"{first_assistant_a}...\"\n\n"
        f"Now rewrite this follow-up as a standalone search query: {query}"
    )
    messages.append({"role": "user", "content": context_hint})

    try:
        return _call_llm(messages).strip().strip('"')
    except Exception:
        return query


def _render_assistant_message(message: dict):
    """Render an assistant message with linked citations and a source list."""
    answer = message["content"]
    citations = message.get("citations", [])
    provider = message.get("provider", "")

    formatted = _linkify_citations(answer, citations)
    st.markdown(formatted)

    if citations:
        st.divider()
        st.caption(f"Sources ({provider})")
        for i, url in enumerate(citations, 1):
            domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
            st.markdown(
                f"<small>{i}. <a href='{url}' target='_blank'>{domain}</a></small>",
                unsafe_allow_html=True,
            )
    elif provider:
        st.caption(f"Search provider: {provider}")


# ---------------------------------------------------------------------------
# Session state and main logic
# ---------------------------------------------------------------------------
if "analyst_messages" not in st.session_state:
    st.session_state.analyst_messages = []       # display messages (with citations metadata)
    st.session_state.analyst_llm_history = []    # plain role/content for LLM context

query = st.chat_input(
    placeholder="e.g. Is Jude Bellingham performing well at Real Madrid this season?"
)

if query:
    # 1. Add user message to display
    st.session_state.analyst_messages.append({"role": "user", "content": query})

    # 2. Rewrite follow-up queries into standalone search queries
    #    Use analyst_messages (clean questions + answers) not analyst_llm_history
    #    (which has search results embedded in user messages and confuses the rewriter)
    search_query = _rewrite_query(query, st.session_state.analyst_messages)

    # 3. Search the internet for context
    with st.spinner("Searching the internet..."):
        try:
            search_result = search_internet(search_query)
        except Exception as e:
            st.error(f"Search failed: {e}")
            search_result = None

    if search_result:
        # 4. Build LLM messages: system + conversation history + new query with search context
        llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        llm_messages += st.session_state.analyst_llm_history

        user_msg_with_context = (
            f"User question: {query}\n\n"
            f"--- Web search results ({search_result['provider']}) ---\n"
            f"{search_result['answer']}"
        )
        llm_messages.append({"role": "user", "content": user_msg_with_context})

        # 5. Call the LLM for a conversational answer
        with st.spinner("Analyzing findings..."):
            try:
                llm_answer = _call_llm(llm_messages)
            except Exception as e:
                st.error(f"LLM call failed: {e}")
                llm_answer = None

        if llm_answer:
            # 6. Update LLM conversation history (carries context for follow-ups)
            st.session_state.analyst_llm_history.append(
                {"role": "user", "content": user_msg_with_context}
            )
            st.session_state.analyst_llm_history.append(
                {"role": "assistant", "content": llm_answer}
            )

            # 7. Add to display messages (with citation metadata for rendering)
            st.session_state.analyst_messages.append(
                {
                    "role": "assistant",
                    "content": llm_answer,
                    "citations": search_result["citations"],
                    "provider": search_result["provider"],
                }
            )

# Display conversation history
for message in st.session_state.analyst_messages:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.write(message["content"])
    else:
        with st.chat_message(
            "assistant", avatar="data/ressources/img/twelve_chat_logo.svg"
        ):
            _render_assistant_message(message)
