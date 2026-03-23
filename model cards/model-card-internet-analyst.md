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
live web content and synthesises it into narrative prose, using query classification and
multi-source search as the retrieval layer. A *secondary use case* is for football fans and
researchers to obtain narrative summaries of recent matches, player form, injuries, and
transfer stories from trusted journalism sources.

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
(`PLANNER_PROMPT`). The planner still identifies one of five query types, but it now also
returns language and retrieval metadata:

| Type | Searches | Output structure |
|------|----------|-----------------|
| `match_report` | 3 | Context → first half → turning point → second half → journalist perspectives → **Bottom line:** |
| `player_performance` | 2 | How they started → key moments → assessment → **Bottom line:** |
| `injury` | 1 | What happened → severity → return date → team impact → **Bottom line:** |
| `team_form` | 2 | Recent run narrative → tactical patterns → key contributors → **Bottom line:** |
| `transfer` | 2 | Current situation → confirmed vs speculated → source credibility → **Bottom line:** |

The planner returns structured JSON including `query_type`, `user_language`,
`answer_language`, `absolute_date`, `entities`, `competition_country`,
`search_locales`, `entity_aliases`, and locale-specific `search_query_batches`.
Conversation history from the last few turns is included so follow-up questions are
resolved correctly.

### Retrieval layer

`search_multi()` in `utils/search.py` now executes locale batches in priority order rather
than one flat English query list. For each locale batch it records `locale_attempts`,
`winning_locale`, and `source_tier`, then either stops on the first sufficiently verified
match-report path or falls through the locale chain.

For recent match reports, the search layer applies deterministic verification before any
answer is generated. Hits are filtered by:

1. Both teams or accepted aliases
2. The exact resolved fixture date
3. Football-only content
4. Narrative-match coverage availability

The search response returns a `verified_match` block with fields such as
`match_identity_verified`, `match_result_verified`, `narrative_coverage_available`,
`verified_date`, `verified_score`, `searched_locales`, `winning_locale`,
`source_tier`, and `verified_source_language`.

### Narrative synthesis (SYSTEM_PROMPT)

The main LLM call receives the combined search results as its context window. The system
prompt instructs the model to:

1. Answer **only** from the provided web search results — not from parametric knowledge
2. Write in **flowing paragraphs** — no bullet points, no statistics tables
3. **Lead with the narrative**, not the scoreline
4. Cite sources inline as `[1]`, `[2]`, with "According to The Guardian [1]…" phrasing
5. Flag **source conflicts**: "Sky Sports [1] reported X; The Athletic [2] suggested Y"
6. Flag **paywalled content**: "The Athletic's full report requires a subscription…"
7. Flag **developing coverage**: "Early reports suggest… final verdicts may follow"
8. Write the final answer in the user's language, even when the supporting sources are in another language

The live page no longer depends on fixture-specific few-shot examples. Style is carried by
the system prompt and the verified search context instead.

### Quality evaluation (EVALUATION_PROMPT)

After the main answer is generated, a second LLM call scores the answer on three
dimensions (1–5 each):

- **Narrative depth:** journalistic prose vs. raw statistics listing
- **Source grounding:** all claims traceable to search results vs. potential hallucination
- **Source diversity:** multiple distinct outlets cited vs. single source

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
