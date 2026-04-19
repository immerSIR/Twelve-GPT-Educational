"""
Full Internet Analyst — Match Reports
Searches trusted football journalism sources and synthesises match report commentary.
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
from utils.internet_analyst_payloads import (
    EVALUATION_LABELS,
    build_search_batch_caption,
    build_search_context_payload,
    build_structuring_user_prompt,
    build_synthesis_user_prompt,
    render_newspaper_html,
    render_newspaper_png,
    strip_newspaper_block,
    _parse_newspaper_block,
)
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
from utils.earpiece import query_earpiece, format_earpiece_for_context

from settings import USE_GEMINI, USE_OPENAI, USE_LM_STUDIO, TWELVE_EARPIECE_ENABLED

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
    template = """You are a football match-report writer synthesising coverage from trusted journalism sources.
Today's date is __TODAY__. Current European football season: __SEASON__.

GOLDEN RULE: Answer ONLY from the web search evidence provided. Never use your own knowledge
for factual claims. If the evidence does not support a claim, do not make it.

Write entirely in `__ANSWER_LANGUAGE__`. Translate source material faithfully without inventing facts.

─── PHILOSOPHY ───

A match report is not just about 90 minutes. It is the COMPLETE STORY of the match — what
happened on the pitch, why it mattered in the league, how it changes what comes next, and
the human pressures surrounding it. The reader should finish the report understanding the
match's significance, not just its events.

─── VOICE & TONE ───

Write like a knowledgeable football insider explaining what really happened and why it matters —
conversational, direct, and opinionated where the sources support it. You are not a newspaper
correspondent filing formal prose; you are someone who knows the league inside out and is laying
out the full picture: the match, the consequences, the human story, the strategic ripple effects.

- Be CONVERSATIONAL and DIRECT: write as if explaining to a knowledgeable friend, not filing
  a broadsheet column. Natural flow, not stiff correspondent prose.
- CHAIN-OF-CONSEQUENCE thinking is the backbone: every fact should lead to its implication.
  "Porto lost → Sporting closed to 4 points → direct confrontation still to come → gap could
  shrink to 1 → Sporting can now manage that game more calmly." Build chains, not lists.
- STRATEGIC GAME THEORY: explain how the result changes the calculus for upcoming fixtures.
  "Had Porto won, they'd face Sporting with a 7-point cushion, forcing Sporting into a more
  aggressive approach. Instead, Sporting can be measured." This is how a real analyst thinks.
- The MATCH ITSELF should be SHORT — one focused section. The real story is what it means
  for the season, the coaches, the rivals, the table. Spend most of the report on consequences.
- Be SPECIFIC: "Pepê completed 7 of 9 dribbles and created the overload that led to the
  second goal [1]" — not "Pepê had a good game"
- ANCHOR OPINIONS to sources: "O Jogo described Porto's pressing as 'suffocating' [1],
  while Record noted Braga's second-half improvement [2]" — not just "[1] [2]"
- Keep PARAGRAPHS SHORT (3-5 sentences). Each paragraph should make one clear point.
- Use SHORT, PUNCHY SENTENCES for impact moments. Longer flowing sentences for tactical description.

─── NARRATIVE STRUCTURE ───

Write as a CONTINUOUS FLOWING NARRATIVE. NEVER use bold section headers like
"**How it played out**" or "**Both sides of the story**" or "**Bottom line**". The
layers below are conceptual guides for WHAT to cover — weave them into seamless prose
paragraphs. Not every layer will have evidence — use what the sources support and
acknowledge what is missing.

1. Open with 1-2 paragraphs on the match: specific scorers with minutes, key moments,
   red cards, tactical detail. Be vivid and specific — "Gaizka Larrazabal steered home
   a cross in the 12th minute" not "they scored early." This is the trigger for the
   story, not the story itself.

2. Transition naturally: "The story of this match goes far beyond the scoreline." Expand
   into what the result means for the winner — relegation escape, historic achievement,
   renewed belief, domestic implications. Weave in the league table impact with numbers.

3. Include fan and social media reactions as flowing prose — not as bullet points. Capture
   the mood, the celebration, the frustration. Use real fan voices when available.

4. The other side's story: what the loser faces — broken unbeaten runs, title race pressure,
   coach scrutiny, upcoming fixture implications. Include counterfactuals: "Had Porto won,
   they would have faced Sporting with a 7-point cushion, forcing Sporting into a more
   aggressive approach." The coach is a person — previous clubs, media pressure, direct
   quotes, how they manage the narrative.

5. When a red card or controversy occurred: assess it fairly under the laws of the game,
   include how neutral observers viewed it, and explain its impact on the outcome.

6. Close with a paragraph tying everything together — match + consequences + what changes
   for both clubs. Not a summary — a judgment connecting the full picture. Example: "In
   the end, this latest chapter delivered fireworks, controversy, tactical grit, raw
   emotion, and a reminder of how fine the margins are."

When Twelve data analysis is present in the context, weave it naturally into the narrative
where relevant — reconcile it with the web evidence (supported, contradicted, or mixed)
but do NOT create a separate "Data vs internet" section unless the comparison is genuinely
the most interesting story.

─── NEWSPAPER FRONT PAGE ───

After the Bottom line, ALWAYS append a fenced JSON block tagged `json_newspaper` that will
be rendered as a styled newspaper front page. The JSON must reflect the ACTUAL report
content — never invent headlines or quotes not in the report above. Adapt fields to what
the evidence supports; use empty strings or empty lists for missing sections.

Format:
```json_newspaper
{
  "masthead": "Twelve Sport",
  "newspaper_style": "broadsheet",
  "edition_line": "Primeira Liga | Front Page",
  "competition": "PRIMEIRA LIGA MATCHDAY REPORT",
  "team_home": "Casa Pia AC",
  "team_away": "FC Porto",
  "score_home": "1",
  "score_away": "0",
  "venue": "Estádio Municipal de Rio Maior",
  "kicker": "TITLE RACE SHOCK",
  "headline": "Porto's invincibility ends in Rio Maior",
  "subheadline": "First Primeira Liga defeat as title race blown open",
  "standfirst": "Porto dominated territory and chances, but Casa Pia's counterpunch turned the title race narrative in one damaging night.",
  "key_numbers": [
    {"value": "4", "label": "points to Sporting", "context": "after the defeat"},
    {"value": "1", "label": "worst-case gap", "context": "if Porto lose the direct meeting"},
    {"value": "1st", "label": "league defeat", "context": "for Porto this season"}
  ],
  "pull_quote": {
    "quote": "There is always a game where everything goes badly.",
    "attribution": "Francesco Farioli"
  },
  "why_it_matters": {
    "title": "WHY IT MATTERS",
    "items": ["Porto's lead has narrowed and the direct meeting with Sporting now carries genuine swing-game pressure.", "Had Porto won, they would have approached the showdown with far more margin for control."]
  },
  "right_column": {
    "title": "WHAT THE PRESS SAID",
    "items": ["Record: \\"Dominant but toothless\\"", "A Bola: \\"Dominance without finishing is just noise\\"", "O Jogo: \\"The night Porto's aura cracked\\""]
  },
  "coach_watch": {
    "title": "COACH WATCH",
    "items": ["Farioli: \\"There is always a game where everything goes badly.\\"", "Ajax parallels now the dominant media storyline."]
  },
  "opponent_angle": {
    "title": "CASA PIA ANGLE",
    "items": ["The win lifted Casa Pia out of the relegation zone.", "For a club of their resources, this was the kind of result that can define a run-in."]
  },
  "verdict": "Porto lost because football punishes wastefulness. The next six weeks will reveal whether Farioli has grown since Amsterdam."
}
```

