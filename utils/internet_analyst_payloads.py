"""Pure helpers for the Full Internet Analyst evidence pipeline."""

import json
import html as html_mod
import re
from io import BytesIO
from functools import lru_cache
from pathlib import Path

from utils.search import (
    QUERY_CATEGORIES,
    QUERY_CATEGORY_CONTEXT_SENTIMENT,
    QUERY_CATEGORY_MATCH_NARRATIVE,
    QUERY_CATEGORY_POST_MATCH_REACTION,
)

_STYLE_GUIDE_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "gpt_examples" / "MatchReportStyle.md"
)

QUERY_CATEGORY_LABELS = {
    QUERY_CATEGORY_MATCH_NARRATIVE: "Match narrative evidence",
    QUERY_CATEGORY_POST_MATCH_REACTION: "Post-match reaction evidence",
    QUERY_CATEGORY_CONTEXT_SENTIMENT: "Context & mood evidence",
}

EVALUATION_LABELS = [
    ("Narrative depth", "narrative_depth"),
    ("Source grounding", "source_grounding"),
    ("Source diversity", "source_diversity"),
    ("Context integration", "context_integration"),
    ("Unsupported-claim control", "unsupported_claim_risk"),
    ("Casa Pia style adherence", "style_adherence"),
    ("Data reconciliation", "data_reconciliation"),
]


def build_search_batch_caption(batch: dict) -> str:
    locale = batch.get("locale", "unknown")
    source_tier = batch.get("source_tier", "unknown")
    query_category = batch.get("query_category", QUERY_CATEGORY_MATCH_NARRATIVE)
    return f"{locale} [{source_tier}] [{query_category}]"


def format_verified_match_facts(verified_match: dict | None) -> str:
    if not verified_match:
        return "No structured match verification was available."

    verified_score = verified_match.get("verified_score") or "not verified"
    lines = [
        f"Teams: {verified_match.get('team_a', 'Unknown')} and {verified_match.get('team_b', 'Unknown')}",
        f"Requested date: {verified_match.get('requested_date_display', 'not resolved')}",
        f"Match identity verified: {'yes' if verified_match.get('match_identity_verified') else 'no'}",
        f"Score verified: {verified_score}",
        f"Narrative coverage available: {'yes' if verified_match.get('narrative_coverage_available') else 'no'}",
        f"Context coverage available: {'yes' if verified_match.get('context_coverage_available') else 'no'}",
        f"Searched locales: {', '.join(verified_match.get('searched_locales', [])) or 'not recorded'}",
        f"Primary match locale: {verified_match.get('primary_match_locale') or verified_match.get('winning_locale') or 'not selected'}",
        f"Source tier: {verified_match.get('source_tier') or 'not selected'}",
        f"Verified source language: {verified_match.get('verified_source_language') or 'not verified'}",
        "If the score is not verified above, do not state a scoreline.",
    ]
    return "\n".join(f"- {line}" for line in lines)


def _citation_index_lookup(citations: list[str]) -> dict[str, int]:
    return {url: idx for idx, url in enumerate(citations or [], 1) if url}


def format_evidence_blocks_for_prompt(
    evidence_blocks: dict[str, list[dict]] | None,
    citations: list[str] | None = None,
) -> str:
    evidence_blocks = evidence_blocks or {}
    citation_lookup = _citation_index_lookup(citations or [])
    sections = []
    for query_category in QUERY_CATEGORIES:
        hits = evidence_blocks.get(query_category, [])
        section = [f"--- {QUERY_CATEGORY_LABELS[query_category]} ---"]
        if not hits:
            section.append("No evidence found.")
            sections.append("\n".join(section))
            continue
        for hit in hits:
            title = hit.get("title", "Untitled result")
            body = hit.get("body", "")
            href = hit.get("href", "")
            domain = hit.get("domain") or "unknown"
            locale = hit.get("locale") or ""
            citation_idx = citation_lookup.get(href)
            ref = f"[{citation_idx}]" if citation_idx else ""
            locale_tag = f" ({locale})" if locale else ""
            header = f"{ref} {domain}{locale_tag}: {title}".strip()
            section.append(header)
            if body:
                section.append(body)
            section.append("")
        sections.append("\n".join(section))
    # Append source summary so the LLM knows how many distinct sources it has
    total_hits = sum(len(hits) for hits in (evidence_blocks or {}).values())
    unique_domains = sorted({
        hit.get("domain")
        for hits in (evidence_blocks or {}).values()
        for hit in hits
        if hit.get("domain")
    })
    if unique_domains:
        sections.append(
            f"--- Source summary ---\n"
            f"Total evidence items: {total_hits}\n"
            f"Unique source domains: {len(unique_domains)} ({', '.join(unique_domains)})"
        )
    return "\n\n".join(sections)


def build_search_context_payload(
    query_plan: dict,
    search_result: dict,
    data_narrative: str = "",
) -> str:
    verified_match = search_result.get("verified_match")
    evidence_blocks = search_result.get("evidence_blocks", {})
    citations = search_result.get("citations", [])
    verified_facts_block = ""
    if verified_match:
        verified_facts_block = (
            f"--- Verified match facts ---\n{format_verified_match_facts(verified_match)}\n\n"
        )
    plan_block = (
        "--- Query plan ---\n"
        f"- Answer language: {query_plan.get('answer_language', 'en')}\n"
        f"- Search locales: {', '.join(query_plan.get('search_locales', [])) or 'not set'}\n"
        f"- Primary match locale: {search_result.get('primary_match_locale') or search_result.get('winning_locale') or 'not selected'}\n"
        f"- Source tier: {search_result.get('source_tier') or 'not selected'}\n\n"
    )
    data_block = ""
    if data_narrative:
        data_block = f"--- Twelve data analysis (provided by user) ---\n{data_narrative}\n\n"
    evidence_block = format_evidence_blocks_for_prompt(evidence_blocks, citations=citations)
    return (
        f"{plan_block}"
        f"{verified_facts_block}"
        f"{data_block}"
        f"{evidence_block}"
    )


def _extract_markdown_section(text: str, start_heading: str, end_heading: str | None = None) -> str:
    start = text.find(start_heading)
    if start == -1:
        return ""
    end = text.find(end_heading, start) if end_heading else len(text)
    if end == -1:
        end = len(text)
    return text[start:end].strip()


