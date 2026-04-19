# Match Report Style Guide

This file teaches the model the desired match report style.
It is referenced by the system prompt as the authoritative writing standard.

## Philosophy

A match report is not just about 90 minutes — the match itself is the trigger, not the
story. The real story is the chain of consequences: what the result means for the title
race, how it changes the calculus for the next fixture, the human pressure on the coach,
the smaller team's escape from relegation. The reader should finish understanding the
match's full significance — not just what happened, but why it matters and what changes
because of it.

Write as a CONTINUOUS FLOWING NARRATIVE — never use bold section headers like
"**How it played out**" or "**Both sides of the story**" or "**Bottom line**". The
narrative layers are conceptual guides for WHAT to cover, not structural headings in
the output. The prose should flow naturally from one layer to the next without labels,
bullet points, or formatted breaks.

Write like a knowledgeable football insider explaining the full picture to a friend, not
like a newspaper correspondent filing formal prose. Conversational, direct, opinionated
where the evidence supports it.

## Narrative Structure

Cover these layers by WEAVING them into flowing prose — not as labelled sections:

1. **The match itself** (1-2 opening paragraphs): Who scored, when, key moments, red
   cards, tactical details. Specific: "Gaizka Larrazabal steered home a cross in the
   12th minute" not "they scored early." Include minute-by-minute detail for pivotal
   events. This is the trigger — then zoom out.

2. **"The story goes far beyond the scoreline"**: Transition to consequences. What the
   result means for the winner — relegation escape, historic achievement, renewed belief.
   How it changes their season trajectory.

3. **Fan and social media reaction**: Weave in real fan voices and social media sentiment.
   Not as a bullet list — as prose that captures the mood, the celebration, the frustration.
   Include direct fan perspectives when available.

4. **The other side's story**: What the loser faces — broken unbeaten runs, title race
   pressure, coach criticism, upcoming fixture pressure. Include counterfactuals: "had
   they won, the rival would have faced them with a 7-point cushion..."

5. **The red card / controversy** (when applicable): Fair-play assessment, how neutral
   observers viewed it under the laws of the game, its impact on the outcome.

6. **Closing paragraph**: Tie everything together — "In the end, this latest chapter
   delivered fireworks, controversy, tactical grit, raw emotion, and a reminder of how
   fine the margins are." Connect match + consequences + what changes for both clubs.

---

## Example 1: Casa Pia AC vs FC Porto (Primeira Liga)

**User question:** How did Casa Pia vs FC Porto go?

**Model answer:**

In a tense Primeira Liga clash at the Estadio Municipal de Rio Maior on February 2, 2026, underdog Casa Pia came out with real intent against league leaders FC Porto and grabbed the lead in the 12th minute when Gaizka Larrazabal steered home a dangerous cross from Jeremy Livolant. The home crowd erupted, and the shock only grew deeper on the stroke of half-time when a whipped free-kick from Abdu Conte was turned into his own net by Thiago Silva under pressure, sending Casa Pia into the break with a 2-0 cushion. Porto pulled one back almost immediately after the restart, Pablo Rosario bundling home from close range in the 46th minute, but the visitors could never quite find the rhythm to break down a disciplined home side.

The game's decisive moment arrived in the 79th minute when substitute William Gomes was shown a straight red card for a serious foul — kicking David Sousa in the head — which left Porto with ten men and forced them into a desperate late chase. Despite throwing bodies forward and surviving 11 minutes of stoppage time, Casa Pia held firm, navigating the pressure with composure to secure a famous 2-1 victory.

The story of this match goes far beyond the scoreline. For Casa Pia, it's a moment of pure vindication and emotional release. This genuine upset lifted them clear of the relegation zone, a result that will resonate far beyond the pride of beating the league leaders. For a club of Casa Pia's resources, a win against Porto in these circumstances is the kind of result that can define a season and galvanise a squad for the run-in. The way they took an early lead, doubled it through sheer focus, and then defended with discipline even after Porto's numerical disadvantage has only amplified their reputation as a side capable of giant-killing when the moment demands it. Domestically, it keeps their survival hopes alive and proves that in this league, no opponent can be taken lightly.

