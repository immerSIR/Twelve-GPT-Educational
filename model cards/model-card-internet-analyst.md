# Model card for Full Internet Analyst

The Full Internet Analyst is implemented within the [TwelveGPT Education framework](https://github.com/soccermatics/twelve-gpt-educational)
as an illustration of retrieval-augmented wordalisation — generating narrative commentary
from live internet search results rather than a static dataframe. It is intended as an
educational example of how to combine live retrieval with a structured prompting pipeline.

Jump to section:

- [Intended use](#intended-use)
- [Factors](#factors)
- [Datasets](#datasets)
- [Model](#model)
- [Evaluation](#evaluation)
- [Ethical considerations](#ethical-considerations)
- [Caveats and recommendations](#caveats-and-recommendations)

## Intended use

The *primary use case* is educational: it shows how to build a wordalisation that retrieves
live web content and synthesises it into narrative prose, using multi-locale search as the
retrieval layer. A *secondary use case* is for football fans and researchers to obtain
narrative match reports from trusted journalism sources.

Professional scouting and transfer decision-making are *out of scope* — the tool synthesises
public journalism, not proprietary data. Use for non-football topics is also *out of scope*.

## Factors

The system is prompted for association football. Coverage quality varies by league: top
European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Primeira Liga)
are well covered; lower-division and women's football coverage is limited by what
journalism sources publish. The system now searches in the competition's local language
first when it can infer that locale, then falls back to the user's language and finally
to English. Final answers are written in the user's language by default.

## Datasets

Unlike other pages in this framework, the Full Internet Analyst uses **no static dataset**.
All content is retrieved in real-time via the Perplexity Sonar API (primary) or DuckDuckGo
(fallback). The retrieval layer now uses three source tiers:

- **Curated local**: trusted football outlets for supported locales, combined with global stats domains
- **Open-web local**: local-language open-web search for unsupported locales, with strict post-filtering
- **English fallback**: trusted English-language journalism and global stats domains

The current curated local bundles cover Portugal, Poland, England, Spain, Germany, Italy,
France, the Netherlands, Turkey, and Egypt. Global football grounding domains are still
used across locales:

**English journalism-first:** The Athletic, The Guardian, BBC Sport, Sky Sports, ESPN Soccer,
Goal, FourFourTwo, Opta Analyst, CBS Sports, 90min, talkSPORT, Planet Football,
Football365, The Independent, World Soccer Talk.

**Selected local bundles:** A Bola, O Jogo, Record, Maisfutebol, Zerozero, Meczyki,
Weszło, Marca, AS, Kicker, Gazzetta, L'Équipe, VI, Fanatik, FilGoal, Yallakora, and others.

**Statistics (grounding support):** SofaScore, FotMob, FBref, Transfermarkt, BeSoccer.

## Model

### Query planning

Before searching, the system plans every user question with a single LLM call
(`PLANNER_PROMPT`). The planner focuses exclusively on match report retrieval,
identifying the fixture and generating rich, diverse search queries across three
evidence categories per locale.

The planner returns structured JSON including `user_language`, `answer_language`,
`absolute_date`, `entities`, `competition_country`, `search_locales`,
`entity_aliases`, and locale-specific `search_query_batches`. Each batch carries an
explicit `query_category`: `match_narrative`, `post_match_reaction`, or
`context_sentiment`, with 2-4 queries per category per locale. Conversation history
from the last few turns is included so follow-up questions are resolved correctly.

| Category | Purpose |
|----------|---------|
| `match_narrative` | Tactical breakdowns, formation analysis, key moments, set pieces, individual displays |
| `post_match_reaction` | Player ratings, manager quotes, journalist verdicts, press conferences |
| `context_sentiment` | Fan mood, coach pressure, pre-match form, lineup surprises, crowd atmosphere |

### Retrieval layer

`search_multi()` in `utils/search.py` now executes every planned batch for recent
match reports instead of short-circuiting on the first passing locale. Results are
aggregated into category-specific `evidence_blocks`, a `primary_match_locale`, and
category-aware `locale_attempts`.

For recent match reports, the search layer applies deterministic verification before any
answer is generated. Verification is now split into three passes:

1. **Match narrative verification:** both teams, exact fixture date, football-only content,
   and genuine match-report or live-commentary signals
2. **Post-match reaction verification:** both teams, exact fixture date, and verdict or
   reaction coverage
3. **Context verification:** at least one fixture club plus season-relevant mood,
   pressure, or expectation coverage

The search response returns a `verified_match` block with fields such as
`match_identity_verified`, `match_result_verified`, `narrative_coverage_available`,
`context_coverage_available`, `verified_date`, `verified_score`, `searched_locales`,
`winning_locale`, `primary_match_locale`, `source_tier`, `verified_source_language`,
`accepted_hits`, `reaction_hits`, and `context_hits`.

### Narrative synthesis (SYSTEM_PROMPT)

The answer path is now two-stage. A first LLM call structures the evidence into a JSON
summary (`match_story`, `journalist_verdicts`, `context_mood`, `source_conflicts`,
`data_vs_web`, and `evidence_gaps`). The final synthesis call then receives the labeled
evidence blocks plus the structured summary. The system prompt instructs the model to:

1. Answer **only** from the provided web search results — not from parametric knowledge
2. Write in **guided prose**, allowing short section labels when they improve clarity
3. **Lead with the narrative**, not the scoreline
4. Cite sources inline as `[1]`, `[2]`, with "According to The Guardian [1]…" phrasing
5. Flag **source conflicts**: "Sky Sports [1] reported X; The Athletic [2] suggested Y"
6. Surface **evidence gaps** instead of smoothing them over
7. Reconcile optional **Twelve data analysis** as `supported`, `contradicted`, `mixed`,
   or `insufficient evidence`
8. Write the final answer in the user's language, even when the supporting sources are in another language

The live page no longer depends on fixture-specific few-shot examples. Style is carried by
the system prompt and the verified search context instead.

### Quality evaluation (EVALUATION_PROMPT)

After the main answer is generated, a second LLM call scores the answer on five
dimensions:

- **Narrative depth:** journalistic prose vs. raw statistics listing
- **Source grounding:** all claims traceable to search results vs. potential hallucination
- **Source diversity:** multiple distinct outlets cited vs. single source
- **Context integration:** whether mood and expectation evidence is used accurately
- **Data reconciliation:** whether Twelve-vs-web reconciliation is handled correctly
  (`null` when no Twelve data narrative was present)

The system does not retry simply because prose quality is low. Retry is reserved for cases
where retrieval found candidate results for a recent match but exact team/date verification
still failed.

### Language model

Supports OpenAI (gpt-4o-mini), Azure OpenAI, Google Gemini, and LM Studio local models.
Provider selection is controlled via `settings.py` and `.streamlit/secrets.toml`.

## Evaluation

Qualitative evaluation during development focused on whether the output reads as
journalistic narrative synthesis rather than a statistics summary. Test cases included
matches with rich coverage (El Clásico, North-West Derby), matches with limited coverage
(lower Portuguese league fixtures), and edge cases (paywall snippets, developing stories).

The three-dimension quality score (narrative depth, source grounding, source diversity)
provides lightweight automated evaluation per response. Scores of ≤ 2 on narrative depth
trigger automatic query refinement and re-search.

Compared to the Football Scout wordalisation — where a fixed dataset enables
quantitative accuracy evaluation — the Internet Analyst's output quality is inherently
dependent on what journalism exists at search time and cannot be evaluated against a
ground truth label.

## Ethical considerations

The system retrieves and synthesises publicly available journalism. It cannot access
paywalled content (The Athletic, some others) in full, and flags this transparently.
The system may reproduce editorial biases present in its source publications. Moving to
local-language retrieval broadens coverage, but also means answers may inherit the framing
or blind spots of domestic outlets.

Coverage of women's football and lower-division leagues is still limited by the volume of
available journalism. The system should not be used to make professional football
decisions (transfers, scouting) — it synthesises public commentary, not expert analysis.
All factual claims should be verified against the original sources cited.

## Caveats and recommendations

Coverage quality depends entirely on what journalism is available at search time. Very
recent events (within hours of a match) will have developing coverage that may be revised.
Lower-league matches, women's football, and non-European competitions will still have less
coverage. Always check cited sources directly for critical decisions.

The new locale-aware retrieval improves coverage for leagues primarily reported outside
English, but it is still conservative. If the system cannot verify the exact fixture/date
with enough narrative coverage across the locales it tried, it will refuse rather than
guess.