@lru_cache(maxsize=1)
def _load_match_report_style_reference() -> str:
    try:
        raw = _STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""

    example_one = _extract_markdown_section(
        raw,
        "## Example 1: Casa Pia AC vs FC Porto (Primeira Liga)",
        "## Example 2",
    )
    example_two = _extract_markdown_section(
        raw,
        "## Example 2: Atletico Madrid vs FC Barcelona (UEFA Champions League QF)",
        "## Style Rules Summary",
    )
    summary = _extract_markdown_section(raw, "## Style Rules Summary")
    chosen = "\n\n".join(part for part in (example_one, example_two, summary) if part)
    return chosen.strip()


def _serialise_for_prompt(payload: dict | None) -> str:
    if payload is None:
        return "{}"
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_structuring_user_prompt(
    answer_language: str,
    user_query: str,
    relevant_info: str,
    has_data_narrative: bool = False,
) -> str:
    data_instruction = (
        "Classify the relationship between the Twelve data narrative "
        "and the web evidence as `supported`, `contradicted`, `mixed`, "
        "or `insufficient evidence`."
        if has_data_narrative
        else "If no Twelve data narrative is present, "
        "set `data_vs_web.relationship` to null."
    )
    return (
        f"Extract structured evidence for a football match report "
        f"in language `{answer_language}`.\n\n"
        f"User question:\n{user_query}\n\n"
        f"Evidence context:\n{relevant_info}\n\n"
        f"INSTRUCTIONS:\n"
        f"- Extract every key match event with minute if available\n"
        f"- Capture specific tactical observations from the sources\n"
        f"- Extract individual player observations with source attribution\n"
        f"- Capture journalist verdicts as opinions, not facts\n"
        f"- Produce writer-ready sections named `match_story`, `table_impact`, `opponent_story`, "
        f"`coach_pressure`, `institutional_response`, `strategic_ripple`, `surprise_factor`, "
        f"`press_consensus`, and `hard_gaps`\n"
        f"- `match_story` must be short and vivid because the final report opens with it\n"
        f"- Only include standings math or counterfactuals when the raw evidence gives the numbers needed\n"
        f"- Use empty strings or empty lists for unsupported layers instead of guessing\n"
        f"- For each writer-ready section, note which source citations support it in parentheses\n"
        f"- `hard_gaps` MUST list every narrative layer that has ZERO supporting evidence from "
        f"this list: match_story, table_impact, opponent_story, coach_pressure, "
        f"institutional_response, strategic_ripple, surprise_factor, press_consensus\n"
        f"- {data_instruction}"
    )


def build_synthesis_user_prompt(
    answer_language: str,
    relevant_info: str,
    user_input: str,
    evidence_summary: dict | None = None,
    has_data_narrative: bool = False,
) -> str:
    style_reference = _load_match_report_style_reference()
    style_block = ""
    if style_reference:
        style_block = (
            "--- Repository style exemplar (follow structure and tone, never copy its facts) ---\n"
            f"{style_reference}\n\n"
        )

    summary_block = ""
    synthesis_guidance = ""
    if evidence_summary:
        summary_block = (
            "--- Structured evidence summary ---\n"
            f"{_serialise_for_prompt(evidence_summary)}\n\n"
        )
        synthesis_guidance = (
            "--- How to use the structured summary ---\n"
            "- `match_story` is the opening section and must stay SHORT: one or two paragraphs maximum\n"
            "- Use `table_impact` for the standings and points scenarios only when the evidence states them\n"
            "- Use `opponent_story` so the smaller side's consequence is not lost\n"
            "- Use `coach_pressure` and `institutional_response` only when sources truly support them\n"
            "- Use `strategic_ripple` for the counterfactual and upcoming-fixture logic\n"
            "- Use `surprise_factor` for why the result mattered emotionally or contextually\n"
            "- Use `press_consensus` and `journalist_verdicts` for attributed judgments and quotes\n"
            "- Treat `hard_gaps` as RED LINES: do not infer or embellish anything listed there\n"
            "- If `source_conflicts` exist, present both sides with attribution\n\n"
        )

    data_instruction = (
        "If the evidence contains Twelve data analysis, include a `Data vs internet` section only when the web evidence genuinely supports that comparison."
        if has_data_narrative
        else "Do not invent a `Data vs internet` section when no Twelve data analysis is present."
    )

    return (
        f"Write a match report in language `{answer_language}`.\n\n"
        f"--- Raw evidence ---\n{relevant_info}\n\n"
        f"{summary_block}"
        f"{style_block}"
        "--- Output contract ---\n"
        "- Follow the style exemplar closely: write a CONTINUOUS FLOWING NARRATIVE with NO section headers, NO bold labels, NO bullet points\n"
        "- DO NOT use headers like '**How it played out**', '**Both sides**', '**Bottom line**' — weave all layers into seamless prose paragraphs\n"
        "- Open with 1-2 paragraphs on the match itself: specific scorers, minutes, key moments, red cards, tactical detail\n"
        "- Transition naturally (e.g. 'The story of this match goes far beyond the scoreline') then expand into consequences\n"
        "- Cover the winner's perspective and what the result means for them, fan and social media reaction woven into prose, the loser's perspective and what they face next\n"
        "- When a red card or controversy occurred, include a fair-play assessment and how neutral observers viewed it\n"
        "- Close with a paragraph tying everything together — match + consequences + what changes for both clubs\n"
        "- Every paragraph must be grounded in cited web evidence or arithmetic directly derivable from numbers stated in the evidence\n"
        "- Cite at least 3 different sources across the report; vary citation numbers per paragraph — do NOT rely on a single source\n"
        "- When two or more sources confirm the same fact, cite them together: [1][3]\n"
        "- Do not invent quotes, standings scenarios, board reactions, or pressure narratives\n"
        "- Attribute judgments and quotes to outlets or speakers with citations\n"
        "- If evidence is thin, write a shorter answer instead of filling space\n\n"
        "--- json_newspaper contract ---\n"
        "- After the closing paragraph, append a fenced `json_newspaper` block that reflects the report exactly\n"
        "- Include `newspaper_style`: use `broadsheet` for a serious newspaper front page, or `tabloid` only for unusually dramatic shocks, controversies, or title swings\n"
        "- Do not use real newspaper names, logos, or mastheads; the style can be inspired by broadsheet/tabloid conventions without impersonating a publication\n"
        "- Prefer the richer front-page fields: `masthead`, `edition_line`, `kicker`, `standfirst`, `key_numbers`, `pull_quote`, `why_it_matters`, `coach_watch`, `opponent_angle`, and `verdict`\n"
        "- Legacy fields (`left_column`, `right_column`, `bottom_left`, `bottom_right`, `footer`) remain allowed, but richer front-page fields are preferred\n"
        "- Use empty strings or empty lists for unsupported front-page elements; never invent copy just to fill the design\n\n"
        f"{synthesis_guidance}"
        f"{data_instruction}\n\n"
        f"```User: {user_input}```"
    )