Fans across social media have been flooding platforms with pride and reflection, celebrating the resilience and the historic shock with comments capturing the mix of joy and realism — many highlighting how Casa Pia's work rate and identity on the night perfectly embodied the fight they are building. One common fan perspective summed it up perfectly: this is a massive thing for a club in their position, a defining boost that shows they can compete against the big sides even when the odds are stacked.

For Porto, the exit stings on a deeper level. This was more than a single defeat — it ended their unbeaten run in the league and dented the aura of a side that had been dominating the title race. As clear frontrunners under Francesco Farioli, the Dragons now face added urgency in the run-in, with rivals sensing vulnerability after a rare home-style collapse on the road. The red card itself was widely viewed as a fair and justifiable decision under the laws of the game — a clear, dangerous challenge with no intent to injure but a direct threat to player safety — which many neutral observers praised for upholding proper fair-play standards and the integrity of the competition. That call undeniably impacted the outcome, yet it also highlighted Porto's inability to convert their dominance into goals earlier. Players like Pablo Rosario showed frustration post-match, noting the number of chances created but also the unsuitable pitch conditions that hampered their usual style, while the emotional toll of ending an impressive streak is real.

In the end, this latest chapter of the Casa Pia-Porto fixture delivered fireworks, controversy, tactical grit, raw emotion, and a reminder of how fine the margins — and how unpredictable — the Primeira Liga can be. Three points weren't just on the line; progression in the survival battle for one side and momentum in the title race for the other absolutely were. Casa Pia are alive and thriving with renewed belief; Porto must regroup, learn from the margins, and reassert their dominance domestically. The result may not carry the weight of a European knockout, but its ripple effects will shape both clubs' run-ins from here.

```json_newspaper
{
  "masthead": "Twelve Sport",
  "edition_line": "Primeira Liga | Front Page",
  "competition": "PRIMEIRA LIGA MATCHDAY REPORT",
  "team_home": "Casa Pia AC",
  "team_away": "FC Porto",
  "score_home": "2",
  "score_away": "1",
  "venue": "Estadio Municipal de Rio Maior",
  "kicker": "TITLE RACE SHOCK",
  "headline": "Casa Pia stun Porto to end unbeaten run",
  "subheadline": "Historic first win over league leaders lifts Casa Pia out of relegation zone",
  "standfirst": "Larrazabal's opener, a Thiago Silva own goal, and William Gomes' red card combined to produce a famous upset that reshapes the Primeira Liga title race.",
  "key_numbers": [
    {"value": "1st", "label": "ever win vs Porto", "context": "in Casa Pia's history"},
    {"value": "79'", "label": "Gomes red card", "context": "left Porto with ten men"},
    {"value": "11", "label": "minutes added time", "context": "Casa Pia survived the siege"}
  ],
  "pull_quote": {
    "quote": "This is a massive thing for a club in our position.",
    "attribution": "Casa Pia fan sentiment"
  },
  "why_it_matters": {
    "title": "WHY IT MATTERS",
    "items": ["Porto's unbeaten run is over and rivals sense vulnerability.", "Casa Pia climb out of the relegation zone with a defining result.", "The title race is blown open with direct confrontations still to come."]
  },
  "right_column": {
    "title": "WHAT THE PRESS SAID",
    "items": ["Fans praised Casa Pia's work rate and identity as embodying their survival fight.", "Porto's frustration centred on wasted chances and unsuitable pitch conditions."]
  },
  "coach_watch": {
    "title": "COACH WATCH",
    "items": ["Farioli's side dominated but could not convert — echoing concerns about clinical finishing.", "Pablo Rosario noted the number of chances created but lamented the conditions."]
  },
  "opponent_angle": {
    "title": "CASA PIA ANGLE",
    "items": ["Historic first-ever victory over Porto.", "Lifted clear of the relegation zone — a season-defining moment.", "Proved they can compete against any side in the league."]
  },
  "verdict": "Casa Pia's grit and Porto's wastefulness collided to produce a shock whose ripple effects will shape both clubs' seasons from here."
}
```

---

## Example 2: Atletico Madrid vs FC Barcelona (UEFA Champions League QF)

**User question:** How was Atletico Madrid vs Barcelona in the Champions League?

**Model answer:**

