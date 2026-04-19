import unittest
from datetime import date

from utils.search import (
    build_match_report_refusal,
    build_recent_match_search,
    match_report_can_answer,
    resolve_query_date,
    verify_context_hits,
    verify_match_hits,
)


class RecentMatchGuardrailsTests(unittest.TestCase):
    def test_resolve_query_date_handles_day_of_month_language(self):
        resolved = resolve_query_date(
            "How was the game between FC Porto vs SC Braga on day 22 of March?",
            today=date(2026, 3, 23),
        )
        self.assertEqual(resolved, "2026-03-22")

    def test_build_recent_match_search_uses_exact_date_and_neutral_queries(self):
        built = build_recent_match_search(
            "How was the game between FC Porto vs SC Braga on day 22 of March?",
            [
                "FC Porto vs SC Braga match report tactical analysis 2025/26",
                "FC Porto vs SC Braga player ratings performances 2025/26",
                "Sergio Conceicao Carlos Carvalhal post-match quotes press conference FC Porto SC Braga 2025/26",
            ],
            today=date(2026, 3, 23),
        )

        self.assertEqual(
            built["search_queries"],
            [
                "FC Porto vs SC Braga March 22 2026 match report tactical analysis",
                "SC Braga vs FC Porto March 22 2026 final score player ratings live commentary",
                "FC Porto SC Braga March 22 2026 post-match quotes press conference",
            ],
        )
        self.assertEqual(built["match_context"]["requested_date"], "2026-03-22")
        self.assertEqual(built["match_context"]["team_a"], "FC Porto")
        self.assertEqual(built["match_context"]["team_b"], "SC Braga")
        self.assertTrue(all("Conceicao" not in query for query in built["search_queries"]))
        self.assertTrue(all("Carvalhal" not in query for query in built["search_queries"]))

    def test_verify_match_hits_filters_wrong_date_wrong_sport_and_generic_pages(self):
        built = build_recent_match_search(
            "How was the game between FC Porto vs SC Braga on day 22 of March?",
            ["FC Porto vs SC Braga match report tactical analysis 2025/26"],
            today=date(2026, 3, 23),
        )
        match_context = built["match_context"]

        hits = [
            {
                "title": "Live Commentary - Braga vs FC Porto | 22.03.2026 - Sky Sports",
                "body": "Portuguese Primeira Liga match Braga vs FC Porto 22.03.2026. Preview and stats followed by live commentary, video highlights and match report.",
                "href": "https://www.skysports.com/football/braga-vs-fc-porto/537516",
            },
            {
                "title": "Braga vs. FC Porto (Mar 22, 2026) Live Score - ESPN",
                "body": "Braga 1-2 FC Porto final score from March 22, 2026.",
                "href": "https://www.espn.com/soccer/match/_/gameId/750487",
            },
            {
                "title": "FC Porto 2-1 Braga (Nov 2, 2025) Final Score - ESPN",
                "body": "Game summary of the FC Porto vs. Braga game, final score 2-1, from November 2, 2025.",
                "href": "https://www.espn.com/soccer/match/_/gameId/750329/braga-fc-porto",
            },
            {
                "title": "FC Porto vs SC Braga volleyball result",
                "body": "Volleyball match between FC Porto and SC Braga.",
                "href": "https://www.sofascore.com/volleyball/match/fc-porto-sc-braga/OhBcsXmJc",
            },
            {
                "title": "Sporting Braga live score, schedule & player stats",
                "body": "Sporting Braga live score, fixtures, player ratings and statistics.",
                "href": "https://www.sofascore.com/football/team/sporting-braga/2999",
            },
        ]

        verified = verify_match_hits(hits, match_context, today=date(2026, 3, 23))

        self.assertTrue(verified["match_identity_verified"])
        self.assertTrue(verified["narrative_coverage_available"])
        self.assertTrue(verified["match_result_verified"])
        self.assertEqual(verified["verified_score"], "FC Porto 2-1 SC Braga")
        self.assertEqual(len(verified["accepted_hits"]), 1)

        rejected_reasons = {hit["reason"] for hit in verified["rejected_hits"]}
        self.assertIn("wrong_or_missing_date", rejected_reasons)
        self.assertIn("non_football_result", rejected_reasons)
        self.assertIn("generic_team_page", rejected_reasons)

    def test_context_only_hits_do_not_unlock_match_report(self):
        built = build_recent_match_search(
            "How was the game between FC Porto vs SC Braga on day 22 of March?",
            ["FC Porto vs SC Braga match report tactical analysis 2025/26"],
            today=date(2026, 3, 23),
        )
        match_context = built["match_context"]

        hits = [
            {
                "title": "FC Porto fans boo despite Braga win as pressure rises on coach",
                "body": "March 22, 2026: FC Porto beat SC Braga, but supporters booed and pressure is rising around the coach.",
                "href": "https://www.goal.com/en/fc-porto-fans-boo",
                "locale": "en",
                "source_tier": "english_fallback",
            }
        ]

        verified_match = verify_match_hits(hits, match_context, today=date(2026, 3, 23))
        verified_context = verify_context_hits(hits, match_context, today=date(2026, 3, 23))

        self.assertTrue(verified_match["match_identity_verified"])
        self.assertFalse(verified_match["narrative_coverage_available"])
        self.assertFalse(match_report_can_answer(verified_match))
        self.assertTrue(verified_context["context_coverage_available"])
        self.assertEqual(len(verified_context["accepted_hits"]), 1)

    def test_refusal_message_uses_exact_date_and_disallows_guessing(self):
        built = build_recent_match_search(
            "How was the game between FC Porto vs SC Braga on day 22 of March?",
            ["FC Porto vs SC Braga match report tactical analysis 2025/26"],
            today=date(2026, 3, 23),
        )
        verified_match = {
            **built["match_context"],
            "match_identity_verified": False,
            "narrative_coverage_available": False,
            "verified_score": None,
        }

        message = build_match_report_refusal(verified_match)
        self.assertIn("FC Porto", message)
        self.assertIn("SC Braga", message)
        self.assertIn("March 22, 2026", message)
        self.assertIn("without guessing", message)
        self.assertIn("local or English-language coverage", message)
        self.assertFalse(match_report_can_answer(verified_match))


if __name__ == "__main__":
    unittest.main()