# ---------------------------------------------------------------------------
# Newspaper front-page HTML renderer
# ---------------------------------------------------------------------------

_NEWSPAPER_CSS = """
.newspaper-frontpage {
  --paper-bg: #fbfaf6;
  --paper-panel: #ffffff;
  --ink: #171717;
  --muted: #626262;
  --rule: #1f1f1f;
  --hairline: rgba(31, 31, 31, 0.22);
  --accent: #0b6b5f;
  --accent-soft: #e4f0ed;
  --accent-contrast: #ffffff;
  --masthead-font: Georgia, 'Times New Roman', serif;
  --headline-font: Georgia, 'Times New Roman', serif;
  --label-font: Arial, Helvetica, sans-serif;
  font-family: Georgia, 'Times New Roman', serif;
  max-width: 960px;
  margin: 1.5rem auto;
  background: var(--paper-bg);
  color: var(--ink);
  border: 1px solid var(--rule);
  box-shadow: 0 14px 34px rgba(17, 17, 17, 0.16);
}
.newspaper-frontpage--tabloid {
  --paper-bg: #fff8ec;
  --paper-panel: #fffdfa;
  --ink: #120f0c;
  --muted: #6a5141;
  --rule: #18110c;
  --hairline: rgba(24, 17, 12, 0.26);
  --accent: #c2261d;
  --accent-soft: #ffe4d4;
  --accent-contrast: #fff8ec;
  --masthead-font: Impact, Haettenschweiler, 'Arial Narrow Bold', sans-serif;
  --headline-font: Impact, Haettenschweiler, 'Arial Narrow Bold', sans-serif;
  max-width: 880px;
}
.newspaper-masthead-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 1rem;
  padding: 0.9rem 1.25rem 0.75rem;
  border-top: 6px solid var(--rule);
  border-bottom: 1px solid var(--rule);
}
.newspaper-frontpage--broadsheet .newspaper-masthead-row {
  text-align: center;
  grid-template-columns: 1fr;
  gap: 0.25rem;
}
.newspaper-frontpage--tabloid .newspaper-masthead-row {
  background: var(--rule);
  color: var(--accent-contrast);
  border-bottom: 6px solid var(--accent);
}
.newspaper-masthead {
  font-family: var(--masthead-font);
  font-size: 3rem;
  line-height: 0.95;
  margin: 0;
}
.newspaper-frontpage--broadsheet .newspaper-masthead {
  font-weight: 700;
}
.newspaper-frontpage--tabloid .newspaper-masthead {
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.newspaper-edition {
  margin: 0;
  font-family: var(--label-font);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--muted);
}
.newspaper-frontpage--tabloid .newspaper-edition {
  color: #f4cfbc;
}
.newspaper-score-strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 1rem;
  align-items: center;
  padding: 0.8rem 1.25rem;
  border-bottom: 1px solid var(--rule);
}
.newspaper-frontpage--tabloid .newspaper-score-strip {
  background: var(--accent);
  color: var(--accent-contrast);
  border-bottom: 4px solid var(--rule);
}
.newspaper-score-side {
  min-width: 0;
}
.newspaper-score-side--away {
  text-align: right;
}
.newspaper-score-label {
  display: block;
  margin-bottom: 0.15rem;
  font-family: var(--label-font);
  font-size: 0.67rem;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: var(--muted);
}
.newspaper-frontpage--tabloid .newspaper-score-label {
  color: #ffe1d1;
}
.newspaper-score-team {
  display: block;
  font-size: 1.2rem;
  font-weight: 700;
  line-height: 1.15;
}
.newspaper-score-center {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 0.55rem;
  min-width: 126px;
}
.newspaper-score-number {
  font-family: var(--headline-font);
  font-size: 2.75rem;
  font-weight: 800;
  line-height: 0.95;
}
.newspaper-score-divider {
  font-size: 1.25rem;
  color: var(--muted);
}
.newspaper-frontpage--tabloid .newspaper-score-divider {
  color: #ffe1d1;
}
.newspaper-score-meta {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.55rem 1.25rem 0.65rem;
  border-bottom: 1px solid var(--hairline);
  font-family: var(--label-font);
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}
.newspaper-hero {
  padding: 1.15rem 1.25rem 1.25rem;
  border-bottom: 3px double var(--rule);
}
.newspaper-kicker {
  display: inline-block;
  margin: 0 0 0.55rem;
  padding-bottom: 0.15rem;
  border-bottom: 3px solid var(--accent);
  font-family: var(--label-font);
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.17em;
  color: var(--accent);
}
.newspaper-headline {
  margin: 0;
  font-family: var(--headline-font);
  font-size: 3.45rem;
  font-weight: 800;
  line-height: 0.98;
}
.newspaper-frontpage--tabloid .newspaper-headline {
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.newspaper-subheadline {
  margin: 0.55rem 0 0;
  font-family: var(--label-font);
  font-size: 0.92rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--muted);
}
.newspaper-standfirst {
  margin: 0.75rem 0 0;
  max-width: 52rem;
  font-size: 1.05rem;
  line-height: 1.55;
}
.newspaper-keynumbers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0;
  padding: 0;
  border-bottom: 1px solid var(--rule);
}
.newspaper-keynumber {
  min-width: 0;
  padding: 0.85rem 1.1rem 0.8rem;
  background: var(--paper-panel);
  border-right: 1px solid var(--hairline);
}
.newspaper-keynumber:last-child {
  border-right: 0;
}
.newspaper-frontpage--tabloid .newspaper-keynumber {
  background: var(--accent-soft);
}
.newspaper-keynumber-value {
  display: block;
  font-family: var(--headline-font);
  font-size: 1.85rem;
  font-weight: 800;
  line-height: 0.95;
}
.newspaper-keynumber-label {
  display: block;
  margin-top: 0.25rem;
  font-family: var(--label-font);
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--accent);
}
.newspaper-keynumber-context {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.9rem;
  line-height: 1.35;
}
.newspaper-body {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(260px, 0.95fr);
  gap: 0;
}
.newspaper-main {
  border-right: 1px solid var(--hairline);
}
.newspaper-main,
.newspaper-sidebar {
  padding: 0;
}
.newspaper-panel {
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--hairline);
}
.newspaper-panel--lead {
  background: var(--paper-panel);
}
.newspaper-panel--muted {
  background: rgba(0, 0, 0, 0.03);
}
.newspaper-panel-title {
  margin: 0 0 0.65rem;
  font-family: var(--label-font);
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--accent);
}
.newspaper-frontpage--tabloid .newspaper-panel-title {
  font-family: var(--headline-font);
  font-size: 1.05rem;
  letter-spacing: 0.05em;
  color: var(--ink);
}
.newspaper-panel-items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.newspaper-panel-items li {
  margin: 0 0 0.7rem;
  font-size: 0.98rem;
  line-height: 1.52;
}
.newspaper-panel-items li:last-child {
  margin-bottom: 0;
}
.newspaper-quote-card {
  margin: 1rem 1rem 0;
  padding: 1rem 1rem 0.95rem;
  background: var(--paper-panel);
  color: var(--ink);
  border-top: 5px solid var(--accent);
  border-bottom: 1px solid var(--hairline);
}
.newspaper-frontpage--tabloid .newspaper-quote-card {
  background: var(--rule);
  color: var(--accent-contrast);
  border-top: 0;
}
.newspaper-quote-kicker {
  margin: 0 0 0.55rem;
  font-family: var(--label-font);
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--accent);
}
.newspaper-frontpage--tabloid .newspaper-quote-kicker {
  color: #f4cfbc;
}
.newspaper-quote-card blockquote {
  margin: 0;
  font-size: 1.16rem;
  line-height: 1.48;
  font-style: italic;
}
.newspaper-quote-attribution {
  margin: 0.7rem 0 0;
  font-family: var(--label-font);
  font-size: 0.74rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}
.newspaper-frontpage--tabloid .newspaper-quote-attribution {
  color: #f4cfbc;
}
.newspaper-bottom-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  border-top: 1px solid var(--hairline);
}
.newspaper-bottom-grid .newspaper-panel:first-child {
  border-right: 1px solid var(--hairline);
}
.newspaper-footer-note {
  padding: 0.8rem 1.25rem 0.9rem;
  border-top: 1px solid var(--hairline);
  font-size: 0.92rem;
  line-height: 1.45;
}
.newspaper-verdict-strip {
  padding: 0.9rem 1.25rem 1rem;
  background: var(--paper-panel);
  color: var(--ink);
  border-top: 4px solid var(--rule);
}
.newspaper-frontpage--tabloid .newspaper-verdict-strip {
  background: var(--rule);
  color: var(--accent-contrast);
  border-top: 5px solid var(--accent);
}
.newspaper-verdict-label {
  margin: 0 0 0.35rem;
  font-family: var(--label-font);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: var(--accent);
}
.newspaper-frontpage--tabloid .newspaper-verdict-label {
  color: #f4cfbc;
}
.newspaper-verdict-text {
  margin: 0;
  font-size: 1.02rem;
  line-height: 1.55;
  font-weight: 700;
}
@media (max-width: 720px) {
  .newspaper-frontpage {
    margin: 1rem auto;
  }
  .newspaper-masthead-row,
  .newspaper-score-meta,
  .newspaper-score-strip {
    grid-template-columns: 1fr;
  }
  .newspaper-masthead-row,
  .newspaper-score-meta {
    display: block;
  }
  .newspaper-masthead {
    font-size: 2.35rem;
  }
  .newspaper-headline {
    font-size: 2.35rem;
  }
  .newspaper-edition {
    margin-top: 0.4rem;
  }
  .newspaper-score-strip {
    gap: 0.6rem;
  }
  .newspaper-score-side,
  .newspaper-score-side--away {
    text-align: left;
  }
  .newspaper-score-center {
    justify-content: flex-start;
  }
  .newspaper-body,
  .newspaper-bottom-grid {
    grid-template-columns: 1fr;
  }
  .newspaper-main {
    border-right: 0;
  }
  .newspaper-bottom-grid .newspaper-panel:first-child {
    border-right: 0;
  }
  .newspaper-keynumber,
  .newspaper-keynumber:last-child {
    border-right: 0;
    border-bottom: 1px solid var(--hairline);
  }
  .newspaper-quote-card {
    margin: 0;
    border-top: 1px solid var(--hairline);
  }
}
"""