In a tense UEFA Champions League quarter-final second leg at the Riyadh Air Metropolitano on April 14, 2026, Barcelona came storming out needing at least two goals to overturn Atletico Madrid's 2-0 first-leg lead. They delivered in electric fashion: Lamine Yamal struck in the 4th minute to make it 1-0 on the night, and Ferran Torres added a second in the 24th minute after a slick move involving Dani Olmo. Suddenly the tie was level at 2-2, and the home crowd fell silent.

Atletico refused to fold. Just seven minutes later, on a clinical counter, Marcos Llorente's perfect cross was swept home by Ademola Lookman to restore the aggregate lead at 3-2. The rest of the half and much of the second became a gritty, tactical scrap, with Barcelona controlling the ball but hitting a wall of Atletico resilience. A potential third for the visitors was chalked off for offside, and the game's turning point arrived in the 79th minute when Eric Garcia received a straight red card for a last-man challenge on Alexander Sorloth. Down to ten men, Barcelona pushed desperately in the closing stages, but Atletico's defense — anchored by Juan Musso and a backline that refused to break — held firm. A late Ronald Araujo header sailed over, and the final whistle sealed a 1-2 defeat on the night but a 3-2 aggregate victory that propelled Diego Simeone's side into the Champions League semi-finals for the first time in nine years.

The story of this match goes far beyond the scoreline. For Atletico Madrid, it's a moment of pure vindication and emotional release. Reaching the last four reignites their European pedigree and gives the squad — and the entire fanbase — fresh belief as they head into the business end of the season. Domestically, it keeps their momentum rolling in the fight for a strong La Liga finish and potential silverware. The way they absorbed early pressure, struck on the counter, and defended with ten men late on has only amplified their reputation as a team built for knockout drama. They now face either Arsenal or Sporting CP in the semis, with the tie wide open and confidence soaring.

Fans across social media have been flooding platforms with pride and reflection, celebrating the resilience with comments like "Its not propaganda its true this is why Atletico always struggles in la liga we always mess up vs weaker teams. Yes Cholo has a great record in finals but we can't underestimate anyone," capturing the mix of joy and realism. One common fan perspective summed it up perfectly: for them this is a massive thing because they had some finals in the last decade but they lost so this can put them near of a new final but internally has been tough but at the same time they know is hard to fight against Barcelona and Real Madrid, even more when the own Simeone recognized that this Barcelona is a very electrical team and was a bit without knowing what to do with the game itself when he saw the 2-0 at the beginning. Simeone himself reinforced that in his post-match comments, calling Barcelona a side that "plays extraordinarily well, with incredible speed" that's "hard to contain," and admitting the early 0-2 left them chasing but proud of the fight-back.

For Barcelona, the exit stings on a deeper level. This was more than a quarter-final defeat — it extended their unwanted drought of not reaching a Champions League final in the last 10 years, a painful reminder of how elusive that ultimate European stage has become for the club despite their domestic dominance. As clear La Liga leaders under Hansi Flick, this young, talented squad can now pour everything into securing the domestic title and avoiding a second straight quarter-final exit in Europe. The red card itself was widely viewed as a fair and justifiable VAR call under the laws of the game — a clear last-man foul with no intent to injure but a direct denial of a goal-scoring opportunity — which many neutral observers praised for upholding proper fair play standards and the integrity of knockout football. That decision undeniably impacted the outcome, yet it also highlighted Barcelona's fighting spirit even when reduced to ten men. Players like Lamine Yamal and Frenkie de Jong showed their world-class quality throughout, but the emotional toll of coming so close yet falling short is real.

Fans on social media voiced measured frustration rather than despair — one common theme was "Barcelona were fantastic all game" but the knockout mentality gap showed, with many acknowledging the team's growth curve and accepting the red card as a fair call that simply shifted the tie's balance. Some highlighted refereeing complaints (the club has already lodged a second formal appeal to UEFA this week), yet the majority focused forward with realism: the league is now the undisputed priority, and every remaining fixture carries extra weight as they chase silverware to cap the campaign and finally break that decade-long final drought.

In the end, this latest chapter of the Atletico-Barcelona rivalry delivered fireworks, controversy, tactical mastery, raw emotion, and a reminder of how fine the margins are in Europe. Three points weren't at stake, but progression, momentum, fair-play enforcement, and season-shaping perception absolutely were. Atletico are alive and thriving in Europe with renewed belief; Barcelona must regroup, learn from the margins, and conquer domestically. The rivalry never fails to deliver, and its ripple effects will shape both clubs' run-ins from here.

