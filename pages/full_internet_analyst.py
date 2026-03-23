"""
Full Internet Analyst
Searches trusted football journalism sources and synthesises narrative commentary.
Auto-detects query type (match / player / injury / team / transfer) and formats output.
Follows the standard worldisation pattern:
  add_common_page_elements → create_chat → empty-state init
  → get_input → display_messages → save_state.
"""

import json
import re
from datetime import date

import streamlit as st
from openai import OpenAI

from classes.chat import Chat
from utils.page_components import add_common_page_elements
from utils.search import (
    TRUSTED_DOMAINS,
    build_match_context_from_plan,
    build_match_report_refusal,
    build_recent_match_retry_query,
    match_report_can_answer,
    normalise_query_plan,
    search_multi,
    should_retry_match_report,
)
from utils.utils import create_chat

from settings import USE_GEMINI, USE_OPENAI, USE_LM_STUDIO

if USE_GEMINI:
    from settings import GEMINI_API_KEY, GEMINI_CHAT_MODEL
elif USE_OPENAI:
    from settings import OPENAI_API_KEY, OPENAI_CHAT_MODEL
elif USE_LM_STUDIO:
    from settings import LM_STUDIO_API_KEY, LM_STUDIO_CHAT_MODEL, LM_STUDIO_API_BASE
else:
    from settings import GPT_BASE, GPT_KEY, GPT_CHAT_MODEL