def _esc(text: str) -> str:
    return html_mod.escape(text) if text else ""


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_non_empty(*values) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _normalise_text_list(items) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, list):
        items = [items]
    return [text for item in items if (text := _clean_text(item))]


def _normalise_panel(panel, fallback_title: str = "") -> dict:
    if isinstance(panel, dict):
        title = _first_non_empty(panel.get("title"), fallback_title)
        items = _normalise_text_list(panel.get("items", []))
    elif panel:
        title = _clean_text(fallback_title)
        items = _normalise_text_list(panel)
    else:
        title = _clean_text(fallback_title)
        items = []
    return {"title": title, "items": items}


def _normalise_key_numbers(items) -> list[dict]:
    cards = []
    for item in items or []:
        if isinstance(item, dict):
            value = _clean_text(item.get("value"))
            label = _clean_text(item.get("label"))
            context = _clean_text(item.get("context"))
        else:
            value = ""
            label = _clean_text(item)
            context = ""
        if value or label or context:
            cards.append({"value": value, "label": label, "context": context})
    return cards


def _normalise_pull_quote(value) -> dict:
    if isinstance(value, dict):
        return {
            "quote": _first_non_empty(value.get("quote"), value.get("text")),
            "attribution": _first_non_empty(value.get("attribution"), value.get("source")),
        }
    if value:
        return {"quote": _clean_text(value), "attribution": ""}
    return {"quote": "", "attribution": ""}


def _normalise_newspaper_style(value) -> str:
    text = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    if text in {"tabloid", "daily_news", "dailynews", "daily_news_inspired", "sports_tabloid"}:
        return "tabloid"
    if text in {
        "broadsheet",
        "guardian",
        "guardian_style",
        "guardian_inspired",
        "serious",
        "serious_newspaper",
    }:
        return "broadsheet"
    return "broadsheet"