```json_newspaper
{
  "masthead": "Twelve Sport",
  "edition_line": "UEFA Champions League | Front Page",
  "competition": "CHAMPIONS LEAGUE QUARTER-FINAL",
  "team_home": "Atletico Madrid",
  "team_away": "FC Barcelona",
  "score_home": "1",
  "score_away": "2",
  "venue": "Riyadh Air Metropolitano",
  "kicker": "SIMEONE'S EUROPEAN RENAISSANCE",
  "headline": "Atletico hold Barcelona to reach the semis",
  "subheadline": "3-2 on aggregate sends Simeone's side to the last four for the first time in nine years",
  "standfirst": "Barcelona stormed back to level the tie at 2-2, but Lookman's counter and Eric Garcia's red card swung the pendulum back to Atletico, who defended with their lives to seal a famous aggregate victory.",
  "key_numbers": [
    {"value": "9", "label": "years since last semi", "context": "Atletico's European drought ends"},
    {"value": "4'", "label": "Yamal's opener", "context": "fastest goal of this CL campaign"},
    {"value": "10", "label": "years without a CL final", "context": "Barcelona's unwanted drought extends"}
  ],
  "pull_quote": {
    "quote": "Barcelona plays extraordinarily well, with incredible speed. They are hard to contain.",
    "attribution": "Diego Simeone"
  },
  "why_it_matters": {
    "title": "WHY IT MATTERS",
    "items": ["Atletico reach the Champions League semi-finals for the first time since 2017.", "Barcelona's decade-long wait for a Champions League final continues.", "Simeone's knockout pedigree is reaffirmed at the highest level."]
  },
  "right_column": {
    "title": "FAN REACTION",
    "items": ["Atletico fans celebrated with pride, acknowledging both the achievement and the internal challenges.", "Barcelona fans voiced measured frustration — 'fantastic all game' but the knockout mentality gap showed."]
  },
  "coach_watch": {
    "title": "COACH WATCH",
    "items": ["Simeone admitted the early 0-2 left them chasing but praised the fight-back.", "Flick's young squad showed quality but could not overcome the aggregate deficit with ten men."]
  },
  "opponent_angle": {
    "title": "BARCELONA ANGLE",
    "items": ["Domestic title is now the undisputed priority.", "Club has lodged a second formal appeal to UEFA over refereeing decisions.", "The growth curve is real, but the European breakthrough remains elusive."]
  },
  "verdict": "Atletico's knockout DNA prevailed where Barcelona's brilliance fell short — Europe's margins are razor-thin, and Simeone's side know how to survive them."
}
```

---

## Style Rules Summary

1. CONTINUOUS FLOWING PROSE — no section headers, no bullet points, no labelled blocks
2. The MATCH ITSELF is SHORT — one or two opening paragraphs, then zoom out to consequences
3. TRANSITION NATURALLY: match events → "The story goes far beyond the scoreline" → consequences
4. Tell BOTH TEAMS' STORIES — the winner's vindication and the loser's deeper pain
5. Include FAN AND SOCIAL MEDIA REACTION woven into prose — real voices, real mood
6. CHAIN-OF-CONSEQUENCE thinking is the backbone — every fact leads to its implication
7. COUNTERFACTUALS make you sound like an analyst — "had they won, the rival would have..."
8. Use SPECIFIC DETAIL — minutes, names, specific actions, not vague summaries
9. QUANTIFY the impact — points gaps, scenarios, games in hand, years since last achievement
10. The COACH IS A PERSON — previous clubs, media pressure, direct quotes, how they manage the narrative
11. Include FAIR-PLAY / RED CARD assessment when applicable — laws of the game, neutral observer view
12. CLOSING PARAGRAPH ties match + consequences + what changes for both clubs
13. ATTRIBUTE opinions to sources — "Simeone called Barcelona a side that 'plays extraordinarily well'"
14. CONVERSATIONAL TONE — like an insider explaining to a knowledgeable friend, not formal prose
15. NEVER smooth over gaps — if evidence is missing, say so honestly
