import unittest

from utils.internet_analyst_payloads import (
    build_search_batch_caption,
    build_search_context_payload,
    build_structuring_user_prompt,
    build_synthesis_user_prompt,
    render_newspaper_html,
    render_newspaper_png,
)


class InternetAnalystPayloadTests(unittest.TestCase):
    def test_search_context_payload_contains_labeled_evidence_blocks(self):
        payload = build_search_context_payload(
            {
                "answer_language": "en",
                "search_locales": ["pt-PT", "en"],
            },
            {
                "citations": [
                    "https://www.ojogo.pt/cronica",
                    "https://www.abola.pt/contexto",
                ],
                "primary_match_locale": "pt-PT",
                "source_tier": "curated_local",
                "verified_match": {
                    "team_a": "FC Porto",
                    "team_b": "SC Braga",
                    "requested_date_display": "March 22, 2026",
                    "match_identity_verified": True,
                    "verified_score": "FC Porto 2-1 SC Braga",
                    "narrative_coverage_available": True,
                    "context_coverage_available": True,
                    "searched_locales": ["pt-PT", "en"],
                    "primary_match_locale": "pt-PT",
                    "source_tier": "curated_local",
                    "verified_source_language": "pt",
                },
                "evidence_blocks": {
                    "match_narrative": [
                        {
                            "title": "Crónica FC Porto 2-1 SC Braga",
                            "body": "Crónica e análise tática.",
                            "href": "https://www.ojogo.pt/cronica",
                            "domain": "ojogo.pt",
                        }
                    ],
                    "post_match_reaction": [],
                    "context_sentiment": [
                        {
                            "title": "Assobios no Dragão",
                            "body": "Os adeptos mostraram frustração apesar da vitória.",
                            "href": "https://www.abola.pt/contexto",
                            "domain": "abola.pt",
                        }
                    ],
                },
            },
            data_narrative="Barcelona dominated possession but looked nervous after scoring.",
        )

        self.assertIn("--- Verified match facts ---", payload)
        self.assertIn("--- Match narrative evidence ---", payload)
        self.assertIn("--- Post-match reaction evidence ---", payload)
        self.assertIn("--- Context & mood evidence ---", payload)
        self.assertIn("--- Twelve data analysis (provided by user) ---", payload)
        self.assertIn("[1] ojogo.pt", payload)
        self.assertIn("[2] abola.pt", payload)

    def test_search_batch_caption_includes_query_category(self):
        caption = build_search_batch_caption(
            {
                "locale": "pt-PT",
                "source_tier": "curated_local",
                "query_category": "context_sentiment",
            }
        )
        self.assertEqual(caption, "pt-PT [curated_local] [context_sentiment]")

    def test_structuring_prompt_requests_data_reconciliation_when_present(self):
        prompt = build_structuring_user_prompt(
            "en",
            "How was Porto vs Braga?",
            "Evidence block here",
            has_data_narrative=True,
        )
        self.assertIn("supported`, `contradicted`, `mixed`, or `insufficient evidence`", prompt)
        self.assertIn("Evidence context:", prompt)
        self.assertIn("`match_story`", prompt)
        self.assertIn("`hard_gaps`", prompt)

    def test_synthesis_prompt_includes_style_exemplar_and_strict_contract(self):
        prompt = build_synthesis_user_prompt(
            "en",
            "Evidence block here",
            "How was Porto vs Braga?",
            evidence_summary={
                "match_story": "Porto dominated but were punished in transition.",
                "hard_gaps": ["No verified board reaction found."],
                "data_vs_web": {"relationship": "mixed"},
            },
            has_data_narrative=True,
        )
        self.assertIn("--- Structured evidence summary ---", prompt)
        self.assertIn("--- Repository style exemplar", prompt)
        self.assertIn("Casa Pia AC vs FC Porto", prompt)
        self.assertIn("Do not invent quotes, standings scenarios, board reactions, or pressure narratives", prompt)
        self.assertIn("CONTINUOUS FLOWING NARRATIVE", prompt)
        self.assertIn("NO section headers", prompt)
        self.assertIn("Data vs internet", prompt)
        self.assertIn("```User: How was Porto vs Braga?```", prompt)

    def test_render_newspaper_html_supports_rich_newspaper_schema(self):
        html = render_newspaper_html(
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
                "standfirst": "Porto controlled the match, but Casa Pia landed the decisive blow.",
                "key_numbers": [
                    {"value": "4", "label": "points to Sporting", "context": "after the defeat"},
                    {"value": "1st", "label": "league defeat", "context": "for Porto this season"},
                ],
                "pull_quote": {
                    "quote": "There is always a game where everything goes badly.",
                    "attribution": "Francesco Farioli",
                },
                "why_it_matters": {
                    "title": "WHY IT MATTERS",
                    "items": ["The title race is alive again."],
                },
                "right_column": {
                    "title": "WHAT THE PRESS SAID",
                    "items": ["Record: \"Dominant but toothless\""],
                },
                "coach_watch": {
                    "title": "COACH WATCH",
                    "items": ["Ajax parallels are back in the conversation."],
                },
                "opponent_angle": {
                    "title": "CASA PIA ANGLE",
                    "items": ["The win lifted Casa Pia out of the relegation zone."],
                },
                "verdict": "A damaging defeat with title-race consequences.",
            }
        )

        self.assertIn("newspaper-masthead", html)
        self.assertIn("newspaper-frontpage--broadsheet", html)
        self.assertIn("newspaper-keynumbers", html)
        self.assertIn("Front-page quote", html)
        self.assertIn("WHY IT MATTERS", html)
        self.assertIn("COACH WATCH", html)
        self.assertIn("CASA PIA ANGLE", html)
        self.assertIn("Porto&#x27;s invincibility ends in Rio Maior", html)

    def test_render_newspaper_html_remains_backward_compatible_with_legacy_schema(self):
        html = render_newspaper_html(
            {
                "competition": "PRIMEIRA LIGA MATCHDAY REPORT",
                "team_home": "Casa Pia AC",
                "team_away": "FC Porto",
                "score_home": "1",
                "score_away": "0",
                "venue": "Estádio Municipal de Rio Maior",
                "headline": "Porto's invincibility ends in Rio Maior",
                "subheadline": "First Primeira Liga defeat as title race blown open",
                "left_column": {
                    "title": "TITLE RACE IMPACT",
                    "items": ["After: Porto +4"],
                },
                "right_column": {
                    "title": "WHAT THE PRESS SAID",
                    "items": ["Record: \"Dominant but toothless\"", "A Bola: \"Dominance without finishing is just noise\""],
                },
                "bottom_left": {
                    "title": "COACH SPOTLIGHT",
                    "items": ["Farioli under pressure again."],
                },
                "bottom_right": {
                    "title": "INSTITUTIONAL RESPONSE",
                    "items": ["Vilas-Boas backed Farioli publicly."],
                },
                "footer": {
                    "title": "CASA PIA",
                    "items": ["Left the relegation zone."],
                },
                "verdict": "Porto lost because football punishes wastefulness.",
            }
        )

        self.assertIn("TITLE RACE IMPACT", html)
        self.assertIn("WHAT THE PRESS SAID", html)
        self.assertIn("COACH SPOTLIGHT", html)
        self.assertIn("INSTITUTIONAL RESPONSE", html)
        self.assertIn("Bottom line", html)

    def test_render_newspaper_html_handles_thin_evidence_without_optional_fields(self):
        html = render_newspaper_html(
            {
                "team_home": "Casa Pia AC",
                "team_away": "FC Porto",
                "score_home": "1",
                "score_away": "0",
                "headline": "Late counter decides it",
                "verdict": "The upset mattered more than the scoreline alone.",
            }
        )

        self.assertIn("Twelve Sport", html)
        self.assertIn("Late counter decides it", html)
        self.assertIn("The upset mattered more than the scoreline alone.", html)
        self.assertNotIn(">None<", html)

    def test_render_newspaper_html_supports_broadsheet_and_tabloid_aliases(self):
        broadsheet_html = render_newspaper_html(
            {
                "style": "Guardian",
                "headline": "A controlled win with wider consequences",
                "verdict": "The result mattered because of the way it reshaped the run-in.",
            }
        )
        tabloid_html = render_newspaper_html(
            {
                "newspaper_style": "Daily News",
                "headline": "Title race rocked",
                "verdict": "The shock changed the pressure around the league.",
            }
        )

        self.assertIn("newspaper-frontpage--broadsheet", broadsheet_html)
        self.assertIn("newspaper-frontpage--tabloid", tabloid_html)

    def test_render_newspaper_png_returns_real_png_bytes(self):
        png = render_newspaper_png(
            {
                "newspaper_style": "broadsheet",
                "masthead": "Twelve Sport",
                "edition_line": "Primeira Liga | Front Page",
                "competition": "PRIMEIRA LIGA MATCHDAY REPORT",
                "team_home": "Casa Pia AC",
                "team_away": "FC Porto",
                "score_home": "1",
                "score_away": "0",
                "headline": "Porto's invincibility ends in Rio Maior",
                "standfirst": "Casa Pia's counterpunch turned the title race narrative in one night.",
                "key_numbers": [{"value": "4", "label": "points to Sporting", "context": "after the defeat"}],
                "verdict": "A damaging defeat with title-race consequences.",
            }
        )

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png), 10_000)

    def test_render_newspaper_png_supports_tabloid_style(self):
        png = render_newspaper_png(
            {
                "newspaper_style": "tabloid",
                "team_home": "Casa Pia AC",
                "team_away": "FC Porto",
                "score_home": "1",
                "score_away": "0",
                "headline": "Title race rocked",
                "verdict": "The shock changed the pressure around the league.",
            }
        )

        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_casa_pia_acceptance_fixture_hits_tabloid_renderer_and_prompt_contract(self):
        prompt = build_synthesis_user_prompt(
            "en",
            "Evidence block here",
            "How did Casa Pia vs FC Porto go?",
            evidence_summary={
                "match_story": "Porto dominated territory but Casa Pia took the decisive chance.",
                "table_impact": "The gap to Sporting narrowed.",
                "opponent_story": "Casa Pia left the relegation zone.",
                "coach_pressure": "Ajax parallels returned in the media coverage.",
                "strategic_ripple": "The direct meeting with Sporting now carries far more pressure.",
                "press_consensus": "Record and A Bola focused on Porto's wastefulness.",
                "hard_gaps": [],
                "data_vs_web": {"relationship": None, "summary": ""},
            },
        )
        html = render_newspaper_html(
            {
                "masthead": "Twelve Sport",
                "edition_line": "Primeira Liga | Front Page",
                "competition": "PRIMEIRA LIGA MATCHDAY REPORT",
                "team_home": "Casa Pia AC",
                "team_away": "FC Porto",
                "score_home": "1",
                "score_away": "0",
                "venue": "Estádio Municipal de Rio Maior",
                "kicker": "TITLE RACE SHOCK",
                "headline": "Porto's invincibility ends in Rio Maior",
                "standfirst": "Casa Pia's win changed the title-race temperature in one night.",
                "key_numbers": [{"value": "4", "label": "points to Sporting", "context": "after the defeat"}],
                "pull_quote": {"quote": "There is always a game where everything goes badly.", "attribution": "Francesco Farioli"},
                "why_it_matters": {"title": "WHY IT MATTERS", "items": ["The direct meeting with Sporting now looks far more volatile."]},
                "right_column": {"title": "WHAT THE PRESS SAID", "items": ["Record: \"Dominant but toothless\""]},
                "coach_watch": {"title": "COACH WATCH", "items": ["Ajax parallels are back in the coverage."]},
                "opponent_angle": {"title": "CASA PIA ANGLE", "items": ["Casa Pia climbed out of the relegation zone."]},
                "verdict": "A defeat whose damage extends far beyond Rio Maior.",
            }
        )

        self.assertIn("Casa Pia AC vs FC Porto", prompt)
        self.assertIn("CONTINUOUS FLOWING NARRATIVE", prompt)
        self.assertIn("NO section headers", prompt)
        self.assertIn("newspaper_style", prompt)
        self.assertIn("newspaper-score-strip", html)
        self.assertIn("newspaper-quote-card", html)
        self.assertIn("newspaper-verdict-strip", html)


if __name__ == "__main__":
    unittest.main()