def _panel_has_content(panel: dict) -> bool:
    return bool(panel.get("title") or panel.get("items"))


def _normalise_newspaper_payload(data: dict) -> dict:
    legacy_left = _normalise_panel(data.get("left_column"), "WHY IT MATTERS")
    legacy_right = _normalise_panel(data.get("right_column"), "WHAT THE PRESS SAID")
    legacy_bottom_left = _normalise_panel(data.get("bottom_left"), "COACH WATCH")
    legacy_bottom_right = _normalise_panel(data.get("bottom_right"), "OPPONENT ANGLE")
    legacy_footer = _normalise_panel(data.get("footer"))

    press_reaction = _normalise_panel(
        data.get("press_reaction") or data.get("right_column"),
        "WHAT THE PRESS SAID",
    )
    pull_quote = _normalise_pull_quote(data.get("pull_quote"))
    if not pull_quote["quote"] and press_reaction.get("items"):
        pull_quote = {
            "quote": press_reaction["items"][0],
            "attribution": press_reaction.get("title", ""),
        }
        if len(press_reaction["items"]) > 1:
            press_reaction = {
                "title": press_reaction.get("title", ""),
                "items": press_reaction["items"][1:],
            }
        else:
            press_reaction = {"title": press_reaction.get("title", ""), "items": []}

    why_it_matters = _normalise_panel(
        data.get("why_it_matters") or data.get("left_column"),
        "WHY IT MATTERS",
    )
    coach_watch = _normalise_panel(
        data.get("coach_watch") or data.get("bottom_left"),
        "COACH WATCH",
    )
    opponent_angle = _normalise_panel(
        data.get("opponent_angle") or data.get("bottom_right") or data.get("footer"),
        "OPPONENT ANGLE",
    )

    footer_panel = legacy_footer
    if footer_panel == opponent_angle:
        footer_panel = {"title": "", "items": []}

    return {
        "newspaper_style": _normalise_newspaper_style(
            data.get("newspaper_style") or data.get("style") or data.get("template")
        ),
        "masthead": _first_non_empty(data.get("masthead"), "Twelve Sport"),
        "edition_line": _first_non_empty(
            data.get("edition_line"),
            data.get("competition"),
            "Matchday Front Page",
        ),
        "competition": _first_non_empty(data.get("competition"), "MATCHDAY REPORT"),
        "team_home": _clean_text(data.get("team_home")),
        "team_away": _clean_text(data.get("team_away")),
        "score_home": _clean_text(data.get("score_home")),
        "score_away": _clean_text(data.get("score_away")),
        "venue": _clean_text(data.get("venue")),
        "kicker": _first_non_empty(data.get("kicker"), data.get("competition"), "Matchday"),
        "headline": _first_non_empty(data.get("headline"), data.get("subheadline"), "Matchday Report"),
        "subheadline": _clean_text(data.get("subheadline")),
        "standfirst": _first_non_empty(data.get("standfirst"), data.get("subheadline")),
        "key_numbers": _normalise_key_numbers(data.get("key_numbers", [])),
        "pull_quote": pull_quote,
        "press_reaction": press_reaction if _panel_has_content(press_reaction) else legacy_right,
        "why_it_matters": why_it_matters if _panel_has_content(why_it_matters) else legacy_left,
        "coach_watch": coach_watch if _panel_has_content(coach_watch) else legacy_bottom_left,
        "opponent_angle": opponent_angle if _panel_has_content(opponent_angle) else legacy_bottom_right,
        "footer": footer_panel,
        "verdict": _clean_text(data.get("verdict")),
    }


def _parse_newspaper_block(text: str) -> dict | None:
    """Extract a JSON newspaper block fenced by ```json_newspaper ... ```."""
    pattern = r"```json_newspaper\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return None


def strip_newspaper_block(text: str) -> str:
    """Remove the json_newspaper fenced block from the answer text."""
    return re.sub(r"\s*```json_newspaper\s*\n.*?```", "", text, flags=re.DOTALL).rstrip()


def _render_key_numbers(cards: list[dict]) -> str:
    if not cards:
        return ""
    parts = ['<div class="newspaper-keynumbers">']
    for card in cards:
        value = _esc(card.get("value", ""))
        label = _esc(card.get("label", ""))
        context = _esc(card.get("context", ""))
        parts.append('<div class="newspaper-keynumber">')
        if value:
            parts.append(f'<span class="newspaper-keynumber-value">{value}</span>')
        if label:
            parts.append(f'<span class="newspaper-keynumber-label">{label}</span>')
        if context:
            parts.append(f'<span class="newspaper-keynumber-context">{context}</span>')
        parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)


def _render_panel(panel: dict, extra_class: str = "") -> str:
    if not _panel_has_content(panel):
        return ""
    title = _esc(panel.get("title", ""))
    items = panel.get("items", [])
    classes = "newspaper-panel"
    if extra_class:
        classes = f"{classes} {extra_class}"
    parts = [f'<section class="{classes}">']
    if title:
        parts.append(f'<p class="newspaper-panel-title">{title}</p>')
    if items:
        parts.append('<ul class="newspaper-panel-items">')
        for item in items:
            parts.append(f"<li>{_esc(item)}</li>")
        parts.append("</ul>")
    parts.append("</section>")
    return "\n".join(parts)


def _render_quote_card(quote: dict) -> str:
    if not quote.get("quote"):
        return ""
    attribution = _esc(quote.get("attribution", ""))
    parts = [
        '<aside class="newspaper-quote-card">',
        '<p class="newspaper-quote-kicker">Front-page quote</p>',
        f'<blockquote>"{_esc(quote.get("quote", ""))}"</blockquote>',
    ]
    if attribution:
        parts.append(f'<p class="newspaper-quote-attribution">{attribution}</p>')
    parts.append("</aside>")
    return "\n".join(parts)


