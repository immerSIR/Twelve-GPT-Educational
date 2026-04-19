import unittest
from datetime import date
from unittest.mock import patch

from utils.search import (
    build_match_context_from_plan,
    build_match_report_refusal,
    normalise_query_plan,
    resolve_query_date,
    search_multi,
    verify_match_hits,
)


class MultilingualLocaleTests(unittest.TestCase):
    def test_portuguese_query_prefers_portuguese_locale(self):
        plan = normalise_query_plan(
            {

                "user_language": "pt",
                "answer_language": "pt",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "FC Porto", "type": "club"},
                    {"name": "SC Braga", "type": "club"},
                ],
                "competition_country": "Portugal",
                "search_locales": ["pt", "en"],
                "entity_aliases": {
                    "FC Porto": ["Porto"],
                    "SC Braga": ["Braga", "Sporting Braga"],
                },
                "search_query_batches": [
                    {"locale": "pt", "queries": ["FC Porto vs SC Braga 22 março 2026 crónica"]},
                    {"locale": "en", "queries": ["FC Porto vs SC Braga March 22 2026 match report"]},
                ],
            },
            "Como foi o jogo entre FC Porto e SC Braga no dia 22 de março?",
            today=date(2026, 3, 23),
        )

        self.assertEqual(plan["answer_language"], "pt")
        self.assertEqual(plan["search_locales"][0], "pt-PT")
        self.assertEqual(plan["search_query_batches"][0]["locale"], "pt-PT")

    def test_english_query_about_polish_match_prefers_polish_locale(self):
        plan = normalise_query_plan(
            {

                "user_language": "en",
                "answer_language": "en",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "Lech Poznan", "type": "club"},
                    {"name": "Legia Warsaw", "type": "club"},
                ],
                "competition_country": "Poland",
                "search_locales": ["pl-PL", "en"],
                "entity_aliases": {
                    "Lech Poznan": ["Lech Poznań"],
                    "Legia Warsaw": ["Legia Warszawa"],
                },
                "search_query_batches": [
                    {"locale": "pl-PL", "queries": ["Lech Poznań Legia Warszawa 22 marca 2026 relacja"]},
                    {"locale": "en", "queries": ["Lech Poznan vs Legia Warsaw March 22 2026 match report"]},
                ],
            },
            "How was Lech Poznan vs Legia Warsaw on March 22?",
            today=date(2026, 3, 23),
        )

        self.assertEqual(plan["answer_language"], "en")
        self.assertEqual(plan["search_locales"][0], "pl-PL")

    def test_egyptian_match_prefers_arabic_locale(self):
        plan = normalise_query_plan(
            {

                "user_language": "en",
                "answer_language": "en",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "Al Ahly", "type": "club"},
                    {"name": "Zamalek", "type": "club"},
                ],
                "competition_country": "Egypt",
                "search_locales": ["ar", "en"],
                "entity_aliases": {
                    "Al Ahly": ["الأهلي"],
                    "Zamalek": ["الزمالك"],
                },
                "search_query_batches": [
                    {"locale": "ar", "queries": ["الأهلي الزمالك 22 مارس 2026 تقرير مباراة"]},
                    {"locale": "en", "queries": ["Al Ahly vs Zamalek March 22 2026 match report"]},
                ],
            },
            "How was Al Ahly vs Zamalek on March 22?",
            today=date(2026, 3, 23),
        )

        self.assertEqual(plan["search_locales"][0], "ar-EG")

    def test_resolve_query_date_portuguese(self):
        resolved = resolve_query_date(
            "Como foi o jogo entre FC Porto e SC Braga no dia 22 de março?",
            today=date(2026, 3, 23),
            languages=["pt"],
        )
        self.assertEqual(resolved, "2026-03-22")

    def test_resolve_query_date_polish(self):
        resolved = resolve_query_date(
            "Jak wygladal mecz Lech Poznan z Legia Warszawa 22 marca?",
            today=date(2026, 3, 23),
            languages=["pl"],
        )
        self.assertEqual(resolved, "2026-03-22")

    def test_default_match_report_queries_include_reaction_terms(self):
        plan = normalise_query_plan(
            {

                "user_language": "en",
                "answer_language": "en",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "FC Porto", "type": "club"},
                    {"name": "SC Braga", "type": "club"},
                ],
                "competition_country": "Portugal",
                "search_locales": ["en"],
                "entity_aliases": {},
                "search_query_batches": [],
            },
            "How was FC Porto vs SC Braga on March 22?",
            today=date(2026, 3, 23),
        )

        reaction_queries = next(
            batch["queries"]
            for batch in plan["search_query_batches"]
            if batch["locale"] == "en" and batch["query_category"] == "post_match_reaction"
        )
        context_queries = next(
            batch["queries"]
            for batch in plan["search_query_batches"]
            if batch["locale"] == "en" and batch["query_category"] == "context_sentiment"
        )
        self.assertTrue(any("reaction" in query or "opinion" in query for query in reaction_queries))
        self.assertTrue(any("fan reaction" in query or "coach under pressure" in query for query in context_queries))

    def test_same_locale_multi_category_batches_survive_normalisation(self):
        plan = normalise_query_plan(
            {

                "user_language": "pt",
                "answer_language": "pt",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "FC Porto", "type": "club"},
                    {"name": "SC Braga", "type": "club"},
                ],
                "competition_country": "Portugal",
                "search_locales": ["pt-PT"],
                "entity_aliases": {},
                "search_query_batches": [
                    {
                        "locale": "pt-PT",
                        "query_category": "match_narrative",
                        "queries": ["FC Porto vs SC Braga 22 março 2026 crónica"],
                    },
                    {
                        "locale": "pt-PT",
                        "query_category": "context_sentiment",
                        "queries": ["FC Porto adeptos reação ambiente 2025/26"],
                    },
                ],
            },
            "Como foi o jogo entre FC Porto e SC Braga no dia 22 de março?",
            today=date(2026, 3, 23),
        )

        categories = [
            batch["query_category"]
            for batch in plan["search_query_batches"]
            if batch["locale"] == "pt-PT"
        ]
        self.assertIn("match_narrative", categories)
        self.assertIn("context_sentiment", categories)
        self.assertIn("post_match_reaction", categories)

    def test_verify_match_hits_handles_portuguese_sources(self):
        plan = normalise_query_plan(
            {

                "user_language": "pt",
                "answer_language": "pt",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "FC Porto", "type": "club"},
                    {"name": "SC Braga", "type": "club"},
                ],
                "competition_country": "Portugal",
                "search_locales": ["pt-PT", "en"],
                "entity_aliases": {
                    "FC Porto": ["Porto"],
                    "SC Braga": ["Braga", "Sporting Braga"],
                },
                "search_query_batches": [
                    {"locale": "pt-PT", "queries": ["FC Porto vs SC Braga 22 março 2026 crónica"]},
                    {"locale": "en", "queries": ["FC Porto vs SC Braga March 22 2026 match report"]},
                ],
            },
            "Como foi o jogo entre FC Porto e SC Braga no dia 22 de março?",
            today=date(2026, 3, 23),
        )
        match_context = build_match_context_from_plan(
            plan,
            fallback_query="Como foi o jogo entre FC Porto e SC Braga no dia 22 de março?",
        )

        hits = [
            {
                "title": "Crónica FC Porto 2-1 SC Braga",
                "body": "No dia 22 de março de 2026, o FC Porto venceu o SC Braga por 2-1. A crónica descreveu pressão alta, mudanças táticas e um final intenso.",
                "href": "https://www.ojogo.pt/futebol/1a-liga/noticias/cronica-fc-porto-sc-braga-123",
                "locale": "pt-PT",
                "source_tier": "curated_local",
            },
            {
                "title": "Reações e notas: FC Porto 2-1 Sporting Braga - Record",
                "body": "22/03/2026: FC Porto 2-1 Sporting Braga. Reações, opinião ao jogo e relato da partida.",
                "href": "https://www.record.pt/futebol/futebol-nacional/liga-betclic/fc-porto/detalhe/fc-porto-sporting-braga-2-1",
                "locale": "pt-PT",
                "source_tier": "curated_local",
            },
            {
                "title": "FC Porto 2-1 SC Braga (02/11/2025)",
                "body": "Resumo do jogo do FC Porto contra o SC Braga em 2 de novembro de 2025.",
                "href": "https://www.record.pt/futebol/futebol-nacional/liga-betclic/fc-porto/detalhe/jogo-antigo",
                "locale": "pt-PT",
                "source_tier": "curated_local",
            },
            {
                "title": "FC Porto vs SC Braga voleibol",
                "body": "Resultado do jogo de voleibol entre FC Porto e SC Braga.",
                "href": "https://www.sofascore.com/volleyball/match/fc-porto-sc-braga/abc",
                "locale": "pt-PT",
                "source_tier": "curated_local",
            },
            {
                "title": "Sporting Braga live score, schedule & player stats",
                "body": "Sporting Braga live score, fixtures, player ratings and statistics.",
                "href": "https://www.sofascore.com/football/team/sporting-braga/2999",
                "locale": "pt-PT",
                "source_tier": "curated_local",
            },
        ]

        verified = verify_match_hits(hits, match_context, today=date(2026, 3, 23))

        self.assertTrue(verified["match_identity_verified"])
        self.assertTrue(verified["narrative_coverage_available"])
        self.assertEqual(verified["verified_score"], "FC Porto 2-1 SC Braga")
        self.assertEqual(verified["verified_source_language"], "pt")
        rejected_reasons = {hit["reason"] for hit in verified["rejected_hits"]}
        self.assertIn("wrong_or_missing_date", rejected_reasons)
        self.assertIn("non_football_result", rejected_reasons)
        self.assertIn("generic_team_page", rejected_reasons)

    @patch("utils.search.search_internet")
    def test_search_multi_prefers_curated_local_before_english_fallback(self, mock_search_internet):
        plan = normalise_query_plan(
            {

                "user_language": "pt",
                "answer_language": "pt",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "FC Porto", "type": "club"},
                    {"name": "SC Braga", "type": "club"},
                ],
                "competition_country": "Portugal",
                "search_locales": ["pt-PT", "en"],
                "entity_aliases": {
                    "FC Porto": ["Porto"],
                    "SC Braga": ["Braga", "Sporting Braga"],
                },
                "search_query_batches": [
                    {"locale": "pt-PT", "queries": ["FC Porto vs SC Braga 22 março 2026 crónica"]},
                    {"locale": "en", "queries": ["FC Porto vs SC Braga March 22 2026 match report"]},
                ],
            },
            "Como foi o jogo entre FC Porto e SC Braga no dia 22 de março?",
            today=date(2026, 3, 23),
        )
        match_context = build_match_context_from_plan(plan, fallback_query="FC Porto vs SC Braga")

        def side_effect(query, locale="en", source_tier="english_fallback"):
            lowered = query.lower()
            if locale == "pt-PT" and "fc porto" in lowered and "adept" not in lowered and "reac" not in lowered and "confer" not in lowered:
                return {
                    "answer": "Crónica: FC Porto 2-1 SC Braga em 22/03/2026.",
                    "citations": ["https://www.ojogo.pt/futebol/1a-liga/noticias/cronica-fc-porto-sc-braga-123"],
                    "hits": [
                        {
                            "title": "Crónica FC Porto 2-1 SC Braga",
                            "body": "22/03/2026: FC Porto 2-1 SC Braga. Crónica e análise tática.",
                            "href": "https://www.ojogo.pt/futebol/1a-liga/noticias/cronica-fc-porto-sc-braga-123",
                            "locale": "pt-PT",
                        }
                    ],
                    "provider": "DuckDuckGo",
                }
            return {
                "answer": "No results found.",
                "citations": [],
                "hits": [],
                "provider": "DuckDuckGo",
            }

        mock_search_internet.side_effect = side_effect
        result = search_multi(plan["search_query_batches"], match_context=match_context)

        self.assertEqual(result["primary_match_locale"], "pt-PT")
        self.assertEqual(result["source_tier"], "curated_local")
        self.assertEqual(result["verified_match"]["winning_locale"], "pt-PT")
        self.assertEqual(len(result["locale_attempts"]), len(plan["search_query_batches"]))
        self.assertTrue(result["evidence_blocks"]["match_narrative"])

    @patch("utils.search.search_internet")
    def test_search_multi_reports_open_web_local_for_uncurated_locale(self, mock_search_internet):
        plan = normalise_query_plan(
            {

                "user_language": "en",
                "answer_language": "en",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "Dinamo Zagreb", "type": "club"},
                    {"name": "Hajduk Split", "type": "club"},
                ],
                "competition_country": "Croatia",
                "search_locales": ["hr", "en"],
                "entity_aliases": {},
                "search_query_batches": [
                    {"locale": "hr", "queries": ["Dinamo Zagreb Hajduk Split 22 ozujka 2026 match report"]},
                    {"locale": "en", "queries": ["Dinamo Zagreb vs Hajduk Split March 22 2026 match report"]},
                ],
            },
            "How was Dinamo Zagreb vs Hajduk Split on March 22?",
            today=date(2026, 3, 23),
        )
        match_context = build_match_context_from_plan(plan, fallback_query="Dinamo Zagreb vs Hajduk Split")

        def side_effect(query, locale="en", source_tier="english_fallback"):
            if locale == "hr" and "match report" in query.lower():
                return {
                    "answer": "Dinamo Zagreb 2-1 Hajduk Split match report 22/03/2026.",
                    "citations": ["https://sportske.jutarnji.hr/example"],
                    "hits": [
                        {
                            "title": "Dinamo Zagreb 2-1 Hajduk Split match report",
                            "body": "22/03/2026: Dinamo Zagreb 2-1 Hajduk Split. Match report and tactical analysis.",
                            "href": "https://sportske.jutarnji.hr/example",
                            "locale": "hr",
                        }
                    ],
                    "provider": "DuckDuckGo",
                }
            return {
                "answer": "No results found.",
                "citations": [],
                "hits": [],
                "provider": "DuckDuckGo",
            }

        mock_search_internet.side_effect = side_effect
        result = search_multi(plan["search_query_batches"], match_context=match_context)

        self.assertEqual(result["primary_match_locale"], "hr")
        self.assertEqual(result["source_tier"], "open_web_local")
        self.assertEqual(result["verified_match"]["source_tier"], "open_web_local")
        self.assertEqual(result["verified_match"]["verified_source_language"], "hr")

    @patch("utils.search.search_internet")
    def test_search_multi_combines_match_and_context_evidence(self, mock_search_internet):
        plan = normalise_query_plan(
            {

                "user_language": "en",
                "answer_language": "en",
                "absolute_date": "2026-03-22",
                "entities": [
                    {"name": "FC Porto", "type": "club"},
                    {"name": "SC Braga", "type": "club"},
                ],
                "competition_country": "Portugal",
                "search_locales": ["pt-PT", "en"],
                "entity_aliases": {
                    "FC Porto": ["Porto"],
                    "SC Braga": ["Braga", "Sporting Braga"],
                },
                "search_query_batches": [
                    {
                        "locale": "pt-PT",
                        "query_category": "match_narrative",
                        "queries": ["FC Porto vs SC Braga 22 março 2026 crónica"],
                    },
                    {
                        "locale": "pt-PT",
                        "query_category": "context_sentiment",
                        "queries": ["FC Porto adeptos reação ambiente 2025/26"],
                    },
                ],
            },
            "How was FC Porto vs SC Braga on March 22?",
            today=date(2026, 3, 23),
        )
        match_context = build_match_context_from_plan(plan, fallback_query="FC Porto vs SC Braga")

        def side_effect(query, locale="en", source_tier="english_fallback"):
            lowered = query.lower()
            if "fc porto" in lowered and "adept" not in lowered and "reac" not in lowered and "confer" not in lowered:
                return {
                    "answer": "Crónica: FC Porto 2-1 SC Braga em 22/03/2026.",
                    "citations": ["https://www.ojogo.pt/cronica-fc-porto-sc-braga"],
                    "hits": [
                        {
                            "title": "Crónica FC Porto 2-1 SC Braga",
                            "body": "22/03/2026: FC Porto 2-1 SC Braga. Crónica e análise tática.",
                            "href": "https://www.ojogo.pt/cronica-fc-porto-sc-braga",
                            "locale": "pt-PT",
                        }
                    ],
                    "provider": "DuckDuckGo",
                }
            if "adept" in lowered or "atmosf" in lowered:
                return {
                    "answer": "Adeptos do FC Porto assobiaram apesar da vitória.",
                    "citations": ["https://www.abola.pt/fc-porto-adeptos-assobios"],
                    "hits": [
                        {
                            "title": "Assobios no Dragão apesar da vitória",
                            "body": "Março de 2026: os adeptos do FC Porto mostraram frustração e aumentaram a pressão sobre o treinador.",
                            "href": "https://www.abola.pt/fc-porto-adeptos-assobios",
                            "locale": "pt-PT",
                        }
                    ],
                    "provider": "DuckDuckGo",
                }
            return {
                "answer": "No results found.",
                "citations": [],
                "hits": [],
                "provider": "DuckDuckGo",
            }

        mock_search_internet.side_effect = side_effect
        result = search_multi(plan["search_query_batches"], match_context=match_context)

        self.assertTrue(result["verified_match"]["narrative_coverage_available"])
        self.assertTrue(result["verified_match"]["context_coverage_available"])
        self.assertEqual(len(result["verified_match"]["context_hits"]), 1)
        self.assertIn("context_sentiment", {attempt["query_category"] for attempt in result["locale_attempts"]})

    def test_refusal_lists_locales_attempted(self):
        message = build_match_report_refusal(
            {
                "team_a": "FC Porto",
                "team_b": "SC Braga",
                "requested_date_display": "March 22, 2026",
                "match_identity_verified": False,
                "narrative_coverage_available": False,
                "searched_locales": ["pt-PT", "en"],
            }
        )

        self.assertIn("March 22, 2026", message)
        self.assertIn("pt-PT, en", message)


if __name__ == "__main__":
    unittest.main()