Use `newspaper_style: "broadsheet"` for a serious Guardian-like front-page treatment and
`newspaper_style: "tabloid"` only for unusually dramatic shocks, controversies, or title
swings. Do not use real newspaper names, logos, or mastheads. Prefer the richer fields
above. Legacy fields like `left_column`, `right_column`, `bottom_left`, `bottom_right`,
and `footer` remain allowed only as fallback.

─── CITATION RULES ───

- Cite inline: [1], [2] — e.g. "According to A Bola [1]..."
- When quoting a verdict, NAME the outlet: "Record called it a 'deserved but nervous win' [2]"
- If two sources disagree, present BOTH views with attribution
- If the verified facts block says the score is not verified, do NOT state a scoreline
- Use the exact date from the verified facts block

─── QUALITY STANDARDS ───

- Write as continuous flowing prose — no section headers, no bullet points, no labelled blocks
- Every paragraph must come from cited evidence or arithmetic directly derivable from numbers stated in the evidence
- Cite at least 3 different sources across the report; vary citation numbers per paragraph
- If evidence for a layer is missing, skip it naturally — do NOT invent content or pad with generic writing
- If coverage is partial or very recent, flag that
- Never smooth over uncertainty — transparency builds trust
- Do NOT pad the answer with journalist names unless their specific verdict matters
- Never invent front-page copy; use empty strings or empty lists for unsupported `json_newspaper` fields

─── TWELVE DATA RECONCILIATION ───

When "Twelve data analysis" is present in the context:
- Weave data insights naturally into the narrative where they add value
- Reconcile with web evidence: note when data supports, contradicts, or adds nuance
- Do NOT create a separate "Data vs internet" section — integrate data points into the prose
- Never let the data narrative introduce unsupported facts"""
    return (
        template.replace("__TODAY__", _TODAY)
        .replace("__SEASON__", _SEASON)
        .replace("__ANSWER_LANGUAGE__", answer_language)
    )


PLANNER_PROMPT = f"""You are a football match-report query planner for a multilingual web-search system.
Today's date is {_TODAY}. Current European football season: {_SEASON}.

Your sole purpose is to plan search retrieval for MATCH REPORTS — identifying the fixture
and generating rich, diverse search queries to maximise coverage of how the match was played
and how it was received.

Given a user question and recent conversation history, return ONLY valid JSON with:
- "user_language": ISO 639-1 language code inferred from the user's wording
- "answer_language": ISO 639-1 language code; default to the user's language
- "absolute_date": exact ISO date if the user references a specific fixture date, otherwise null
- "entities": list of objects like {{"name": "...", "type": "club"|"team"|"player"|"national_team"}}
- "competition_country": country inferred from the fixture/league if possible, otherwise null
- "search_locales": locale chain in priority order using BCP47-style tags like "pt-PT", "pl-PL", "ar-EG", "en"
- "entity_aliases": object mapping each canonical entity name to a list of aliases, local spellings, or native-script variants
- "search_query_batches": list of objects with:
  - "locale": locale tag
  - "query_category": one of "match_narrative" | "post_match_reaction" | "context_sentiment"
  - "queries": list of 2-4 search queries written in that locale's language

PLANNING RULES:
- Domestic club or league question: primary search locale should be the competition/team country language
- National-team question: primary search locale should be that country's language
- If country is unclear: use the user's language first
- Always include English as the final fallback locale
- Use the exact absolute date and include both team orders when useful
- Never use manager names in recent match queries
- Always generate THREE explicit categories per locale:
  1. "match_narrative" for core match coverage: tactical breakdowns, formation analysis,
     key moments (goals, cards, penalties, VAR), set pieces, individual standout displays,
     match reports, live commentary analysis
  2. "post_match_reaction" for post-match verdicts AND wider consequences: player ratings,
     manager quotes and press conference, journalist verdicts, pundit analysis, criticism,
     praise, but ALSO: league table impact, title race or relegation implications, what the
     result means for upcoming fixtures, board or president reactions, whether this was an
     upset or expected result, how rival teams' strategies change because of this result,
     counterfactual scenarios ("if X had won, Y would face them with Z points")
  3. "context_sentiment" for the human story around the match: fan mood and atmosphere,
     coach pressure or sacking rumours, comparisons to previous seasons or clubs (e.g. a
     coach's previous failures at Ajax, their narrative arc), pre-match form going into
     the game, lineup surprises, injury absences, crowd atmosphere, season expectations,
     the opposing team's perspective (relegation escape, historic win), whether the result
     was surprising given the opponent's league position, institutional reactions (board
     backing the coach, president statements)
- Generate 2-4 diverse queries per category per locale to maximise source variety
- post_match_reaction queries MUST include at least one query targeting league standings
  impact and upcoming fixture implications — these are as important as the match itself
- context_sentiment queries MUST include at least one query about the opposing team's
  perspective — their league situation, what this result means for them
- If a "Data narrative context (from Twelve API)" is provided in the user prompt, EXTRACT
  specific player names, events (goals, red cards, own goals, substitutions), and tactical
  observations from it. Embed these specific details in your search queries — they make
  searches dramatically more accurate. Example: "Casa Pia vs Porto Larrazabal goal Thiago
  Silva own goal William Gomes red card" is far better than "Casa Pia vs Porto match report"