def render_newspaper_html(data: dict) -> str:
    """Build a styled sports newspaper front page from structured data."""
    payload = _normalise_newspaper_payload(data or {})
    style_class = f'newspaper-frontpage--{payload["newspaper_style"]}'
    key_numbers_html = _render_key_numbers(payload.get("key_numbers", []))
    quote_html = _render_quote_card(payload.get("pull_quote", {}))
    why_it_matters_html = _render_panel(payload.get("why_it_matters", {}), "newspaper-panel--lead")
    press_reaction_html = _render_panel(payload.get("press_reaction", {}))
    coach_watch_html = _render_panel(payload.get("coach_watch", {}))
    opponent_angle_html = _render_panel(payload.get("opponent_angle", {}))
    footer_html = _render_panel(payload.get("footer", {}), "newspaper-panel--muted")

    hero_deck = []
    if payload.get("subheadline") and payload.get("subheadline") != payload.get("standfirst"):
        hero_deck.append(f'<p class="newspaper-subheadline">{_esc(payload["subheadline"])}</p>')
    if payload.get("standfirst"):
        hero_deck.append(f'<p class="newspaper-standfirst">{_esc(payload["standfirst"])}</p>')
    hero_deck_html = "\n".join(hero_deck)

    return f"""<style>{_NEWSPAPER_CSS}</style>
<section class="newspaper-frontpage {style_class}">
  <div class="newspaper-masthead-row">
    <p class="newspaper-masthead">{_esc(payload["masthead"])}</p>
    <p class="newspaper-edition">{_esc(payload["edition_line"])}</p>
  </div>
  <div class="newspaper-score-strip">
    <div class="newspaper-score-side">
      <span class="newspaper-score-label">Home</span>
      <span class="newspaper-score-team">{_esc(payload["team_home"])}</span>
    </div>
    <div class="newspaper-score-center">
      <span class="newspaper-score-number">{_esc(payload["score_home"])}</span>
      <span class="newspaper-score-divider">-</span>
      <span class="newspaper-score-number">{_esc(payload["score_away"])}</span>
    </div>
    <div class="newspaper-score-side newspaper-score-side--away">
      <span class="newspaper-score-label">Away</span>
      <span class="newspaper-score-team">{_esc(payload["team_away"])}</span>
    </div>
  </div>
  <div class="newspaper-score-meta">
    <span>{_esc(payload["competition"])}</span>
    <span>{_esc(payload["venue"])}</span>
  </div>
  <div class="newspaper-hero">
    <p class="newspaper-kicker">{_esc(payload["kicker"])}</p>
    <p class="newspaper-headline">{_esc(payload["headline"])}</p>
    {hero_deck_html}
  </div>
  {key_numbers_html}
  <div class="newspaper-body">
    <div class="newspaper-main">
      {why_it_matters_html}
      {footer_html}
    </div>
    <div class="newspaper-sidebar">
      {quote_html}
      {press_reaction_html}
    </div>
  </div>
  <div class="newspaper-bottom-grid">
    {coach_watch_html}
    {opponent_angle_html}
  </div>
  <div class="newspaper-verdict-strip">
    <p class="newspaper-verdict-label">Bottom line</p>
    <p class="newspaper-verdict-text">{_esc(payload["verdict"])}</p>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Newspaper PNG renderer
# ---------------------------------------------------------------------------

def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to render the newspaper PNG.") from exc
    return Image, ImageDraw, ImageFont


def _font_candidates(face: str) -> list[str]:
    windows = Path("C:/Windows/Fonts")
    linux = Path("/usr/share/fonts/truetype/dejavu")
    return {
        "serif": [
            str(windows / "georgia.ttf"),
            str(linux / "DejaVuSerif.ttf"),
            "Georgia.ttf",
            "DejaVuSerif.ttf",
        ],
        "serif_bold": [
            str(windows / "georgiab.ttf"),
            str(linux / "DejaVuSerif-Bold.ttf"),
            "Georgia Bold.ttf",
            "DejaVuSerif-Bold.ttf",
        ],
        "serif_italic": [
            str(windows / "georgiai.ttf"),
            str(linux / "DejaVuSerif-Italic.ttf"),
            "Georgia Italic.ttf",
            "DejaVuSerif-Italic.ttf",
        ],
        "sans": [
            str(windows / "arial.ttf"),
            str(linux / "DejaVuSans.ttf"),
            "Arial.ttf",
            "DejaVuSans.ttf",
        ],
        "sans_bold": [
            str(windows / "arialbd.ttf"),
            str(linux / "DejaVuSans-Bold.ttf"),
            "Arial Bold.ttf",
            "DejaVuSans-Bold.ttf",
        ],
        "display": [
            str(windows / "impact.ttf"),
            str(linux / "DejaVuSansCondensed-Bold.ttf"),
            "Impact.ttf",
            "DejaVuSansCondensed-Bold.ttf",
        ],
    }.get(face, [])


@lru_cache(maxsize=128)
def _newspaper_font(face: str, size: int):
    _, _, ImageFont = _load_pillow()
    for candidate in _font_candidates(face):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _shift_rgb(rgb: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(max(0, min(255, channel + amount)) for channel in rgb)


def _make_paper(width: int, height: int, base_hex: str):
    Image, ImageDraw, _ = _load_pillow()
    base = _hex_to_rgb(base_hex)
    image = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(image)
    for i in range(5200):
        x = (i * 37) % width
        y = (i * 91) % height
        shade = ((i * 19) % 9) - 4
        draw.point((x, y), fill=_shift_rgb(base, shade))
    return image


def _text_size(draw, text: str, font) -> tuple[int, int]:
    if not text:
        return 0, 0
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _font_height(font) -> int:
    bbox = font.getbbox("Ag")
    return bbox[3] - bbox[1]


def _truncate_to_width(draw, text: str, font, max_width: int) -> str:
    if _text_size(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    while text and _text_size(draw, f"{text}{suffix}", font)[0] > max_width:
        text = text[:-1].rstrip()
    return f"{text}{suffix}" if text else suffix


def _wrap_text(draw, text: str, font, max_width: int, max_lines: int | None = None) -> list[str]:
    words = _clean_text(text).split()
    if not words:
        return []
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if _text_size(draw, candidate, font)[0] <= max_width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = word
        if _text_size(draw, line, font)[0] > max_width:
            line = _truncate_to_width(draw, line, font, max_width)
    if line:
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _truncate_to_width(draw, lines[-1], font, max_width)
    return lines


def _fit_wrapped_font(
    draw,
    text: str,
    face: str,
    max_size: int,
    min_size: int,
    max_width: int,
    max_lines: int,
):
    for size in range(max_size, min_size - 1, -4):
        font = _newspaper_font(face, size)
        lines = _wrap_text(draw, text, font, max_width, max_lines=max_lines)
        if len(lines) <= max_lines:
            return font, lines
    font = _newspaper_font(face, min_size)
    return font, _wrap_text(draw, text, font, max_width, max_lines=max_lines)


def _draw_wrapped(
    draw,
    text: str,
    x: int,
    y: int,
    max_width: int,
    font,
    fill: str,
    line_gap: int = 8,
    max_lines: int | None = None,
) -> int:
    for line in _wrap_text(draw, text, font, max_width, max_lines=max_lines):
        draw.text((x, y), line, font=font, fill=fill)
        y += _font_height(font) + line_gap
    return y


def _draw_centered(draw, text: str, y: int, font, fill: str, width: int) -> int:
    text_width, text_height = _text_size(draw, text, font)
    draw.text(((width - text_width) // 2, y), text, font=font, fill=fill)
    return y + text_height


def _panel_height(draw, panel: dict, width: int, title_font, body_font, max_items: int = 4) -> int:
    if not _panel_has_content(panel):
        return 0
    height = 30
    title = panel.get("title", "")
    if title:
        height += _font_height(title_font) + 20
    for item in panel.get("items", [])[:max_items]:
        height += len(_wrap_text(draw, item, body_font, width - 34, max_lines=3)) * (
            _font_height(body_font) + 7
        )
        height += 10
    return height + 8


def _draw_panel(
    draw,
    panel: dict,
    x: int,
    y: int,
    width: int,
    palette: dict,
    title_font,
    body_font,
    max_items: int = 4,
    fill: str | None = None,
) -> int:
    if not _panel_has_content(panel):
        return y
    height = _panel_height(draw, panel, width, title_font, body_font, max_items=max_items)
    draw.rectangle((x, y, x + width, y + height), fill=fill or palette["panel"], outline=palette["hairline"])
    cursor = y + 16
    title = panel.get("title", "")
    if title:
        draw.text((x + 17, cursor), title.upper(), font=title_font, fill=palette["accent"])
        cursor += _font_height(title_font) + 18
    for item in panel.get("items", [])[:max_items]:
        cursor = _draw_wrapped(
            draw,
            item,
            x + 17,
            cursor,
            width - 34,
            body_font,
            palette["ink"],
            line_gap=7,
            max_lines=3,
        )
        cursor += 10
    return y + height + 18


def _draw_key_numbers(draw, cards: list[dict], x: int, y: int, width: int, palette: dict) -> int:
    if not cards:
        return y
    cards = cards[:3]
    gap = 0
    card_width = (width - gap * (len(cards) - 1)) // len(cards)
    height = 148
    value_font = _newspaper_font("serif_bold", 42)
    label_font = _newspaper_font("sans_bold", 17)
    context_font = _newspaper_font("serif", 24)
    for index, card in enumerate(cards):
        cell_x = x + index * (card_width + gap)
        draw.rectangle(
            (cell_x, y, cell_x + card_width, y + height),
            fill=palette["soft"],
            outline=palette["hairline"],
        )
        cursor = y + 18
        if card.get("value"):
            draw.text((cell_x + 20, cursor), card["value"], font=value_font, fill=palette["ink"])
            cursor += _font_height(value_font) + 8
        if card.get("label"):
            cursor = _draw_wrapped(
                draw,
                card["label"].upper(),
                cell_x + 20,
                cursor,
                card_width - 40,
                label_font,
                palette["accent"],
                line_gap=4,
                max_lines=2,
            )
        if card.get("context"):
            _draw_wrapped(
                draw,
                card["context"],
                cell_x + 20,
                cursor + 4,
                card_width - 40,
                context_font,
                palette["muted"],
                line_gap=4,
                max_lines=2,
            )
    return y + height + 28


def _draw_score_strip(draw, payload: dict, x: int, y: int, width: int, palette: dict, tabloid: bool) -> int:
    height = 128 if tabloid else 112
    fill = palette["accent"] if tabloid else palette["panel"]
    text_fill = palette["accent_contrast"] if tabloid else palette["ink"]
    muted = "#ffe4d6" if tabloid else palette["muted"]
    draw.rectangle((x, y, x + width, y + height), fill=fill, outline=palette["rule"])
    label_font = _newspaper_font("sans_bold", 17)
    team_font = _newspaper_font("serif_bold", 30)
    score_font = _newspaper_font("display" if tabloid else "serif_bold", 62)
    left_w = (width - 210) // 2
    center_x = x + left_w
    draw.text((x + 24, y + 26), "HOME", font=label_font, fill=muted)
    _draw_wrapped(draw, payload["team_home"], x + 24, y + 52, left_w - 36, team_font, text_fill, max_lines=2)
    away_label = "AWAY"
    away_label_w, _ = _text_size(draw, away_label, label_font)
    right_x = x + width - left_w
    draw.text((right_x + left_w - 24 - away_label_w, y + 26), away_label, font=label_font, fill=muted)
    away_lines = _wrap_text(draw, payload["team_away"], team_font, left_w - 36, max_lines=2)
    away_y = y + 52
    for line in away_lines:
        line_w, _ = _text_size(draw, line, team_font)
        draw.text((right_x + left_w - 24 - line_w, away_y), line, font=team_font, fill=text_fill)
        away_y += _font_height(team_font) + 6
    score = f'{payload["score_home"] or "-"} - {payload["score_away"] or "-"}'
    score_w, score_h = _text_size(draw, score, score_font)
    draw.text((center_x + (210 - score_w) // 2, y + (height - score_h) // 2 - 4), score, font=score_font, fill=text_fill)
    return y + height + 22


def _render_newspaper_image(payload: dict, width: int = 1400):
    Image, ImageDraw, _ = _load_pillow()
    tabloid = payload["newspaper_style"] == "tabloid"
    palette = {
        "paper": "#fff8ec" if tabloid else "#fbfaf4",
        "panel": "#fffdf8" if tabloid else "#ffffff",
        "soft": "#ffe4d4" if tabloid else "#e4f0ed",
        "ink": "#15110d" if tabloid else "#171717",
        "muted": "#6b5547" if tabloid else "#636363",
        "rule": "#17110c" if tabloid else "#202020",
        "hairline": "#c9beb0" if tabloid else "#c7c7c0",
        "accent": "#c2261d" if tabloid else "#0b6b5f",
        "accent_contrast": "#fff8ec" if tabloid else "#ffffff",
    }
    height = 2400
    image = _make_paper(width, height, palette["paper"])
    draw = ImageDraw.Draw(image)
    margin = 72
    content_w = width - margin * 2
    y = 54

    masthead_font = _newspaper_font("display" if tabloid else "serif_bold", 82)
    edition_font = _newspaper_font("sans_bold", 20)
    meta_font = _newspaper_font("sans", 21)
    kicker_font = _newspaper_font("sans_bold", 22)
    standfirst_font = _newspaper_font("serif", 31)
    subheadline_font = _newspaper_font("sans_bold", 22)
    panel_title_font = _newspaper_font("sans_bold", 20)
    panel_body_font = _newspaper_font("serif", 25)

    draw.rectangle((34, 34, width - 34, height - 34), outline=palette["rule"], width=2)
    if tabloid:
        header_h = 132
        draw.rectangle((margin, y, margin + content_w, y + header_h), fill=palette["rule"])
        draw.rectangle((margin, y + header_h - 12, margin + content_w, y + header_h), fill=palette["accent"])
        draw.text((margin + 28, y + 24), payload["masthead"].upper(), font=masthead_font, fill=palette["accent_contrast"])
        edition = _truncate_to_width(draw, payload["edition_line"].upper(), edition_font, 360)
        edition_w, _ = _text_size(draw, edition, edition_font)
        draw.text((margin + content_w - 28 - edition_w, y + 58), edition, font=edition_font, fill="#f4cfbc")
        y += header_h + 18
    else:
        draw.line((margin, y, margin + content_w, y), fill=palette["rule"], width=4)
        y += 16
        y = _draw_centered(draw, payload["masthead"], y, masthead_font, palette["ink"], width)
        y += 14
        edition = payload["edition_line"].upper()
        y = _draw_centered(draw, edition, y, edition_font, palette["muted"], width)
        y += 16
        draw.line((margin, y, margin + content_w, y), fill=palette["rule"], width=2)
        y += 22

    meta = " | ".join(text for text in [payload["competition"], payload["venue"]] if text)
    if meta:
        y = _draw_centered(draw, meta.upper(), y, meta_font, palette["muted"], width)
        y += 18

    y = _draw_score_strip(draw, payload, margin, y, content_w, palette, tabloid)

    if payload["kicker"]:
        draw.text((margin, y), payload["kicker"].upper(), font=kicker_font, fill=palette["accent"])
        y += _font_height(kicker_font) + 12
        draw.line((margin, y, margin + 260, y), fill=palette["accent"], width=5)
        y += 22

    headline_face = "display" if tabloid else "serif_bold"
    headline_font, headline_lines = _fit_wrapped_font(
        draw,
        payload["headline"],
        headline_face,
        92 if tabloid else 82,
        48,
        content_w,
        max_lines=4,
    )
    for line in headline_lines:
        draw.text((margin, y), line.upper() if tabloid else line, font=headline_font, fill=palette["ink"])
        y += _font_height(headline_font) + 8
    y += 12

    if payload["subheadline"] and payload["subheadline"] != payload["standfirst"]:
        y = _draw_wrapped(
            draw,
            payload["subheadline"].upper(),
            margin,
            y,
            content_w,
            subheadline_font,
            palette["muted"],
            line_gap=6,
            max_lines=2,
        )
        y += 8
    if payload["standfirst"]:
        y = _draw_wrapped(
            draw,
            payload["standfirst"],
            margin,
            y,
            min(content_w, 1040),
            standfirst_font,
            palette["ink"],
            line_gap=9,
            max_lines=4,
        )
        y += 22

    draw.line((margin, y, margin + content_w, y), fill=palette["rule"], width=3)
    y += 18
    y = _draw_key_numbers(draw, payload["key_numbers"], margin, y, content_w, palette)

    gutter = 34
    left_w = int((content_w - gutter) * 0.62)
    right_w = content_w - gutter - left_w
    left_x = margin
    right_x = margin + left_w + gutter
    left_y = y
    right_y = y

    left_y = _draw_panel(draw, payload["why_it_matters"], left_x, left_y, left_w, palette, panel_title_font, panel_body_font)
    left_y = _draw_panel(draw, payload["coach_watch"], left_x, left_y, left_w, palette, panel_title_font, panel_body_font)
    left_y = _draw_panel(draw, payload["footer"], left_x, left_y, left_w, palette, panel_title_font, panel_body_font)

    quote = payload.get("pull_quote", {})
    if quote.get("quote"):
        quote_panel = {
            "title": "Front-page quote",
            "items": [
                f'"{quote.get("quote", "")}"'
                + (f" - {quote.get('attribution')}" if quote.get("attribution") else "")
            ],
        }
        right_y = _draw_panel(
            draw,
            quote_panel,
            right_x,
            right_y,
            right_w,
            palette,
            panel_title_font,
            _newspaper_font("serif_italic", 28),
            max_items=1,
            fill=palette["soft"] if not tabloid else palette["panel"],
        )
    right_y = _draw_panel(draw, payload["press_reaction"], right_x, right_y, right_w, palette, panel_title_font, panel_body_font)
    right_y = _draw_panel(draw, payload["opponent_angle"], right_x, right_y, right_w, palette, panel_title_font, panel_body_font)

    y = max(left_y, right_y) + 12
    if payload["verdict"]:
        verdict_h = 170
        fill = palette["rule"] if tabloid else palette["panel"]
        text_fill = palette["accent_contrast"] if tabloid else palette["ink"]
        draw.rectangle((margin, y, margin + content_w, y + verdict_h), fill=fill, outline=palette["rule"])
        draw.text((margin + 24, y + 20), "BOTTOM LINE", font=panel_title_font, fill=palette["accent"])
        _draw_wrapped(
            draw,
            payload["verdict"],
            margin + 24,
            y + 56,
            content_w - 48,
            _newspaper_font("serif_bold", 28),
            text_fill,
            line_gap=8,
            max_lines=3,
        )
        y += verdict_h + 34

    crop_bottom = min(height, max(y + 34, 1100))
    return image.crop((0, 0, width, crop_bottom))


def render_newspaper_png(data: dict, width: int = 1400) -> bytes:
    """Render the structured newspaper front page as PNG bytes."""
    payload = _normalise_newspaper_payload(data or {})
    image = _render_newspaper_image(payload, width=width)
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