# ---------------------------------------------------------------------------
# Date / season helpers
# ---------------------------------------------------------------------------
_TODAY = date.today().isoformat()
_YEAR = date.today().year
_SEASON = (
    f"{_YEAR - 1}/{str(_YEAR)[2:]}"
    if date.today().month < 8
    else f"{_YEAR}/{str(_YEAR + 1)[2:]}"
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def _system_prompt(answer_language: str = "en") -> str:
    return f"""You are an expert football analyst synthesising coverage from trusted journalism sources.
Today's date is {_TODAY}. Current European football season: {_SEASON}.

ANSWER ONLY from the web search results provided. Do not use your own knowledge
for factual claims about matches, players, form, or transfers.

Write the final answer entirely in `{answer_language}`. If the supporting sources are in another
language, summarise and translate their meaning into `{answer_language}` without inventing facts.

AUTO-DETECT the query type and format your response accordingly:

MATCH_REPORT: Describe how the game was played and how the match was judged.
Structure: context -> first-half narrative -> turning point -> second half ->
how journalists/local reports rated the performance of each side ->
whether the result felt deserved -> **Bottom line:** [one bold sentence verdict]

PLAYER_PERFORMANCE: Describe the player's performance narrative.
Structure: how they started -> key moments -> decisive contribution ->
overall assessment -> **Bottom line:**
Length: 1-2 focused paragraphs.

INJURY: Concise factual report.
Structure: what happened -> severity -> expected return -> impact on team -> **Bottom line:**
Length: 3-5 sentences maximum.

TEAM_FORM: Describe the team's recent trajectory as a story.
Structure: recent run framed narratively -> tactical patterns noted by journalists ->
key contributors -> outlook -> **Bottom line:**
Length: 2-3 paragraphs.

TRANSFER: Report the situation from journalism.
Structure: current reported situation -> confirmed vs speculated ->
source credibility notes -> timeline -> **Bottom line:**

RULES:
- Write in flowing paragraphs, not bullets or tables
- Lead with the narrative, not the scoreline
- Cite sources inline: [1], [2], "According to A Bola [1]..."
- If the verified facts block says the score is not verified, do not state a scoreline
- When the user asks about a recent match, use the exact absolute date from the verified facts block
- If two sources disagree, present both views
- For match reports, include the main feedback/opinion from the reports, not just the chronology
- Focus on verdicts about control, quality, deservedness, strengths, weaknesses, and standout issues
- Do not pad the answer with commentator names unless their actual verdict matters
- If results lack narrative depth, say so explicitly
- If coverage is very recent or partial, flag that
- Never fabricate. If the provided search context does not support a claim, do not make it."""


PLANNER_PROMPT = f"""You are a football query planner for a multilingual web-search system.
Today's date is {_TODAY}. Current European football season: {_SEASON}.

Given a user question and recent conversation history, return ONLY valid JSON with:
- "query_type": one of "match_report" | "player_performance" | "injury" | "team_form" | "transfer"
- "user_language": ISO 639-1 language code inferred from the user's wording
- "answer_language": ISO 639-1 language code; default to the user's language
- "absolute_date": exact ISO date if the user references a specific fixture date, otherwise null
- "entities": list of objects like {{"name": "...", "type": "club"|"team"|"player"|"national_team"}}
- "competition_country": country inferred from the fixture/league if possible, otherwise null
- "search_locales": locale chain in priority order using BCP47-style tags like "pt-PT", "pl-PL", "ar-EG", "en"
- "entity_aliases": object mapping each canonical entity name to a list of aliases, local spellings, or native-script variants
- "search_query_batches": list of objects with:
  - "locale": locale tag
  - "queries": list of 1-3 search queries written in that locale's language

PLANNING RULES:
- Domestic club or league question: primary search locale should be the competition/team country language
- National-team question: primary search locale should be that country's language
- If country is unclear: use the user's language first
- Always include English as the final fallback locale
- For match_report on a specific recent fixture: use the exact absolute date and include both team orders when useful
- Never use manager names in recent match queries
- Queries should target match reports, post-match reaction, verdicts, player ratings, criticism, or tactical analysis
- Keep the answer language aligned to the user's language even if search locales differ

Return JSON only. Example:
{{"query_type":"match_report","user_language":"pt","answer_language":"pt","absolute_date":"2026-03-22","entities":[{{"name":"FC Porto","type":"club"}},{{"name":"SC Braga","type":"club"}}],"competition_country":"Portugal","search_locales":["pt-PT","en"],"entity_aliases":{{"FC Porto":["Porto"],"SC Braga":["Braga","Sporting Braga"]}},"search_query_batches":[{{"locale":"pt-PT","queries":["FC Porto vs SC Braga 22 março 2026 crónica análise tática","SC Braga vs FC Porto 22 março 2026 reações opinião notas ao jogo","FC Porto SC Braga 22 março 2026 análise pós-jogo desempenho"]}},{{"locale":"en","queries":["FC Porto vs SC Braga March 22 2026 match report tactical analysis","SC Braga vs FC Porto March 22 2026 post-match reaction verdict player ratings"]}}]}}"""

EVALUATION_PROMPT = """You are a quality assessor for a football journalism chatbot.
Given a user question, the analyst's answer, and the raw search results available,
score on exactly three dimensions (1-5 each):

NARRATIVE_DEPTH (1-5): Is the answer journalistic prose with tactical/narrative content?
5 = reads like a quality newspaper match report
3 = mix of narrative and raw facts
1 = just lists scores, goalscorers, and raw stats — no narrative

SOURCE_GROUNDING (1-5): Are all factual claims supported by the search results?
5 = every claim directly traceable to the sources
1 = major claims not in the search results (potential hallucination)

SOURCE_DIVERSITY (1-5): Are multiple distinct outlets cited?
5 = three or more different outlets cited
3 = two outlets
1 = single source or no citations

Return ONLY valid JSON:
{"narrative_depth": <int>, "source_grounding": <int>, "source_diversity": <int>}"""


# ---------------------------------------------------------------------------
# LLM call — provider switching matching the rest of the app
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
# Helper functions
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


def _fallback_query_plan(query: str) -> dict:
    return normalise_query_plan(
        {
            "query_type": "match_report",
            "user_language": "en",
            "answer_language": "en",
            "entities": [],
            "competition_country": None,
            "search_locales": ["en"],
            "entity_aliases": {},
            "search_query_batches": [
                {"locale": "en", "queries": [f"{query} football match reaction opinion analysis"]}
            ],
        },
        query,
    )


def _plan_query(query: str, history: list) -> dict:
    """Use the LLM to build a multilingual search plan, then normalise it."""
    messages = [{"role": "system", "content": PLANNER_PROMPT}]
    for msg in history[-6:]:
        if isinstance(msg.get("content"), str):
            messages.append({"role": msg["role"], "content": msg["content"][:300]})
    messages.append(
        {"role": "user", "content": f"Plan multilingual search retrieval for: {query}"}
    )
    try:
        raw = _call_llm(messages)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return normalise_query_plan(json.loads(raw), query)
    except Exception:
        return _fallback_query_plan(query)


def _evaluate_answer(question: str, answer: str, search_context: str) -> dict | None:
    """Score the answer quality on narrative depth, source grounding, diversity."""
    messages = [
        {"role": "system", "content": EVALUATION_PROMPT},
        {
            "role": "user",
            "content": (
                f"User question: {question}\n\n"
                f"Analyst answer:\n{answer}\n\n"
                f"Raw search results available:\n{search_context[:2000]}"
            ),
        },
    ]
    try:
        raw = _call_llm(messages)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        scores = json.loads(raw)
        assert all(k in scores for k in ("narrative_depth", "source_grounding", "source_diversity"))
        return scores
    except Exception:
        return None


def _render_citations(citations: list, provider: str):
    """Render a numbered source list below an assistant message."""
    st.divider()
    st.caption(f"Sources ({provider})")
    for i, url in enumerate(citations, 1):
        domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
        st.markdown(
            f"<small>{i}. <a href='{url}' target='_blank'>{domain}</a></small>",
            unsafe_allow_html=True,
        )


def _render_search_expander(search_query_batches: list):
    """Show the locale-aware query plan sent to the search layer."""
    with st.expander("Search plan used"):
        for batch in search_query_batches:
            locale = batch.get("locale", "unknown")
            source_tier = batch.get("source_tier", "unknown")
            st.caption(f"{locale} [{source_tier}]")
            for i, query in enumerate(batch.get("queries", []), 1):
                st.markdown(f"- {i}. {query}")


def _render_evaluation(scores: dict):
    """Render the quality score expander."""
    with st.expander("Answer quality"):
        for label, key in [
            ("Narrative depth", "narrative_depth"),
            ("Source grounding", "source_grounding"),
            ("Source diversity", "source_diversity"),
        ]:
            v = scores[key]
            st.caption(f"{label}: {'⭐' * v}{'☆' * (5 - v)}  ({v}/5)")
        if any(scores[k] <= 2 for k in scores):
            st.warning(
                "Low quality score — this answer may lack narrative depth or source coverage."
            )


def _localize_refusal_message(message: str, answer_language: str) -> str:
    language = (answer_language or "en").split("-")[0].lower()
    if language == "en":
        return message

    messages = [
        {
            "role": "system",
            "content": (
                f"Translate the following refusal message into {language}. Preserve meaning exactly. "
                "Do not add any facts, explanations, or apologies. Return only the translated message."
            ),
        },
        {"role": "user", "content": message},
    ]
    try:
        return _call_llm(messages).strip()
    except Exception:
        return message


def _format_verified_match_facts(verified_match: dict | None) -> str:
    if not verified_match:
        return "No structured match verification was available."

    verified_score = verified_match.get("verified_score") or "not verified"
    lines = [
        f"Teams: {verified_match.get('team_a', 'Unknown')} and {verified_match.get('team_b', 'Unknown')}",
        f"Requested date: {verified_match.get('requested_date_display', 'not resolved')}",
        f"Match identity verified: {'yes' if verified_match.get('match_identity_verified') else 'no'}",
        f"Score verified: {verified_score}",
        f"Narrative coverage available: {'yes' if verified_match.get('narrative_coverage_available') else 'no'}",
        f"Searched locales: {', '.join(verified_match.get('searched_locales', [])) or 'not recorded'}",
        f"Winning locale: {verified_match.get('winning_locale') or 'not selected'}",
        f"Source tier: {verified_match.get('source_tier') or 'not selected'}",
        f"Verified source language: {verified_match.get('verified_source_language') or 'not verified'}",
        "If the score is not verified above, do not state a scoreline.",
    ]
    return "\n".join(f"- {line}" for line in lines)


def _render_verification(verified_match: dict, locale_attempts: list | None = None, answer_language: str = "en"):
    with st.expander("Verification details"):
        st.caption(f"Answer language: {answer_language}")
        st.caption(
            f"Teams: {verified_match.get('team_a', 'Unknown')} and {verified_match.get('team_b', 'Unknown')}"
        )
        st.caption(
            f"Requested date: {verified_match.get('requested_date_display', 'not resolved')}"
        )
        st.caption(
            f"Match identity verified: {'yes' if verified_match.get('match_identity_verified') else 'no'}"
        )
        st.caption(
            f"Score verified: {verified_match.get('verified_score') or 'not verified'}"
        )
        st.caption(
            f"Narrative coverage available: {'yes' if verified_match.get('narrative_coverage_available') else 'no'}"
        )
        st.caption(
            f"Searched locales: {', '.join(verified_match.get('searched_locales', [])) or 'not recorded'}"
        )
        st.caption(f"Winning locale: {verified_match.get('winning_locale') or 'not selected'}")
        st.caption(f"Source tier: {verified_match.get('source_tier') or 'not selected'}")
        st.caption(
            f"Verified source language: {verified_match.get('verified_source_language') or 'not verified'}"
        )

        if locale_attempts:
            st.caption("Locale attempts")
            for attempt in locale_attempts:
                st.markdown(
                    "- "
                    f"`{attempt.get('locale', 'unknown')}` "
                    f"[{attempt.get('source_tier', 'unknown')}] "
                    f"hits={attempt.get('raw_hit_count', 0)} "
                    f"accepted={attempt.get('accepted_hit_count', 0)} "
                    f"identity={'yes' if attempt.get('match_identity_verified') else 'no'} "
                    f"narrative={'yes' if attempt.get('narrative_coverage_available') else 'no'}"
                )

        accepted_hits = verified_match.get("accepted_hits", [])
        rejected_hits = verified_match.get("rejected_hits", [])
        if accepted_hits:
            st.caption("Accepted hits")
            for hit in accepted_hits[:6]:
                domain = hit.get("domain") or "unknown"
                st.markdown(
                    f"- `{domain}`: {hit.get('title', 'Untitled result')}"
                )
        if rejected_hits:
            st.caption("Rejected hits")
            for hit in rejected_hits[:6]:
                st.markdown(
                    f"- `{hit.get('reason', 'rejected')}`: {hit.get('title', 'Untitled result')}"
                )


# ===========================================================================
# InternetAnalystChat — Chat subclass following the worldisation pattern
# ===========================================================================
class InternetAnalystChat(Chat):
    def __init__(self, chat_state_hash, state="empty"):
        super().__init__(chat_state_hash, state=state)

    def instruction_messages(self) -> list:
        answer_language = st.session_state.get("fia_answer_language", "en")
        return [{"role": "system", "content": _system_prompt(answer_language)}]

    def get_relevant_info(self, query: str) -> str:
        """Classify, search, and return combined results as context string."""
        query_plan = _plan_query(query, self.messages_to_display)
        query_type = query_plan["query_type"]
        search_batches = query_plan["search_query_batches"]
        match_context = build_match_context_from_plan(query_plan, fallback_query=query)

        st.session_state.fia_answer_language = query_plan.get("answer_language", "en")

        with st.spinner(f"Searching {len(search_batches)} locale source set(s)..."):
            result = search_multi(search_batches, match_context=match_context)

        verified_match = result.get("verified_match")
        if query_type == "match_report" and should_retry_match_report(verified_match):
            retry_query = build_recent_match_retry_query(verified_match or match_context)
            if retry_query:
                with st.spinner("Verification failed — searching again with an exact-date query..."):
                    retry_batches = [
                        {
                            "locale": batch.get("locale", "en"),
                            "queries": [retry_query],
                            "source_tier": batch.get("source_tier"),
                        }
                        for batch in search_batches
                    ]
                    retry_result = search_multi(retry_batches, match_context=match_context)
                search_batches = [
                    {
                        **batch,
                        "queries": [*batch.get("queries", []), retry_query],
                    }
                    for batch in search_batches
                ]
                retry_verified = retry_result.get("verified_match")
                if retry_verified and len(retry_verified.get("accepted_hits", [])) > len(
                    (verified_match or {}).get("accepted_hits", [])
                ):
                    result = retry_result
                    verified_match = retry_verified

        # Stash metadata — handle_input() reads these after super() returns
        st.session_state.fia_pending_citations = result.get("citations", [])
        st.session_state.fia_pending_provider = result.get("provider", "")
        st.session_state.fia_search_queries = search_batches
        st.session_state.fia_query_type = query_type
        st.session_state.fia_query_plan = query_plan
        st.session_state.fia_search_context = result["answer"]
        st.session_state.fia_raw_search_context = result.get("raw_answer", result["answer"])
        st.session_state.fia_verified_match = verified_match
        st.session_state.fia_locale_attempts = result.get("locale_attempts", [])
        st.session_state.fia_winning_locale = result.get("winning_locale")
        st.session_state.fia_source_tier = result.get("source_tier")

        verified_facts_block = ""
        if query_type == "match_report" and verified_match:
            verified_facts_block = (
                f"--- Verified match facts ---\n{_format_verified_match_facts(verified_match)}\n\n"
            )
        plan_block = (
            "--- Query plan ---\n"
            f"- Answer language: {query_plan.get('answer_language', 'en')}\n"
            f"- Search locales: {', '.join(query_plan.get('search_locales', [])) or 'not set'}\n"
            f"- Winning locale: {result.get('winning_locale') or 'not selected'}\n"
            f"- Source tier: {result.get('source_tier') or 'not selected'}\n\n"
        )
        return (
            f"Detected query type: {query_type}\n\n"
            f"{plan_block}"
            f"{verified_facts_block}"
            f"--- Combined web search results ---\n{result['answer']}"
        )

    def get_input(self):
        if x := st.chat_input(
            placeholder="Ask about any match, player, team, injury, or transfer..."
        ):
            self.handle_input(x)

    def handle_input(self, input, reasoning_effort=None, temperature=1, stream=False):
        # Reset stash (get_relevant_info fills it during this method)
        st.session_state.fia_pending_citations = []
        st.session_state.fia_pending_provider = ""
        st.session_state.fia_search_queries = []
        st.session_state.fia_verified_match = None
        st.session_state.fia_locale_attempts = []
        st.session_state.fia_winning_locale = None
        st.session_state.fia_source_tier = None
        st.session_state.fia_answer_language = "en"

        history_messages = [
            message for message in self.messages_to_display.copy()
            if isinstance(message.get("content"), str)
        ]
        relevant_info = self.get_relevant_info(input)

        self.messages_to_display.append({"role": "user", "content": input})

        citations = st.session_state.get("fia_pending_citations", [])
        provider = st.session_state.get("fia_pending_provider", "")
        search_qs = st.session_state.get("fia_search_queries", [])
        query_type = st.session_state.get("fia_query_type", "")
        verified_match = st.session_state.get("fia_verified_match")
        locale_attempts = st.session_state.get("fia_locale_attempts", [])
        answer_language = st.session_state.get("fia_answer_language", "en")
        winning_locale = st.session_state.get("fia_winning_locale")
        source_tier = st.session_state.get("fia_source_tier")

        eval_scores = None
        if query_type == "match_report" and not match_report_can_answer(verified_match):
            assistant_content = _localize_refusal_message(
                build_match_report_refusal(verified_match),
                answer_language,
            )
        else:
            llm_messages = self.instruction_messages() + history_messages
            llm_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Answer in language `{answer_language}`.\n\n"
                        f"Here is the relevant information to answer the users query: {relevant_info}\n\n"
                        f"```User: {input}```"
                    ),
                }
            )
            st.expander("Chat transcript", expanded=False).write(llm_messages)

            with st.spinner("Writing answer..."):
                assistant_content = _call_llm(llm_messages)
            assistant_content = _linkify_citations(assistant_content, citations)

            with st.spinner("Evaluating answer quality..."):
                eval_scores = _evaluate_answer(
                    input,
                    assistant_content,
                    st.session_state.get("fia_search_context", ""),
                )

        self.messages_to_display.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "citations": citations,
                "provider": provider,
                "search_queries": search_qs,
                "eval_scores": eval_scores,
                "verified_match": verified_match,
                "locale_attempts": locale_attempts,
                "answer_language": answer_language,
                "winning_locale": winning_locale,
                "source_tier": source_tier,
            }
        )

    def display_messages(self):
        from itertools import groupby
        from types import GeneratorType

        from classes.visual import Visual

        for key, group in groupby(self.messages_to_display, lambda x: x["role"]):
            group = list(group)
            avatar = (
                "data/ressources/img/twelve_chat_logo.svg" if key == "assistant" else None
            )
            with st.chat_message(name=key, avatar=avatar):
                for message in group:
                    content = message["content"]
                    if isinstance(content, GeneratorType):
                        final_text = st.write_stream(content)
                        message["content"] = final_text
                    elif isinstance(content, str):
                        st.markdown(content)
                    elif isinstance(content, Visual):
                        content.show()

                    if key == "assistant":
                        if message.get("search_queries"):
                            _render_search_expander(message["search_queries"])
                        if message.get("verified_match"):
                            _render_verification(
                                message["verified_match"],
                                locale_attempts=message.get("locale_attempts", []),
                                answer_language=message.get("answer_language", "en"),
                            )
                        if message.get("citations"):
                            _render_citations(
                                message["citations"], message.get("provider", "")
                            )
                        if message.get("eval_scores"):
                            _render_evaluation(message["eval_scores"])


# ===========================================================================
# PAGE — worldisation pattern (mirrors football_scout.py / wvs_chat.py)
# ===========================================================================

sidebar_container = add_common_page_elements()
page_container = st.sidebar.container()
sidebar_container = st.sidebar.container()

st.divider()

st.write(
    "This app can only handle three or four users at a time. Please "
    "[download](https://github.com/soccermatics/twelve-gpt-educational) "
    "and run on your own computer with your own API keys."
)

with open("model cards/model-card-internet-analyst.md", "r", encoding="utf-8") as f:
    model_card_text = f.read()
st.expander("Model card for Full Internet Analyst", expanded=False).markdown(model_card_text)

st.expander("Trusted sources", expanded=False).write(TRUSTED_DOMAINS)

to_hash = ("internet_analyst",)
chat = create_chat(to_hash, InternetAnalystChat)

if chat.state == "empty":
    chat.add_message(
        "Welcome to the Full Internet Analyst. Ask me about any football match, "
        "player performance, team form, injury, or transfer story. I will search "
        "trusted local-language and English sources where appropriate, then answer "
        "in your language when the evidence is strong enough.",
        role="assistant",
    )
    chat.state = "default"

chat.get_input()
chat.display_messages()
chat.save_state()