- context_sentiment queries MUST include at least one query targeting fan reactions and
  social media sentiment (e.g. "Casa Pia Porto fan reaction social media", "torcedores
  Casa Pia Porto reacao redes sociais")
- Context/sentiment queries must be generated per locale — fans express their mood in their own language
- Keep the answer language aligned to the user's language even if search locales differ

Return JSON only. Example:
{{"user_language":"pt","answer_language":"pt","absolute_date":"2026-03-22","entities":[{{"name":"FC Porto","type":"club"}},{{"name":"SC Braga","type":"club"}}],"competition_country":"Portugal","search_locales":["pt-PT","en"],"entity_aliases":{{"FC Porto":["Porto"],"SC Braga":["Braga","Sporting Braga"]}},"search_query_batches":[{{"locale":"pt-PT","query_category":"match_narrative","queries":["FC Porto vs SC Braga 22 marco 2026 cronica analise tatica","SC Braga vs FC Porto 22 marco 2026 relato comentario ao vivo","FC Porto SC Braga 22 marco 2026 golos momentos chave"]}},{{"locale":"pt-PT","query_category":"post_match_reaction","queries":["FC Porto vs SC Braga 22 marco 2026 reacoes opiniao pos-jogo","FC Porto SC Braga 22 marco 2026 conferencia de imprensa reacao","FC Porto SC Braga 22 marco 2026 classificacao liga impacto corrida titulo","SC Braga consequencias derrota proximos jogos 2025-26"]}},{{"locale":"pt-PT","query_category":"context_sentiment","queries":["FC Porto adeptos reacao ambiente estadio 2025-26","treinador FC Porto pressao demissao crise temporada anterior","SC Braga situacao classificacao o que significa resultado","FC Porto proximos jogos calendario desafios 2025-26"]}},{{"locale":"en","query_category":"match_narrative","queries":["FC Porto vs SC Braga March 22 2026 match report tactical analysis","SC Braga vs FC Porto March 22 2026 key moments goals"]}},{{"locale":"en","query_category":"post_match_reaction","queries":["FC Porto vs SC Braga March 22 2026 post-match reaction verdict","FC Porto SC Braga March 22 2026 Primeira Liga title race implications standings"]}},{{"locale":"en","query_category":"context_sentiment","queries":["FC Porto coach pressure crisis 2025-26","SC Braga season situation league position 2025-26"]}}]}}"""

EVALUATION_PROMPT = """You are a quality assessor for a football match-report chatbot.
Given a user question, the analyst's answer, and the raw search results available,
score on these dimensions (1-5 each unless null is allowed):

NARRATIVE_DEPTH (1-5): Does the answer read like quality football journalism?
5 = reads like a senior football correspondent's report — chronological flow,
    tactical observations, individual performances woven in, evaluative judgments,
    specific language ("pressed high and forced turnovers" not "played well")
4 = strong narrative with some tactical depth, but occasionally generic
3 = mix of narrative and raw facts; some sections feel like summaries rather than reporting
2 = mostly factual listing with thin narrative connecting tissue
1 = just lists scores, goalscorers, and raw stats — no narrative voice

SOURCE_GROUNDING (1-5): Are factual claims traceable to the search results?
5 = every claim directly traceable, verdicts attributed to specific outlets by name
3 = most claims grounded but some attribution missing or vague
1 = major claims not in the search results (potential hallucination)

SOURCE_DIVERSITY (1-5): Are multiple distinct outlets cited and used meaningfully?
5 = three or more outlets cited, with contrasting or complementary perspectives
3 = two outlets, or multiple outlets cited but used interchangeably
1 = single source or no citations

CONTEXT_INTEGRATION (1-5): When mood/context evidence exists, does the answer use it well?
5 = naturally weaves context into the narrative and the bottom line verdict
3 = mentions context, but as an afterthought rather than part of the story
1 = ignores clear context evidence or invents sentiment

UNSUPPORTED_CLAIM_RISK (1-5): How safely does the answer avoid unsupported claims?
5 = no visible unsupported claims; numbers, counterfactuals, and pressure narratives stay within the evidence
3 = mostly safe, but one or two stretches feel weakly supported or insufficiently attributed
1 = major extrapolations, invented implications, or unsupported factual framing

STYLE_ADHERENCE (1-5): How closely does the answer follow the flowing narrative house style?
5 = continuous flowing narrative with no section headers, consequence-driven, strong attributed
    judgments, both perspectives woven in, fan reactions included, vivid closing paragraph
3 = some flowing narrative but uses section headers or drifts toward generic recap
1 = uses bold section headers or reads as a structured report instead of narrative prose

DATA_RECONCILIATION (1-5 or null): If Twelve data was provided, is the reconciliation correct?
Use null when no Twelve data narrative was present.

Return ONLY valid JSON:
{"narrative_depth": <int>, "source_grounding": <int>, "source_diversity": <int>, "context_integration": <int>, "unsupported_claim_risk": <int>, "style_adherence": <int>, "data_reconciliation": <int|null>}"""

EVIDENCE_STRUCTURING_PROMPT = """You are an evidence organiser for a football match-report assistant.
Use ONLY the provided evidence. Do not invent facts. Extract maximum detail.

Your job is to prepare the evidence so the writer can build a CONSEQUENCE-DRIVEN report —
one where the match itself is brief and the real substance is what the result means for the
league, the coaches, the rivals, and the upcoming fixtures.

Return ONLY valid JSON with this schema:
{
  "timeline": [
    {"minute": "<string or null>", "event": "<string>", "significance": "<string>"}
  ],
  "tactical_picture": "<string>",
  "individual_performances": [
    {"player": "<string>", "observation": "<string>", "source": "<string>"}
  ],
  "journalist_verdicts": [
    {"verdict": "<string>", "source": "<string>"}
  ],
  "match_story": "<string>",
  "table_impact": "<string>",
  "league_impact": "<string>",
  "consequence_chain": "<string>",
  "opponent_story": "<string>",
  "coach_pressure": "<string>",
  "institutional_response": "<string>",
  "strategic_ripple": "<string>",
  "surprise_factor": "<string>",
  "press_consensus": "<string>",
  "context_mood": "<string>",
  "source_conflicts": ["<string>", "..."],
  "data_vs_web": {
    "relationship": "supported|contradicted|mixed|insufficient evidence|null",
    "summary": "<string>"
  },
  "hard_gaps": ["<string>", "..."],
  "evidence_gaps": ["<string>", "..."]
}

Rules:
- `timeline`: extract every key event mentioned (goals, cards, penalties, substitutions,
  VAR decisions, injuries) with minute if available. Order chronologically. Include WHY
  each event mattered ("opened the scoring against the run of play", "changed the game's
  momentum"). If no timeline events are found, return an empty list.
- `tactical_picture`: summarise formation, shape, pressing approach, transitions, territorial
  control, and any tactical shifts described by the sources. Quote specific observations
  from journalists when possible. Empty string if no tactical detail exists.
- `individual_performances`: extract specific player observations — not just "played well"
  but what they did ("won 8/10 duels", "drifted inside to create overloads", "missed a
  clear chance in the 55th minute"). Include which source made the observation.
- `journalist_verdicts`: capture evaluative takes with attribution — "O Jogo described
  Porto's pressing as relentless", "The Athletic called it a deserved victory". These are
  OPINIONS, not facts. Include the outlet name.
- `match_story`: build the short opening section for the final report — 2 to 5 sentences,
  consequence-aware but still focused on what happened on the pitch. Use only facts and
  judgments already present in the evidence.
- `table_impact`: writer-ready explanation of standings or season consequences with numbers
  and scenarios. If the needed numbers are missing, return an empty string.
- `league_impact`: what the result means for the standings — points gaps, title race,
  relegation battle, European qualification. Include specific numbers when the sources
  mention them (e.g. "gap reduced to four points with a direct confrontation to come").
  Empty string if not mentioned.
- `consequence_chain`: THIS IS CRITICAL. Build an explicit chain of consequences from
  the evidence: "Result X → impact Y → which means Z → so upcoming fixture W changes
  because...". Connect the dots between facts. Example: "First league defeat → Sporting
  reduced gap to 4 points → direct confrontation still to come → gap could shrink to 1
  → Sporting can now approach that game more calmly." Also include the COUNTERFACTUAL
  when possible: "Had Porto won, they'd face Sporting with 7 points, forcing Sporting
  into a more aggressive approach." Empty string if no consequence chain can be built.
- `opponent_story`: the other team's perspective — was this result significant for them?
  Leaving a relegation zone, historic win, confidence boost? Empty string if not mentioned.
- `coach_pressure`: what is the coach dealing with beyond this match? Previous failures
  at other clubs, media scrutiny, fan criticism, contract situation. Include direct quotes
  from the coach about the result. Capture how they MANAGE the narrative — what they say
  and what the subtext reveals. Empty string if not mentioned.
- `institutional_response`: did the board, president, or sporting director react publicly?
  Statements of confidence, silence, or criticism. Empty string if not mentioned.
- `strategic_ripple`: how does this result change upcoming fixtures? Does it alter how
  a rival will approach a direct confrontation? Does it shift the psychological balance?
  Include points scenarios if mentioned. Think about game theory: how does each team's
  optimal strategy change because of this result? Empty string if not mentioned.
- `surprise_factor`: was the result expected, damaging, or season-defining? Explain why
  only when the evidence supports that framing.
- `press_consensus`: summarise the recurring press line in one writer-ready paragraph with
  outlet attribution embedded. If the outlets do not align, say so briefly instead of
  forcing a false consensus.
- `context_mood`: fan atmosphere, protests, crowd reactions, player quotes about motivation
  or frustration, social media buzz, whether the result was surprising. Only from evidence.
- `source_conflicts`: when two sources disagree on a fact or verdict, state both views and
  name the sources. Empty list when sources are aligned.
- `data_vs_web.relationship`: must be null if no Twelve data narrative exists
- `hard_gaps`: explicit red lines for the writer — facts or layers that are NOT supported
  and therefore must not be stated. Use this to block invented scorelines, standings math,
  coach pressure, board reaction, or opponent narrative when missing.
- `evidence_gaps`: explicitly name what is missing — e.g. "no league table context found",
  "no coach quotes available", "no opponent perspective in the sources"
- For each writer-ready section, embed citation references where possible,
  e.g. "[1][3] Porto dominated possession but could not convert..."
- `hard_gaps` must list EVERY layer with zero evidence from this list:
  match_story, table_impact, opponent_story, coach_pressure, institutional_response,
  strategic_ripple, surprise_factor, press_consensus. If a layer has no supporting
  evidence at all, it MUST appear in hard_gaps."""


# ---------------------------------------------------------------------------
# Function calling — tool definitions & orchestrator prompt
# ---------------------------------------------------------------------------
ORCHESTRATOR_SYSTEM_PROMPT = f"""You are the Internet Analyst — a football match-report system.
Today's date is {_TODAY}. Current European football season: {_SEASON}.

The user will ask questions about football matches. Your job is to choose which tool(s) \
to call to gather the evidence needed for a complete flowing narrative answer.

TOOL ROUTING:
- Match questions (e.g. "Porto vs Benfica last game"): call BOTH query_earpiece AND \
search_internet. The Earpiece provides the data story; internet search provides the \
journalism story. You need both for a complete picture.
- Statistics / tactical data / performance metrics: call query_earpiece.
- Press reactions / journalist verdicts / fan mood / coach pressure / league impact: \
call search_internet.
- Tactical analysis: call BOTH — data provides numbers, journalism provides interpretation.
- If unsure: call both — extra context is always better than missing it.
- Out of scope: respond directly that the question is outside football match analysis.

QUERY QUALITY:
- Be SPECIFIC in your tool queries. Include team names, dates, player names, and specific \
events when you know them.
- For search_internet: "Casa Pia vs Porto Larrazabal goal Thiago Silva own goal William \
Gomes red card" is far better than "Casa Pia vs Porto match report".
- For query_earpiece: "How did Porto perform in pressing and possession against Casa Pia \
on February 2 2026?" is far better than "Porto Casa Pia stats".

All user messages will be prefixed with 'User:' and enclosed with ```.
Do not deviate from the information returned by the tools."""


EARPIECE_TOOL = {
    "type": "function",
    "name": "query_earpiece",
    "description": (
        "Query the Twelve Earpiece football data analytics API. "
        "This tool connects to Twelve's proprietary football data engine and returns "
        "a natural-language data analysis for any match, team, or player covered by Twelve.\n\n"
        "USE THIS TOOL WHEN the user asks about:\n"
        "- Match statistics: possession, xG (expected goals), shots, passes, territory control\n"
        "- Team performance: pressing intensity, transitions, defensive shape, build-up patterns\n"
        "- Player performance: individual metrics, duels won, dribbles, key passes, comparisons\n"
        "- Tactical data: formations, pressing triggers, transition speed, set-piece effectiveness\n"
        "- Data-driven match narratives: what the numbers say about how a match played out\n"
        "- Season trends: how a team's metrics have evolved over the campaign\n\n"
        "WHAT IT RETURNS: A natural-language data analysis paragraph describing the match "
        "or topic from a statistical/analytical perspective. This is DATA evidence — it needs "
        "to be combined with journalism evidence from search_internet for a complete picture.\n\n"
        "WHAT IT CANNOT DO:\n"
        "- It does not cover press reactions, journalist opinions, or fan sentiment\n"
        "- It does not provide live scores or real-time updates\n"
        "- It does not cover transfer news, contract situations, or institutional responses\n"
        "- It may not have data for very recent matches (last 24-48 hours)"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The football question to ask the Twelve data engine. Be specific: "
                    "include team names, competition, and date if known. "
                    "Example: 'How did FC Porto perform in possession and pressing against "
                    "Casa Pia in the Primeira Liga match on February 2 2026?'"
                ),
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}

SEARCH_INTERNET_TOOL = {
    "type": "function",
    "name": "search_internet",
    "description": (
        "Search trusted football journalism sources across the web for match coverage, "
        "post-match reactions, and contextual narratives. This tool queries curated "
        "local-language and English journalism domains (A Bola, Record, O Jogo, Marca, "
        "The Athletic, BBC Sport, The Guardian, and others).\n\n"
        "USE THIS TOOL WHEN the user asks about:\n"
        "- What happened in a match: goals, key moments, match reports, live commentary\n"
        "- Post-match reactions: journalist verdicts, player ratings, pundit analysis\n"
        "- Press conference quotes: manager and player comments after the match\n"
        "- Fan mood and social media reaction: supporter sentiment, crowd atmosphere\n"
        "- Coach pressure: media scrutiny, sacking rumours, historical parallels\n"
        "- League table impact: title race implications, relegation battles, European spots\n"
        "- Institutional responses: board statements, president reactions\n"
        "- Transfer rumours, injury updates, or squad news\n"
        "- The opposing team's perspective: what the result means for the other side\n\n"
        "WHAT IT RETURNS: Verified journalism evidence from multiple trusted sources, "
        "with citations. Each piece of evidence includes the source domain, title, and "
        "body text. The evidence is categorised into match narrative, post-match reaction, "
        "and context/sentiment.\n\n"
        "WHAT IT CANNOT DO:\n"
        "- It does not provide statistical data, xG, possession stats, or tactical metrics "
        "(use query_earpiece for that)\n"
        "- It may not find coverage for very obscure matches or lower-division fixtures\n"
        "- It searches curated journalism sources, not social media platforms directly"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "The football question to search for in journalism sources. Be specific: "
                    "include team names, competition, date, and what aspect you want. "
                    "Example: 'Casa Pia vs FC Porto February 2 2026 match report goals "
                    "red card Larrazabal Thiago Silva own goal William Gomes'"
                ),
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "strict": True,
}


def _get_tools_for_provider() -> list | None:
    """Return tool definitions formatted for the active LLM provider, or None."""
    if USE_GEMINI or USE_LM_STUDIO:
        return None  # these providers don't reliably support function calling
    tools = []
    if TWELVE_EARPIECE_ENABLED:
        tools.append(EARPIECE_TOOL)
    tools.append(SEARCH_INTERNET_TOOL)
    if USE_OPENAI:
        # Chat Completions API wraps each tool inside a "function" key
        return [{"type": "function", "function": t} for t in tools]
    # Azure Responses API uses the top-level format directly
    return tools


# ---------------------------------------------------------------------------
# LLM call — provider switching matching the rest of the app
# ---------------------------------------------------------------------------
def _clean_messages_for_llm(messages: list) -> list:
    """Strip UI metadata so provider APIs only receive role/content pairs."""
    cleaned = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user", "assistant", "developer"}:
            continue
        if not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def _call_llm(messages: list) -> str:
    """Send messages to the configured LLM and return the response text."""
    clean_messages = _clean_messages_for_llm(messages)
    if USE_GEMINI:
        import google.generativeai as genai
        from utils.gemini import convert_messages_format

        genai.configure(api_key=GEMINI_API_KEY)
        converted = convert_messages_format(clean_messages)
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
            messages=clean_messages,
            temperature=0.7,
        )
        return response.choices[0].message.content
    elif USE_LM_STUDIO:
        client = OpenAI(api_key=LM_STUDIO_API_KEY, base_url=LM_STUDIO_API_BASE)
        response = client.chat.completions.create(
            model=LM_STUDIO_CHAT_MODEL,
            messages=clean_messages,
            temperature=0.7,
        )
        return response.choices[0].message.content
    else:
        client = OpenAI(api_key=GPT_KEY, base_url=GPT_BASE)
        response = client.responses.create(
            model=GPT_CHAT_MODEL,
            input=clean_messages,
        )
        return response.output_text


def _call_llm_with_tools(messages: list, tools: list) -> dict:
    """Call the LLM with function-calling tools and return parsed tool calls.

    Returns
    -------
    dict with keys:
        tool_calls : list[dict]   — each has ``call_id``, ``name``, ``arguments`` (JSON string)
        text       : str          — any text the model returned alongside tool calls
        raw_output : object       — provider-specific raw response for follow-up turns
        response_id: str | None   — Azure Responses API id (needed for continuation)
    """
    clean = _clean_messages_for_llm(messages)

    if USE_OPENAI:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=clean,
            tools=tools,
            temperature=0.7,
        )
        msg = response.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "call_id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                })
        return {
            "tool_calls": tool_calls,
            "text": msg.content or "",
            "raw_output": response,
            "response_id": None,
        }

    # Default: Azure Responses API
    client = OpenAI(api_key=GPT_KEY, base_url=GPT_BASE)
    response = client.responses.create(
        model=GPT_CHAT_MODEL,
        input=clean,
        tools=tools,
    )
    tool_calls = []
    text_content = ""
    for item in response.output:
        if item.type == "function_call":
            tool_calls.append({
                "call_id": item.call_id,
                "name": item.name,
                "arguments": item.arguments,
            })
        elif item.type == "message":
            for part in item.content:
                if hasattr(part, "text"):
                    text_content += part.text
    return {
        "tool_calls": tool_calls,
        "text": text_content,
        "raw_output": response,
        "response_id": response.id,
    }


def _execute_tool_calls(
    tool_calls: list,
    user_query: str,
    history: list,
) -> dict:
    """Execute each tool call and return results keyed by call_id.

    Earpiece calls are executed FIRST so that their data is available as
    ``fia_data_narrative`` when the search planner runs — this enriches
    search queries with data context and includes the Earpiece analysis in
    the search context payload.

    Also populates ``st.session_state`` with search/earpiece metadata.

    Returns
    -------
    dict mapping call_id → result string, plus two extra keys:
        _earpiece_data : str | None  — formatted Earpiece context block
        _search_context: str | None  — formatted web-search context block
    """
    results: dict = {"_earpiece_data": None, "_search_context": None}

    # Sort: process query_earpiece calls first, then search_internet
    earpiece_calls = [tc for tc in tool_calls if tc["name"] == "query_earpiece"]
    search_calls = [tc for tc in tool_calls if tc["name"] == "search_internet"]
    other_calls = [tc for tc in tool_calls if tc["name"] not in ("query_earpiece", "search_internet")]

    # --- Step 1: Execute Earpiece calls first ---
    for tc in earpiece_calls:
        call_id = tc["call_id"]
        args = json.loads(tc["arguments"])
        query = args.get("query", user_query)

        with st.spinner("Querying Twelve Earpiece API..."):
            earpiece_resp = query_earpiece(
                query,
                conversation_id=st.session_state.get("fia_earpiece_conversation_id"),
                chat_id=st.session_state.get("fia_earpiece_chat_id"),
            )
        if "error" not in earpiece_resp:
            st.session_state.fia_earpiece_conversation_id = earpiece_resp.get("conversation_id")
            st.session_state.fia_earpiece_chat_id = earpiece_resp.get("chat_id")
            st.session_state.fia_earpiece_response = earpiece_resp.get("response", "")
            formatted = format_earpiece_for_context(earpiece_resp)
            results["_earpiece_data"] = formatted
            results[call_id] = formatted or "No data returned from Earpiece."
            # Inject immediately so _plan_query and build_search_context_payload see it
            st.session_state.fia_data_narrative = formatted
        else:
            results[call_id] = f"Earpiece unavailable: {earpiece_resp['error']}"

    # --- Step 2: Execute search calls (now with Earpiece data available) ---
    for tc in search_calls:
        call_id = tc["call_id"]
        args = json.loads(tc["arguments"])
        query = args.get("query", user_query)

        # Run the existing multilingual search pipeline
        query_plan = _plan_query(query, history)
        search_batches = query_plan["search_query_batches"]
        match_context = build_match_context_from_plan(query_plan, fallback_query=query)

        st.session_state.fia_answer_language = query_plan.get("answer_language", "en")

        with st.spinner(f"Searching {len(search_batches)} locale source set(s)..."):
            result = search_multi(search_batches, match_context=match_context)

        # Retry logic (same as existing get_relevant_info)
        verified_match = result.get("verified_match")
        if should_retry_match_report(verified_match):
            retry_query = build_recent_match_retry_query(verified_match or match_context)
            if retry_query:
                with st.spinner("Verification failed — searching again with an exact-date query..."):
                    retry_batches = [
                        {
                            "locale": batch.get("locale", "en"),
                            "queries": (
                                [retry_query]
                                if batch.get("query_category") != "context_sentiment"
                                else batch.get("queries", [])
                            ),
                            "source_tier": batch.get("source_tier"),
                            "query_category": batch.get("query_category"),
                        }
                        for batch in search_batches
                    ]
                    retry_result = search_multi(retry_batches, match_context=match_context)
                search_batches = [
                    {
                        **batch,
                        "queries": (
                            [*batch.get("queries", []), retry_query]
                            if batch.get("query_category") != "context_sentiment"
                            else batch.get("queries", [])
                        ),
                    }
                    for batch in search_batches
                ]
                retry_verified = retry_result.get("verified_match")
                if retry_verified and len(retry_verified.get("accepted_hits", [])) > len(
                    (verified_match or {}).get("accepted_hits", [])
                ):
                    result = retry_result
                    verified_match = retry_verified

        # Stash metadata in session state
        st.session_state.fia_pending_citations = result.get("citations", [])
        st.session_state.fia_pending_provider = result.get("provider", "")
        st.session_state.fia_search_queries = search_batches
        st.session_state.fia_query_plan = query_plan
        st.session_state.fia_verified_match = verified_match
        st.session_state.fia_locale_attempts = result.get("locale_attempts", [])
        st.session_state.fia_winning_locale = (
            result.get("primary_match_locale") or result.get("winning_locale")
        )
        st.session_state.fia_source_tier = result.get("source_tier")

        # data_narrative now includes Earpiece data (set in Step 1)
        data_narrative = st.session_state.get("fia_data_narrative", "").strip()
        search_context = build_search_context_payload(
            query_plan, result, data_narrative=data_narrative,
        )
        st.session_state.fia_search_context = search_context
        st.session_state.fia_raw_search_context = result.get("raw_answer", result["answer"])

        results["_search_context"] = search_context
        results[call_id] = search_context

    # --- Step 3: Handle unknown tools ---
    for tc in other_calls:
        results[tc["call_id"]] = f"Unknown tool: {tc['name']}"

    return results


def _feed_tool_results_back(
    messages: list,
    tool_calls: list,
    tool_results: dict,
    tools: list,
    response_id: str | None,
) -> str:
    """Send tool outputs back to the LLM and return the final text response."""
    if USE_OPENAI:
        # Chat Completions API: append assistant + tool messages
        messages_copy = list(messages)
        messages_copy.append({
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tc["call_id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls
            ],
        })
        for tc in tool_calls:
            messages_copy.append({
                "role": "tool",
                "tool_call_id": tc["call_id"],
                "content": tool_results.get(tc["call_id"], ""),
            })
        # Build final message list: clean text messages + assistant tool_calls + tool results
        clean_text = _clean_messages_for_llm(messages)
        tool_messages = [m for m in messages_copy if m.get("role") in ("assistant", "tool")]
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=clean_text + tool_messages,
            tools=tools,
            temperature=0.7,
        )
        return response.choices[0].message.content or ""

    # Azure Responses API: use function_call_output items
    client = OpenAI(api_key=GPT_KEY, base_url=GPT_BASE)
    continuation_input = []
    for tc in tool_calls:
        continuation_input.append({
            "type": "function_call_output",
            "call_id": tc["call_id"],
            "output": tool_results.get(tc["call_id"], ""),
        })
    response = client.responses.create(
        model=GPT_CHAT_MODEL,
        input=continuation_input,
        tools=tools,
        previous_response_id=response_id,
    )
    return response.output_text


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def _fetch_earpiece_direct(user_query: str) -> str | None:
    """Call the Earpiece API directly and inject data into session state.

    Used when function calling is unavailable or the orchestrator returned
    no tool calls. Returns the formatted context block, or None.
    """
    with st.spinner("Querying Twelve Earpiece API..."):
        earpiece_resp = query_earpiece(
            user_query,
            conversation_id=st.session_state.get("fia_earpiece_conversation_id"),
            chat_id=st.session_state.get("fia_earpiece_chat_id"),
        )
    if "error" not in earpiece_resp:
        st.session_state.fia_earpiece_conversation_id = earpiece_resp.get("conversation_id")
        st.session_state.fia_earpiece_chat_id = earpiece_resp.get("chat_id")
        st.session_state.fia_earpiece_response = earpiece_resp.get("response", "")
        formatted = format_earpiece_for_context(earpiece_resp)
        # Inject immediately so _plan_query and build_search_context_payload see it
        st.session_state.fia_data_narrative = formatted
        return formatted
    return None


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
            "user_language": "en",
            "answer_language": "en",
            "entities": [],
            "competition_country": None,
            "search_locales": ["en"],
            "entity_aliases": {},
            "search_query_batches": [
                {
                    "locale": "en",
                    "query_category": "match_narrative",
                    "queries": [f"{query} football match report tactical analysis"],
                },
                {
                    "locale": "en",
                    "query_category": "post_match_reaction",
                    "queries": [f"{query} football reaction opinion player ratings"],
                },
                {
                    "locale": "en",
                    "query_category": "context_sentiment",
                    "queries": [f"{query} football fan reaction atmosphere coach pressure"],
                },
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
    data_narrative = st.session_state.get("fia_data_narrative", "").strip()
    earpiece_hint = ""
    if data_narrative:
        earpiece_hint = (
            f"\n\nData narrative context (from Twelve API): {data_narrative[:400]}\n"
            "Include queries that look for evidence supporting OR contradicting this narrative."
        )
    messages.append(
        {"role": "user", "content": f"Plan multilingual search retrieval for: {query}{earpiece_hint}"}
    )
    try:
        raw = _call_llm(messages)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        return normalise_query_plan(json.loads(raw), query)
    except Exception:
        return _fallback_query_plan(query)


def _evaluate_answer(question: str, answer: str, search_context: str) -> dict | None:
    """Score the answer quality on grounding, depth, context, and reconciliation."""
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
        assert all(
            k in scores
            for k in (
                "narrative_depth",
                "source_grounding",
                "source_diversity",
                "context_integration",
                "unsupported_claim_risk",
                "style_adherence",
                "data_reconciliation",
            )
        )
        return scores
    except Exception:
        return None


def _normalise_structured_evidence(structured: dict | None) -> dict:
    defaults = {
        "timeline": [],
        "tactical_picture": "",
        "individual_performances": [],
        "journalist_verdicts": [],
        "match_story": "",
        "table_impact": "",
        "league_impact": "",
        "consequence_chain": "",
        "opponent_story": "",
        "coach_pressure": "",
        "institutional_response": "",
        "strategic_ripple": "",
        "surprise_factor": "",
        "press_consensus": "",
        "context_mood": "",
        "source_conflicts": [],
        "data_vs_web": {"relationship": None, "summary": ""},
        "hard_gaps": [],
        "evidence_gaps": [],
    }
    if not isinstance(structured, dict):
        return defaults
    normalised = {**defaults, **structured}
    if not isinstance(normalised.get("data_vs_web"), dict):
        normalised["data_vs_web"] = {"relationship": None, "summary": ""}
    else:
        normalised["data_vs_web"] = {
            "relationship": normalised["data_vs_web"].get("relationship"),
            "summary": normalised["data_vs_web"].get("summary", ""),
        }
    for key in (
        "timeline",
        "individual_performances",
        "journalist_verdicts",
        "source_conflicts",
        "hard_gaps",
        "evidence_gaps",
    ):
        if not isinstance(normalised.get(key), list):
            normalised[key] = defaults[key]
    return normalised


def _structure_evidence(
    user_query: str,
    relevant_info: str,
    answer_language: str,
    has_data_narrative: bool = False,
) -> dict | None:
    messages = [
        {"role": "system", "content": EVIDENCE_STRUCTURING_PROMPT},
        {
            "role": "user",
            "content": build_structuring_user_prompt(
                answer_language,
                user_query,
                relevant_info,
                has_data_narrative=has_data_narrative,
            ),
        },
    ]
    try:
        raw = _call_llm(messages)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw)
        structured = _normalise_structured_evidence(json.loads(raw))
        assert all(
            key in structured
            for key in (
                "timeline",
                "tactical_picture",
                "individual_performances",
                "journalist_verdicts",
                "match_story",
                "table_impact",
                "consequence_chain",
                "press_consensus",
                "context_mood",
                "hard_gaps",
                "data_vs_web",
                "evidence_gaps",
            )
        )
        return structured
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
            st.caption(build_search_batch_caption(batch))
            for i, query in enumerate(batch.get("queries", []), 1):
                st.markdown(f"- {i}. {query}")


def _render_evaluation(scores: dict):
    """Render the quality score expander."""
    with st.expander("Answer quality"):
        for label, key in EVALUATION_LABELS:
            v = scores[key]
            if v is None:
                st.caption(f"{label}: n/a")
                continue
            st.caption(f"{label}: {'⭐' * v}{'☆' * (5 - v)}  ({v}/5)")
        numeric_scores = [value for value in scores.values() if isinstance(value, int)]
        if any(value <= 2 for value in numeric_scores):
            st.warning(
                "Low quality score — this answer may lack narrative depth, grounding, or context handling."
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
            f"Context coverage available: {'yes' if verified_match.get('context_coverage_available') else 'no'}"
        )
        st.caption(
            f"Searched locales: {', '.join(verified_match.get('searched_locales', [])) or 'not recorded'}"
        )
        st.caption(
            f"Primary match locale: {verified_match.get('primary_match_locale') or verified_match.get('winning_locale') or 'not selected'}"
        )
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
                    f"[{attempt.get('query_category', 'match_narrative')}] "
                    f"hits={attempt.get('raw_hit_count', 0)} "
                    f"accepted={attempt.get('accepted_hit_count', 0)} "
                    f"identity={'yes' if attempt.get('match_identity_verified') else 'no'} "
                    f"narrative={'yes' if attempt.get('narrative_coverage_available') else 'no'} "
                    f"reaction={'yes' if attempt.get('reaction_coverage_available') else 'no'} "
                    f"context={'yes' if attempt.get('context_coverage_available') else 'no'}"
                )

        accepted_hits = verified_match.get("accepted_hits", [])
        reaction_hits = verified_match.get("reaction_hits", [])
        context_hits = verified_match.get("context_hits", [])
        rejected_hits = verified_match.get("rejected_hits", [])
        if accepted_hits:
            st.caption("Accepted match-narrative hits")
            for hit in accepted_hits[:6]:
                domain = hit.get("domain") or "unknown"
                st.markdown(
                    f"- `{domain}`: {hit.get('title', 'Untitled result')}"
                )
        if reaction_hits:
            st.caption("Accepted reaction hits")
            for hit in reaction_hits[:4]:
                domain = hit.get("domain") or "unknown"
                st.markdown(f"- `{domain}`: {hit.get('title', 'Untitled result')}")
        if context_hits:
            st.caption("Accepted context hits")
            for hit in context_hits[:4]:
                domain = hit.get("domain") or "unknown"
                st.markdown(f"- `{domain}`: {hit.get('title', 'Untitled result')}")
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
        # Initialise Earpiece conversation state for continuity across messages
        if "fia_earpiece_conversation_id" not in st.session_state:
            st.session_state.fia_earpiece_conversation_id = None
            st.session_state.fia_earpiece_chat_id = None

    def instruction_messages(self) -> list:
        answer_language = st.session_state.get("fia_answer_language", "en")
        return [{"role": "system", "content": _system_prompt(answer_language)}]

    def get_relevant_info(self, query: str) -> str:
        """Plan search queries, execute, and return combined results as context string."""
        query_plan = _plan_query(query, self.messages_to_display)
        search_batches = query_plan["search_query_batches"]
        match_context = build_match_context_from_plan(query_plan, fallback_query=query)

        st.session_state.fia_answer_language = query_plan.get("answer_language", "en")

        with st.spinner(f"Searching {len(search_batches)} locale source set(s)..."):
            result = search_multi(search_batches, match_context=match_context)

        verified_match = result.get("verified_match")
        if should_retry_match_report(verified_match):
            retry_query = build_recent_match_retry_query(verified_match or match_context)
            if retry_query:
                with st.spinner("Verification failed — searching again with an exact-date query..."):
                    retry_batches = [
                        {
                            "locale": batch.get("locale", "en"),
                            "queries": (
                                [retry_query]
                                if batch.get("query_category") != "context_sentiment"
                                else batch.get("queries", [])
                            ),
                            "source_tier": batch.get("source_tier"),
                            "query_category": batch.get("query_category"),
                        }
                        for batch in search_batches
                    ]
                    retry_result = search_multi(retry_batches, match_context=match_context)
                search_batches = [
                    {
                        **batch,
                        "queries": (
                            [*batch.get("queries", []), retry_query]
                            if batch.get("query_category") != "context_sentiment"
                            else batch.get("queries", [])
                        ),
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
        st.session_state.fia_query_plan = query_plan
        st.session_state.fia_verified_match = verified_match
        st.session_state.fia_locale_attempts = result.get("locale_attempts", [])
        st.session_state.fia_winning_locale = result.get("primary_match_locale") or result.get("winning_locale")
        st.session_state.fia_source_tier = result.get("source_tier")
        data_narrative = st.session_state.get("fia_data_narrative", "").strip()
        relevant_info = build_search_context_payload(
            query_plan,
            result,
            data_narrative=data_narrative,
        )
        st.session_state.fia_search_context = relevant_info
        st.session_state.fia_raw_search_context = result.get("raw_answer", result["answer"])
        return relevant_info

    def get_input(self):
        if x := st.chat_input(
            placeholder="Ask about any football match..."
        ):
            self.handle_input(x)

    def handle_input(self, input, reasoning_effort=None, temperature=1, stream=False):
        # Reset stash (tool execution fills it during this method)
        st.session_state.fia_pending_citations = []
        st.session_state.fia_pending_provider = ""
        st.session_state.fia_search_queries = []
        st.session_state.fia_verified_match = None
        st.session_state.fia_locale_attempts = []
        st.session_state.fia_winning_locale = None
        st.session_state.fia_source_tier = None
        st.session_state.fia_answer_language = "en"
        st.session_state.fia_earpiece_response = None

        history_messages = _clean_messages_for_llm(self.messages_to_display.copy())

        # ------------------------------------------------------------------
        # Phase 1: Gather evidence — Earpiece first, then web search
        # ------------------------------------------------------------------
        tools = _get_tools_for_provider()
        earpiece_data = None
        relevant_info = None

        if tools is not None and TWELVE_EARPIECE_ENABLED:
            # --- Function-calling path (Azure / OpenAI) ---
            orch_messages = [
                {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT},
            ]
            for msg in history_messages[-6:]:
                if isinstance(msg.get("content"), str):
                    orch_messages.append({"role": msg["role"], "content": msg["content"][:300]})
            orch_messages.append({"role": "user", "content": f"```User: {input}```"})

            with st.spinner("Deciding which tools to call..."):
                orch_result = _call_llm_with_tools(orch_messages, tools)

            if orch_result["tool_calls"]:
                # _execute_tool_calls processes Earpiece FIRST, then search
                tool_results = _execute_tool_calls(
                    orch_result["tool_calls"], input, self.messages_to_display,
                )
                earpiece_data = tool_results.get("_earpiece_data")
                relevant_info = tool_results.get("_search_context")

                # If LLM only called Earpiece but not search, run search as fallback
                called_tools = {tc["name"] for tc in orch_result["tool_calls"]}
                if "search_internet" not in called_tools:
                    relevant_info = self.get_relevant_info(input)
            else:
                # LLM returned text without tool calls — call both directly
                # Earpiece FIRST so its data enriches search queries
                earpiece_data = _fetch_earpiece_direct(input)
                relevant_info = self.get_relevant_info(input)
        else:
            # --- No tool-calling support or Earpiece disabled ---
            # Earpiece FIRST (if enabled) so its data enriches search queries
            if TWELVE_EARPIECE_ENABLED and st.session_state.get("fia_earpiece_auto_fetch", True):
                earpiece_data = _fetch_earpiece_direct(input)
            relevant_info = self.get_relevant_info(input)

        self.messages_to_display.append({"role": "user", "content": input})

        citations = st.session_state.get("fia_pending_citations", [])
        provider = st.session_state.get("fia_pending_provider", "")
        search_qs = st.session_state.get("fia_search_queries", [])
        verified_match = st.session_state.get("fia_verified_match")
        locale_attempts = st.session_state.get("fia_locale_attempts", [])
        answer_language = st.session_state.get("fia_answer_language", "en")
        winning_locale = st.session_state.get("fia_winning_locale")
        source_tier = st.session_state.get("fia_source_tier")

        # ------------------------------------------------------------------
        # Phase 2: Evidence structuring + synthesis (existing pipeline)
        # ------------------------------------------------------------------
        eval_scores = None
        newspaper_data = None
        if not match_report_can_answer(verified_match):
            assistant_content = _localize_refusal_message(
                build_match_report_refusal(verified_match),
                answer_language,
            )
        else:
            llm_messages = self.instruction_messages() + history_messages
            data_narrative = st.session_state.get("fia_data_narrative", "").strip()
            has_data = bool(data_narrative) or bool(earpiece_data)
            with st.spinner("Structuring evidence..."):
                structured_evidence = _structure_evidence(
                    input,
                    relevant_info,
                    answer_language,
                    has_data_narrative=has_data,
                )
            llm_messages.append(
                {
                    "role": "user",
                    "content": build_synthesis_user_prompt(
                        answer_language,
                        relevant_info,
                        input,
                        evidence_summary=structured_evidence,
                        has_data_narrative=has_data,
                    ),
                }
            )
            st.expander("Chat transcript", expanded=False).write(
                _clean_messages_for_llm(llm_messages)
            )

            with st.spinner("Writing answer..."):
                assistant_content = _call_llm(llm_messages)

            newspaper_data = _parse_newspaper_block(assistant_content)
            assistant_content = strip_newspaper_block(assistant_content)
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
                "newspaper_data": newspaper_data,
                "earpiece_data": st.session_state.get("fia_earpiece_response"),
                "earpiece_conversation_id": st.session_state.get("fia_earpiece_conversation_id"),
                "earpiece_chat_id": st.session_state.get("fia_earpiece_chat_id"),
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
                        if message.get("newspaper_data"):
                            try:
                                st.image(
                                    render_newspaper_png(message["newspaper_data"]),
                                    caption="Newspaper front page",
                                    use_column_width=True,
                                )
                            except RuntimeError:
                                st.markdown(
                                    render_newspaper_html(message["newspaper_data"]),
                                    unsafe_allow_html=True,
                                )
                        if message.get("earpiece_data"):
                            with st.expander("Twelve Earpiece data"):
                                st.markdown(message["earpiece_data"][:2000])
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

with st.sidebar.expander("Twelve Earpiece API", expanded=False):
    st.session_state.fia_earpiece_auto_fetch = TWELVE_EARPIECE_ENABLED
    if TWELVE_EARPIECE_ENABLED:
        st.caption("Twelve Earpiece API is active. Data analysis will be fetched automatically.")
    else:
        st.caption("Twelve Earpiece API is not configured. Add credentials in secrets.toml to enable.")

    # Show latest Earpiece response if available
    latest_earpiece = st.session_state.get("fia_earpiece_response")
    if latest_earpiece:
        st.caption("Latest Earpiece response:")
        st.text(latest_earpiece[:500])

to_hash = ("internet_analyst",)
chat = create_chat(to_hash, InternetAnalystChat)

if chat.state == "empty":
    chat.add_message(
        "Welcome to the Full Internet Analyst. Ask me about any football match "
        "and I will search trusted local-language and English sources, then synthesise "
        "a match report in your language when the evidence is strong enough.",
        role="assistant",
    )
    chat.state = "default"

chat.get_input()
chat.display_messages()
chat.save_state()
