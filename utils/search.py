"""
Internet search utilities for the Full Internet Analyst.
Supports Perplexity Sonar API (primary) with DuckDuckGo fallback.

Search functions return raw web findings plus optional match-verification metadata
for locale-aware fixture queries that require exact date grounding.
"""

from collections import Counter
from datetime import date, datetime, timedelta
import re
import unicodedata
from urllib.parse import urlparse

from openai import OpenAI

from settings import PERPLEXITY_API_KEY, USE_PERPLEXITY

PERPLEXITY_BASE_URL = "https://api.perplexity.ai"
PERPLEXITY_MODEL = "sonar"

GLOBAL_ENGLISH_JOURNALISM_DOMAINS = [
    "theathletic.com",
    "theguardian.com",
    "bbc.com",
    "skysports.com",
    "espn.com",
    "goal.com",
    "fourfourtwo.com",
    "optaanalyst.com",
    "cbssports.com",
    "90min.com",
    "talksport.com",
    "planetfootball.com",
    "football365.com",
    "independent.co.uk",
    "worldsoccertalk.com",
]

GLOBAL_STATS_DOMAINS = [
    "sofascore.com",
    "fotmob.com",
    "fbref.com",
    "transfermarkt.com",
    "besoccer.com",
]

CURATED_LOCAL_DOMAINS = {
    "pt-PT": [
        "abola.pt",
        "ojogo.pt",
        "record.pt",
        "maisfutebol.iol.pt",
        "zerozero.pt",
        "sicnoticias.pt",
    ],
    "pl-PL": [
        "meczyki.pl",
        "weszlo.com",
        "sport.tvp.pl",
        "przegladsportowy.onet.pl",
        "gol24.pl",
    ],
    "en-GB": GLOBAL_ENGLISH_JOURNALISM_DOMAINS,
    "es-ES": [
        "marca.com",
        "as.com",
        "mundodeportivo.com",
        "sport.es",
        "relevo.com",
    ],
    "de-DE": [
        "kicker.de",
        "sport1.de",
        "spox.com",
        "ran.de",
        "transfermarkt.de",
    ],
    "it-IT": [
        "gazzetta.it",
        "corrieredellosport.it",
        "tuttosport.com",
        "sportmediaset.mediaset.it",
    ],
    "fr-FR": [
        "lequipe.fr",
        "sofoot.com",
        "rmcsport.bfmtv.com",
        "maxifoot.fr",
    ],
    "nl-NL": [
        "vi.nl",
        "nos.nl",
        "ad.nl",
        "telegraaf.nl",
    ],
    "tr-TR": [
        "fanatik.com.tr",
        "fotomac.com.tr",
        "ntvspor.net",
        "sporx.com",
    ],
    "ar-EG": [
        "filgoal.com",
        "yallakora.com",
        "btolat.com",
        "kooora.com",
        "kingfut.com",
    ],
}

COUNTRY_TO_PRIMARY_LOCALE = {
    "england": "en-GB",
    "egypt": "ar-EG",
    "france": "fr-FR",
    "germany": "de-DE",
    "italy": "it-IT",
    "netherlands": "nl-NL",
    "poland": "pl-PL",
    "portugal": "pt-PT",
    "spain": "es-ES",
    "turkey": "tr-TR",
    "uk": "en-GB",
    "united kingdom": "en-GB",
}

LOCALE_TO_DDG_REGION = {
    "ar-EG": "eg-ar",
    "de-DE": "de-de",
    "en": "wt-wt",
    "en-GB": "uk-en",
    "es-ES": "es-es",
    "fr-FR": "fr-fr",
    "it-IT": "it-it",
    "nl-NL": "nl-nl",
    "pl-PL": "pl-pl",
    "pt-PT": "pt-pt",
    "tr-TR": "tr-tr",
}

LANGUAGE_TO_DEFAULT_LOCALE = {
    "ar": "ar-EG",
    "de": "de-DE",
    "en": "en",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "pt": "pt-PT",
    "tr": "tr-TR",
}

TRUSTED_DOMAINS = sorted(
    set(GLOBAL_ENGLISH_JOURNALISM_DOMAINS)
    | set(GLOBAL_STATS_DOMAINS)
    | {domain for domains in CURATED_LOCAL_DOMAINS.values() for domain in domains}
)

_JOURNALISM_DOMAINS = set(GLOBAL_ENGLISH_JOURNALISM_DOMAINS) | {
    domain for domains in CURATED_LOCAL_DOMAINS.values() for domain in domains
}
_STATS_DOMAINS = set(GLOBAL_STATS_DOMAINS)

_NON_FOOTBALL_KEYWORDS = {
    "baseball",
    "basketball",
    "basquete",
    "handball",
    "handebol",
    "hockey",
    "koszykowka",
    "koszykówka",
    "rugby",
    "siatkowka",
    "siatkówka",
    "tennis",
    "voleibol",
    "volleyball",
}

_NARRATIVE_KEYWORDS = {
    "ar": ["تقرير", "مباراة", "تعليق مباشر", "مؤتمر صحفي", "تحليل", "ملخص", "ردود فعل", "آراء"],
    "de": ["spielbericht", "live kommentar", "pressekonferenz", "analyse", "bericht", "reaktion", "meinung", "fazit"],
    "en": ["match report", "live commentary", "live text commentary", "press conference", "post match", "analysis", "reaction", "verdict", "opinion", "player ratings"],
    "es": ["crónica", "cronica", "comentario en directo", "rueda de prensa", "análisis", "analisis", "reacción", "reaccion", "opinión", "opinion", "valoraciones"],
    "fr": ["compte-rendu", "compte rendu", "direct commenté", "conférence de presse", "analyse", "réaction", "reaction", "avis"],
    "it": ["cronaca", "diretta", "conferenza stampa", "analisi", "pagelle", "reazioni", "giudizio"],
    "nl": ["wedstrijdverslag", "liveblog", "persconferentie", "analyse", "reactie", "oordeel"],
    "pl": ["relacja", "komentarz na żywo", "komentarz na zywo", "konferencja prasowa", "analiza", "pomeczowy", "reakcje", "opinie", "oceny"],
    "pt": ["crónica", "cronica", "relato", "comentário ao vivo", "comentario ao vivo", "conferência de imprensa", "analise", "análise", "reação", "reacao", "opinião", "opiniao", "notas", "pós-jogo", "pos-jogo", "pos jogo"],
    "tr": ["maç raporu", "mac raporu", "canlı anlatım", "canli anlatim", "basın toplantısı", "basin toplantisi", "analiz", "yorum", "tepki"],
}

_TEAM_PREFIXES = {"ac", "afc", "cf", "cd", "fc", "sc"}
_TEAM_ALIAS_OVERRIDES = {
    "fc porto": {"porto"},
    "porto": {"fc porto"},
    "sc braga": {"braga", "sporting braga"},
    "sporting braga": {"braga", "sc braga"},
}

_MONTH_LOOKUP = {
    "january": 1,
    "janeiro": 1,
    "janvier": 1,
    "gennaio": 1,
    "januar": 1,
    "januari": 1,
    "enero": 1,
    "ocak": 1,
    "styczen": 1,
    "stycznia": 1,
    "يناير": 1,
    "february": 2,
    "fevereiro": 2,
    "fevrier": 2,
    "febbraio": 2,
    "februar": 2,
    "februari": 2,
    "febrero": 2,
    "subat": 2,
    "luty": 2,
    "lutego": 2,
    "فبراير": 2,
    "march": 3,
    "marco": 3,
    "mars": 3,
    "marzo": 3,
    "marz": 3,
    "maart": 3,
    "mart": 3,
    "marzec": 3,
    "marca": 3,
    "مارس": 3,
    "april": 4,
    "abril": 4,
    "avril": 4,
    "aprile": 4,
    "nisan": 4,
    "kwiecien": 4,
    "kwietnia": 4,
    "ابريل": 4,
    "أبريل": 4,
    "may": 5,
    "maio": 5,
    "mai": 5,
    "maggio": 5,
    "mayo": 5,
    "mei": 5,
    "mayis": 5,
    "maj": 5,
    "maja": 5,
    "مايو": 5,
    "june": 6,
    "junho": 6,
    "juin": 6,
    "giugno": 6,
    "juni": 6,
    "junio": 6,
    "haziran": 6,
    "czerwiec": 6,
    "czerwca": 6,
    "يونيو": 6,
    "july": 7,
    "julho": 7,
    "juillet": 7,
    "luglio": 7,
    "juli": 7,
    "julio": 7,
    "temmuz": 7,
    "lipiec": 7,
    "lipca": 7,
    "يوليو": 7,
    "august": 8,
    "agosto": 8,
    "aout": 8,
    "augustus": 8,
    "agustos": 8,
    "sierpien": 8,
    "sierpnia": 8,
    "اغسطس": 8,
    "أغسطس": 8,
    "september": 9,
    "setembro": 9,
    "septembre": 9,
    "settembre": 9,
    "septiembre": 9,
    "eylul": 9,
    "wrzesien": 9,
    "wrzesnia": 9,
    "سبتمبر": 9,
    "october": 10,
    "outubro": 10,
    "octobre": 10,
    "ottobre": 10,
    "oktober": 10,
    "octubre": 10,
    "ekim": 10,
    "pazdziernik": 10,
    "pazdziernika": 10,
    "اكتوبر": 10,
    "أكتوبر": 10,
    "november": 11,
    "novembro": 11,
    "novembre": 11,
    "noviembre": 11,
    "kasim": 11,
    "listopad": 11,
    "listopada": 11,
    "نوفمبر": 11,
    "december": 12,
    "dezembro": 12,
    "decembre": 12,
    "dicembre": 12,
    "diciembre": 12,
    "decembrie": 12,
    "december": 12,
    "aralik": 12,
    "grudzien": 12,
    "grudnia": 12,
    "ديسمبر": 12,
}
_MONTH_PATTERN = "|".join(_MONTH_LOOKUP)


def _unique(values: list) -> list:
    seen = set()
    deduped = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _normalise_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _normalise_key(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return re.sub(r"[\W_]+", " ", folded, flags=re.UNICODE).strip()


def normalise_locale(locale: str | None) -> str:
    if not locale:
        return "en"
    cleaned = locale.replace("_", "-").strip()
    if not cleaned:
        return "en"
    parts = cleaned.split("-")
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def locale_language(locale: str | None) -> str:
    return normalise_locale(locale).split("-")[0]


def default_search_locale_for_language(language: str | None) -> str:
    language = locale_language(language)
    return LANGUAGE_TO_DEFAULT_LOCALE.get(language, language or "en")


def locale_from_country(country: str | None) -> str | None:
    if not country:
        return None
    return COUNTRY_TO_PRIMARY_LOCALE.get(_normalise_key(country))


def _extract_domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.replace("www.", "").lower()


def format_absolute_date(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        value = date.fromisoformat(value)
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def _prefer_dates_from(query: str) -> str:
    lower_query = _normalise_key(query)
    future_keywords = {
        "amanha",
        "demain",
        "jutro",
        "mañana",
        "next",
        "preview",
        "tomorrow",
        "upcoming",
        "will",
    }
    return "future" if any(keyword in lower_query for keyword in future_keywords) else "past"


def _search_dates(text: str, base_date: date, languages: list[str] | None = None) -> list[date]:
    try:
        from dateparser.search import search_dates
    except Exception:
        return []

    parsed = search_dates(
        text,
        languages=languages or None,
        settings={
            "PREFER_DATES_FROM": _prefer_dates_from(text),
            "RELATIVE_BASE": datetime.combine(base_date, datetime.min.time()),
            "RETURN_AS_TIMEZONE_AWARE": False,
        },
    )
    if not parsed:
        return []
    return [dt.date() for _, dt in parsed]


def _infer_missing_year(month: int, day: int, query: str, today: date) -> int | None:
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return None

    lower_query = _normalise_key(query)
    future_intent = any(
        phrase in lower_query
        for phrase in ("tomorrow", "next", "preview", "upcoming", "will", "going to")
    )

    if future_intent and candidate < today:
        return today.year + 1
    if not future_intent and candidate > today:
        return today.year - 1
    return today.year


def resolve_query_date(
    query: str,
    today: date | None = None,
    languages: list[str] | None = None,
) -> str | None:
    """
    Resolve a user-specified recent-fixture date to an absolute ISO date.

    Uses dateparser when available for multilingual month names and relative dates,
    with the existing English fallback patterns preserved for robustness.
    """

    today = today or date.today()
    parsed_dates = _search_dates(query, today, languages=languages)
    if parsed_dates:
        return parsed_dates[0].isoformat()

    lower_query = _normalise_key(query)

    if "yesterday" in lower_query:
        return (today - timedelta(days=1)).isoformat()
    if "today" in lower_query:
        return today.isoformat()
    if "tomorrow" in lower_query:
        return (today + timedelta(days=1)).isoformat()

    day_first = re.search(
        rf"\b(?:on\s+day\s+|day\s+|no\s+dia\s+|dia\s+|dnia\s+)?(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:\s+of|\s+de|\s+do)?\s+(?P<month>{_MONTH_PATTERN})(?:\s+(?P<year>\d{{4}}))?\b",
        lower_query,
    )
    month_first = re.search(
        rf"\b(?P<month>{_MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,\s*|\s+)?(?P<year>\d{{4}})?\b",
        lower_query,
    )
    match = day_first or month_first
    if not match:
        return None

    month = _MONTH_LOOKUP[match.group("month")]
    day = int(match.group("day"))
    year = match.group("year")
    if year is None:
        inferred_year = _infer_missing_year(month, day, query, today=today)
        if inferred_year is None:
            return None
        year = inferred_year
    else:
        year = int(year)

    try:
        return date(int(year), month, day).isoformat()
    except ValueError:
        return None


def _trim_team_label(text: str) -> str:
    text = _normalise_space(text)
    text = re.sub(
        r"^(?:how|what|was|were|is|did|the|match|game|fixture|between|report|analysis)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.strip(" -,:;")
    return text


def extract_match_teams(search_queries: list, fallback_query: str = "") -> tuple[str | None, str | None]:
    """
    Extract two team names from classifier-built search queries or, failing that, the raw user query.
    """

    suffix_markers = (
        " match report",
        " tactical analysis",
        " player ratings",
        " performances",
        " final score",
        " live commentary",
        " live score",
        " post-match quotes",
        " press conference",
        " football analysis",
    )

    candidates = list(search_queries) + [fallback_query]
    for candidate in candidates:
        if not candidate:
            continue
        normalised = re.sub(r"\s+v(?:s\.?)?\s+", " vs ", candidate, flags=re.IGNORECASE)
        if " vs " not in normalised.lower():
            continue
        left, right = re.split(r"\s+vs\s+", normalised, maxsplit=1, flags=re.IGNORECASE)
        lower_right = right.lower()
        cut = len(right)
        for marker in suffix_markers:
            idx = lower_right.find(marker)
            if idx != -1:
                cut = min(cut, idx)
        team_a = _trim_team_label(left)
        team_b = _trim_team_label(right[:cut])
        if team_a and team_b:
            return team_a, team_b
    return None, None


def _team_aliases(team_name: str) -> set[str]:
    base = _normalise_key(team_name)
    if not base:
        return set()

    aliases = {base}
    aliases |= {_normalise_key(alias) for alias in _TEAM_ALIAS_OVERRIDES.get(base, set())}

    tokens = base.split()
    if tokens and tokens[0] in _TEAM_PREFIXES and len(tokens) > 1:
        aliases.add(" ".join(tokens[1:]))
    if tokens and tokens[0] == "sporting" and len(tokens) > 1:
        aliases.add(" ".join(tokens[1:]))

    return {alias for alias in aliases if alias}


def build_recent_match_search(
    query: str,
    search_queries: list,
    today: date | None = None,
    languages: list[str] | None = None,
) -> dict:
    """
    Replace loose season-level match-report queries with exact-date queries when the
    user asked about a specific recent fixture.
    """

    requested_date = resolve_query_date(query, today=today, languages=languages)
    team_a, team_b = extract_match_teams(search_queries, fallback_query=query)
    if not requested_date or not team_a or not team_b:
        return {
            "search_queries": search_queries,
            "match_context": None,
        }

    requested_date_obj = date.fromisoformat(requested_date)
    display_date = format_absolute_date(requested_date_obj)
    search_date = requested_date_obj.strftime("%B %d %Y").replace(" 0", " ")
    refined_queries = [
        f"{team_a} vs {team_b} {search_date} match report tactical analysis",
        f"{team_b} vs {team_a} {search_date} final score player ratings live commentary",
        f"{team_a} {team_b} {search_date} post-match quotes press conference",
    ]

    return {
        "search_queries": refined_queries,
        "match_context": {
            "strict_mode": True,
            "team_a": team_a,
            "team_b": team_b,
            "team_a_aliases": sorted(_team_aliases(team_a)),
            "team_b_aliases": sorted(_team_aliases(team_b)),
            "requested_date": requested_date,
            "requested_date_display": display_date,
            "requested_date_search": search_date,
        },
    }


def build_recent_match_retry_query(match_context: dict | None) -> str | None:
    if not match_context or not match_context.get("requested_date"):
        return None
    return (
        f"\"{match_context['team_a']}\" \"{match_context['team_b']}\" "
        f"\"{match_context.get('requested_date_search', match_context['requested_date_display'])}\" "
        f"live commentary match report final score"
    )


def _locale_domains(locale: str, source_tier: str) -> list[str] | None:
    if source_tier == "english_fallback":
        return GLOBAL_ENGLISH_JOURNALISM_DOMAINS + GLOBAL_STATS_DOMAINS
    if source_tier == "curated_local":
        curated = CURATED_LOCAL_DOMAINS.get(normalise_locale(locale), [])
        return curated + GLOBAL_STATS_DOMAINS
    return None


def _supplemental_domains_for_tier(source_tier: str) -> list[str]:
    return GLOBAL_STATS_DOMAINS if source_tier == "open_web_local" else []


def _default_source_tier(locale: str) -> str:
    locale = normalise_locale(locale)
    if locale in {"en", "en-GB"}:
        return "english_fallback"
    if locale in CURATED_LOCAL_DOMAINS:
        return "curated_local"
    return "open_web_local"


def _default_queries_for_locale(locale: str, query_type: str, entities: list, absolute_date: str | None) -> list[str]:
    names = [entity.get("name", "") for entity in entities if entity.get("name")]
    joined = " vs ".join(names[:2]) if len(names) >= 2 else " ".join(names) or "football"
    if query_type == "match_report" and absolute_date:
        language = locale_language(locale)
        team_a = names[0] if len(names) >= 1 else joined
        team_b = names[1] if len(names) >= 2 else ""
        locale_terms = {
            "en": [
                "match report tactical analysis",
                "post match reaction verdict player ratings",
                "opinion analysis how the game was judged",
            ],
            "pt": [
                "cronica analise tatica",
                "reacoes opiniao notas ao jogo",
                "analise pos jogo desempenho",
            ],
            "pl": [
                "relacja analiza taktyczna",
                "reakcje opinie oceny po meczu",
                "analiza pomeczowa ocena wystepu",
            ],
        }
        terms = locale_terms.get(language, locale_terms["en"])
        queries = [
            f"{team_a} vs {team_b} {absolute_date} {terms[0]}".strip(),
            f"{team_b} vs {team_a} {absolute_date} {terms[1]}".strip(),
            f"{team_a} {team_b} {absolute_date} {terms[2]}".strip(),
        ]
        return _unique(queries)
    if absolute_date:
        return [f"{joined} {absolute_date} football"]
    return [f"{joined} football"]


def _normalise_entity_aliases(entity_aliases: dict | None) -> dict[str, list[str]]:
    normalised = {}
    for name, aliases in (entity_aliases or {}).items():
        normalised[name] = _unique([name, *(aliases or [])])
    return normalised


def normalise_query_plan(raw_plan: dict | None, user_query: str, today: date | None = None) -> dict:
    """
    Validate and normalise the multilingual planner output into a stable
    internal contract for locale-aware retrieval.
    """

    today = today or date.today()
    raw_plan = raw_plan or {}

    query_type = raw_plan.get("query_type") or "match_report"
    user_language = (raw_plan.get("user_language") or "en").lower()
    answer_language = (raw_plan.get("answer_language") or user_language or "en").lower()
    competition_country = raw_plan.get("competition_country")
    entities = raw_plan.get("entities") or []
    entity_aliases = _normalise_entity_aliases(raw_plan.get("entity_aliases"))

    raw_locales = [
        default_search_locale_for_language(locale)
        if "-" not in normalise_locale(locale)
        else normalise_locale(locale)
        for locale in raw_plan.get("search_locales", [])
    ]
    country_locale = locale_from_country(competition_country)
    if country_locale and country_locale not in raw_locales:
        raw_locales.insert(0, country_locale)
    user_locale = default_search_locale_for_language(user_language)
    if user_locale not in raw_locales:
        raw_locales.append(user_locale)
    if "en" not in raw_locales:
        raw_locales.append("en")
    search_locales = _unique(raw_locales)

    absolute_date = raw_plan.get("absolute_date")
    if absolute_date:
        try:
            absolute_date = date.fromisoformat(absolute_date).isoformat()
        except ValueError:
            absolute_date = None
    if not absolute_date:
        absolute_date = resolve_query_date(
            user_query,
            today=today,
            languages=_unique([locale_language(locale) for locale in search_locales]),
        )

    raw_batches = raw_plan.get("search_query_batches") or []
    batches_by_locale = {}
    for batch in raw_batches:
        locale = batch.get("locale")
        locale = (
            default_search_locale_for_language(locale)
            if "-" not in normalise_locale(locale)
            else normalise_locale(locale)
        )
        queries = _unique([_normalise_space(query) for query in batch.get("queries", []) if query])
        if not locale or not queries:
            continue
        batches_by_locale[locale] = {
            "locale": locale,
            "queries": queries,
            "source_tier": batch.get("source_tier") or _default_source_tier(locale),
        }

    search_query_batches = []
    for locale in search_locales:
        batch = batches_by_locale.get(locale)
        if batch is None:
            batch = {
                "locale": locale,
                "queries": _default_queries_for_locale(locale, query_type, entities, absolute_date),
                "source_tier": _default_source_tier(locale),
            }
        search_query_batches.append(batch)

    return {
        "query_type": query_type,
        "user_language": user_language,
        "answer_language": answer_language,
        "absolute_date": absolute_date,
        "entities": entities,
        "competition_country": competition_country,
        "search_locales": search_locales,
        "entity_aliases": entity_aliases,
        "search_query_batches": search_query_batches,
    }


def build_match_context_from_plan(query_plan: dict, fallback_query: str = "") -> dict | None:
    if query_plan.get("query_type") != "match_report":
        return None

    team_names = [
        entity.get("name")
        for entity in query_plan.get("entities", [])
        if entity.get("name") and entity.get("type", "team") in {"club", "team", "national_team"}
    ]
    if len(team_names) < 2:
        fallback_queries = []
        for batch in query_plan.get("search_query_batches", []):
            fallback_queries.extend(batch.get("queries", []))
        extracted = extract_match_teams(fallback_queries, fallback_query=fallback_query)
        team_names = [name for name in extracted if name]
    if len(team_names) < 2:
        return None

    team_a, team_b = team_names[:2]
    alias_map = query_plan.get("entity_aliases", {})
    requested_date = query_plan.get("absolute_date")
    if not requested_date:
        return None

    team_a_aliases = _team_aliases(team_a) | {
        _normalise_key(alias) for alias in alias_map.get(team_a, [])
    }
    team_b_aliases = _team_aliases(team_b) | {
        _normalise_key(alias) for alias in alias_map.get(team_b, [])
    }

    return {
        "strict_mode": True,
        "team_a": team_a,
        "team_b": team_b,
        "team_a_aliases": sorted(team_a_aliases),
        "team_b_aliases": sorted(team_b_aliases),
        "requested_date": requested_date,
        "requested_date_display": format_absolute_date(requested_date),
        "requested_date_search": format_absolute_date(requested_date).replace(",", ""),
        "search_locales": query_plan.get("search_locales", []),
        "answer_language": query_plan.get("answer_language", "en"),
    }


def _text_contains_target_date(
    text: str,
    target_date: str,
    today: date | None = None,
    languages: list[str] | None = None,
) -> bool:
    if not target_date:
        return True

    target = date.fromisoformat(target_date)
    raw_text = (text or "").casefold()
    day = target.day
    month = target.month
    year = target.year
    month_full = target.strftime("%B").lower()
    month_short = target.strftime("%b").lower()

    patterns = [
        rf"\b{year}-{month:02d}-{day:02d}\b",
        rf"\b{day:02d}[./-]{month:02d}[./-]{year}\b",
        rf"\b{day}[./-]{month:02d}[./-]{year}\b",
        rf"\b{year}[./-]{month:02d}[./-]{day:02d}\b",
        rf"\b{month:02d}[./-]{day:02d}[./-]{year}\b",
        rf"\b{month}[./-]{day}[./-]{year}\b",
        rf"\b{month_full}\s+{day}(?:st|nd|rd|th)?(?:,\s*|\s+){year}\b",
        rf"\b{month_short}\.?\s+{day}(?:st|nd|rd|th)?(?:,\s*|\s+){year}\b",
        rf"\b{day}(?:st|nd|rd|th)?\s+(?:of\s+)?{month_full}(?:,\s*|\s+){year}\b",
        rf"\b{day}(?:st|nd|rd|th)?\s+{month_short}\.?(?:,\s*|\s+){year}\b",
    ]
    if any(re.search(pattern, raw_text) for pattern in patterns):
        return True

    parsed_dates = _search_dates(
        text,
        today or date.today(),
        languages=_unique([*(languages or []), "en"]),
    )
    return any(parsed == target for parsed in parsed_dates)


def _hit_text(hit: dict) -> str:
    return _normalise_space(f"{hit.get('title', '')} {hit.get('body', '')}")


def _text_mentions_aliases(text: str, aliases: set[str]) -> bool:
    haystack = _normalise_key(text)
    return any(alias in haystack for alias in aliases)


def _is_non_football_hit(hit: dict) -> bool:
    text = f"{_hit_text(hit)} {hit.get('href', '')}".lower()
    return any(keyword in text for keyword in _NON_FOOTBALL_KEYWORDS)


def _is_generic_team_page(hit: dict, team_a_aliases: set[str], team_b_aliases: set[str]) -> bool:
    text = _normalise_key(_hit_text(hit))
    href = (hit.get("href", "") or "").lower()
    generic_markers = [
        "live score schedule player stats",
        "live score fixtures player ratings",
        "live score fixtures player stats",
        "fixtures player ratings and statistics",
        "fixtures results squad",
        "team page",
        "player stats",
        "team stats",
    ]
    if not any(marker in text for marker in generic_markers) and "/team/" not in href:
        return False
    mentions_a = _text_mentions_aliases(text, team_a_aliases)
    mentions_b = _text_mentions_aliases(text, team_b_aliases)
    return mentions_a ^ mentions_b


def _extract_ordered_score(
    text: str, team_a: str, team_b: str, team_a_aliases: set[str], team_b_aliases: set[str]
) -> str | None:
    for match in re.finditer(
        r"(?P<left>[\w\u00C0-\u024F\u0600-\u06FF][\w\u00C0-\u024F\u0600-\u06FF .&'’/-]{1,80}?)\s+(?P<left_score>\d{1,2})\s*[-–:]\s*(?P<right_score>\d{1,2})\s+(?P<right>[\w\u00C0-\u024F\u0600-\u06FF][\w\u00C0-\u024F\u0600-\u06FF .&'’/-]{1,80})",
        text,
        flags=re.UNICODE,
    ):
        left = _normalise_key(match.group("left"))
        right = _normalise_key(match.group("right"))
        left_score = int(match.group("left_score"))
        right_score = int(match.group("right_score"))

        if _text_mentions_aliases(left, team_a_aliases) and _text_mentions_aliases(
            right, team_b_aliases
        ):
            return f"{team_a} {left_score}-{right_score} {team_b}"
        if _text_mentions_aliases(left, team_b_aliases) and _text_mentions_aliases(
            right, team_a_aliases
        ):
            return f"{team_a} {right_score}-{left_score} {team_b}"

    compact = _normalise_key(text)
    team_a_patterns = sorted(team_a_aliases, key=len, reverse=True)
    team_b_patterns = sorted(team_b_aliases, key=len, reverse=True)
    for team_a_alias in team_a_patterns:
        for team_b_alias in team_b_patterns:
            direct = re.search(
                rf"\b{re.escape(team_a_alias)}\b\s+(?P<left_score>\d{{1,2}})\s*[-–:]\s*(?P<right_score>\d{{1,2}})\s+\b{re.escape(team_b_alias)}\b",
                compact,
            )
            if direct:
                return (
                    f"{team_a} {int(direct.group('left_score'))}-{int(direct.group('right_score'))} {team_b}"
                )

            reverse = re.search(
                rf"\b{re.escape(team_b_alias)}\b\s+(?P<left_score>\d{{1,2}})\s*[-–:]\s*(?P<right_score>\d{{1,2}})\s+\b{re.escape(team_a_alias)}\b",
                compact,
            )
            if reverse:
                return (
                    f"{team_a} {int(reverse.group('right_score'))}-{int(reverse.group('left_score'))} {team_b}"
                )

    return None


def _is_narrative_hit(hit: dict, languages: list[str] | None = None) -> bool:
    text = _normalise_key(_hit_text(hit))
    domain = _extract_domain(hit.get("href", ""))
    source_tier = hit.get("source_tier")
    if domain in _STATS_DOMAINS:
        return False
    if domain not in _JOURNALISM_DOMAINS and source_tier != "open_web_local":
        return False

    keyword_languages = _unique([*(languages or []), locale_language(hit.get("locale")), "en"])
    keyword_pool = []
    for language in keyword_languages:
        keyword_pool.extend(_NARRATIVE_KEYWORDS.get(language, []))
    if any(_normalise_key(keyword) in text for keyword in keyword_pool):
        return True

    if "player ratings" in text or "pagelle" in text:
        return True
    if "analysis" in text and domain not in _STATS_DOMAINS:
        return True

    return False


def verify_match_hits(hits: list, match_context: dict | None, today: date | None = None) -> dict | None:
    if not match_context:
        return None

    today = today or date.today()
    team_a_aliases = set(match_context.get("team_a_aliases", []))
    team_b_aliases = set(match_context.get("team_b_aliases", []))
    requested_date = match_context.get("requested_date")
    team_a = match_context.get("team_a", "")
    team_b = match_context.get("team_b", "")
    languages = _unique(
        [locale_language(locale) for locale in match_context.get("search_locales", [])]
        + [match_context.get("answer_language", "en")]
    )

    accepted_hits = []
    rejected_hits = []
    score_counter = Counter()
    source_language_counter = Counter()

    for hit in hits:
        text = _hit_text(hit)
        if _is_non_football_hit(hit):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "non_football_result",
                }
            )
            continue
        if _is_generic_team_page(hit, team_a_aliases, team_b_aliases):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "generic_team_page",
                }
            )
            continue
        if not _text_mentions_aliases(text, team_a_aliases):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "missing_team_a",
                }
            )
            continue
        if not _text_mentions_aliases(text, team_b_aliases):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "missing_team_b",
                }
            )
            continue
        if requested_date and not _text_contains_target_date(
            f"{text} {hit.get('href', '')}",
            requested_date,
            today=today,
            languages=languages,
        ):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "wrong_or_missing_date",
                }
            )
            continue

        enriched_hit = {
            **hit,
            "domain": _extract_domain(hit.get("href", "")),
            "is_narrative": _is_narrative_hit(hit, languages=languages),
            "verified_source_language": locale_language(hit.get("locale") or hit.get("source_locale")),
        }
        accepted_hits.append(enriched_hit)
        if enriched_hit["verified_source_language"]:
            source_language_counter[enriched_hit["verified_source_language"]] += 1
        if score := _extract_ordered_score(
            text, team_a, team_b, team_a_aliases, team_b_aliases
        ):
            score_counter[score] += 1

    verified_score = score_counter.most_common(1)[0][0] if score_counter else None
    verified_source_language = (
        source_language_counter.most_common(1)[0][0] if source_language_counter else None
    )

    return {
        **match_context,
        "raw_hit_count": len(hits),
        "match_identity_verified": bool(accepted_hits),
        "match_result_verified": bool(verified_score),
        "narrative_coverage_available": any(hit["is_narrative"] for hit in accepted_hits),
        "verified_date": requested_date if accepted_hits else None,
        "verified_score": verified_score,
        "accepted_hits": accepted_hits,
        "rejected_hits": rejected_hits,
        "verified_source_language": verified_source_language,
    }


def match_report_can_answer(verified_match: dict | None) -> bool:
    if not verified_match:
        return True
    if not verified_match.get("strict_mode"):
        return True
    return bool(
        verified_match.get("match_identity_verified")
        and verified_match.get("narrative_coverage_available")
    )


def should_retry_match_report(verified_match: dict | None) -> bool:
    if not verified_match or not verified_match.get("strict_mode"):
        return False
    return bool(
        verified_match.get("raw_hit_count")
        and not verified_match.get("match_identity_verified")
    )


def build_match_report_refusal(verified_match: dict | None) -> str:
    if not verified_match:
        return (
            "I can't verify enough trusted local or English-language coverage for that specific match "
            "to describe how it was played without guessing."
        )

    teams = " and ".join(
        team for team in (verified_match.get("team_a"), verified_match.get("team_b")) if team
    )
    when = verified_match.get("requested_date_display")
    searched_locales = ", ".join(verified_match.get("searched_locales", []))
    if teams and when:
        prefix = (
            f"I can't verify enough trusted local or English-language coverage to describe "
            f"{teams} on {when} without guessing."
        )
    elif teams:
        prefix = (
            f"I can't verify enough trusted local or English-language coverage to describe "
            f"{teams} without guessing."
        )
    else:
        prefix = (
            "I can't verify enough trusted local or English-language coverage to describe that match without guessing."
        )

    if verified_match.get("match_identity_verified") and not verified_match.get(
        "narrative_coverage_available"
    ):
        detail = (
            " I found results tied to the fixture, but not enough verified match-report or live-commentary coverage to write a narrative summary."
        )
    else:
        detail = (
            " The retrieved results did not give me a verified match report or live commentary tied to that exact fixture and date."
        )

    if searched_locales:
        detail += f" Locales tried: {searched_locales}."

    return prefix + detail


def _format_hits_for_context(hits: list) -> str:
    grouped = {}
    for hit in hits:
        key = (hit.get("search_index", 0), hit.get("search_query", ""))
        grouped.setdefault(key, []).append(hit)

    sections = []
    for (search_index, search_query), group_hits in sorted(grouped.items()):
        section = [f"=== Search {search_index}: {search_query} ==="]
        for hit in group_hits:
            title = hit.get("title", "")
            body = hit.get("body", "")
            section.append(f"{title}: {body}".strip(": "))
        sections.append("\n".join(section))
    return "\n\n".join(sections) if sections else "No verified results found."


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _merge_search_results(results: list[dict]) -> dict:
    answers = []
    citations = []
    hits = []
    providers = []
    for result in results:
        answer = result.get("answer")
        if answer and answer != "No results found.":
            answers.append(answer)
        citations.extend(result.get("citations", []))
        hits.extend(result.get("hits", []))
        if result.get("provider"):
            providers.append(result["provider"])
    return {
        "answer": "\n\n".join(answers) if answers else "No results found.",
        "citations": _dedupe_keep_order(citations),
        "hits": hits,
        "provider": " + ".join(_unique(providers)),
    }


def search_perplexity(query: str, locale: str = "en", allowed_domains: list[str] | None = None) -> dict:
    """
    Search using Perplexity's Sonar API (OpenAI-compatible).
    Returns a dict with 'answer' (str), 'citations' (list of URLs), and 'hits' (list).
    """

    client = OpenAI(api_key=PERPLEXITY_API_KEY, base_url=PERPLEXITY_BASE_URL)

    request_kwargs = {
        "model": PERPLEXITY_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a football research assistant. Search for match reports, tactical analysis, "
                    "and post-match verdicts from trusted journalism sources. "
                    "Focus on HOW football was played: tactical flow, key phases, turning points, "
                    "player performances described narratively, and how journalists characterised events. "
                    "Prioritise sources that explain whether the result felt deserved, what each side did well or badly, "
                    "and the main post-match opinions or criticisms. "
                    f"Prioritise sources in locale {normalise_locale(locale)} when available. "
                    "Include direct quotes or close paraphrases from match reports. "
                    "Do NOT just list the score and goalscorers; provide the journalistic narrative. "
                    "Gather perspectives from multiple sources and note where they differ."
                ),
            },
            {"role": "user", "content": query},
        ],
    }
    if allowed_domains:
        request_kwargs["extra_body"] = {"search_domain_filter": allowed_domains}

    response = client.chat.completions.create(**request_kwargs)

    answer = response.choices[0].message.content
    citations = getattr(response, "citations", []) or []
    hits = [
        {
            "title": "Perplexity synthesis",
            "body": answer,
            "href": citation,
            "locale": normalise_locale(locale),
        }
        for citation in citations
    ]
    if not hits and answer:
        hits = [
            {
                "title": "Perplexity synthesis",
                "body": answer,
                "href": "",
                "locale": normalise_locale(locale),
            }
        ]

    return {"answer": answer, "citations": citations, "hits": hits, "provider": "Perplexity"}


def search_duckduckgo(
    query: str,
    locale: str = "en",
    max_results: int = 10,
    allowed_domains: list[str] | None = None,
) -> dict:
    """
    Search using DuckDuckGo (free, no API key needed).
    Returns a dict with 'answer' (str), 'citations' (list of URLs), and 'hits' (list).
    """

    from ddgs import DDGS
    from ddgs.exceptions import DDGSException

    site_filter = " OR ".join(f"site:{domain}" for domain in (allowed_domains or []))
    football_query = f"({site_filter}) {query}" if site_filter else query
    region = LOCALE_TO_DDG_REGION.get(
        normalise_locale(locale),
        LOCALE_TO_DDG_REGION.get(locale_language(locale), "wt-wt"),
    )

    results = []
    try:
        with DDGS() as ddgs:
            for result in ddgs.text(
                football_query,
                region=region,
                max_results=max_results,
            ):
                results.append(result)
    except DDGSException:
        return {
            "answer": "No results found.",
            "citations": [],
            "hits": [],
            "provider": "DuckDuckGo",
        }
    except TypeError:
        try:
            with DDGS() as ddgs:
                for result in ddgs.text(football_query, max_results=max_results):
                    results.append(result)
        except DDGSException:
            return {
                "answer": "No results found.",
                "citations": [],
                "hits": [],
                "provider": "DuckDuckGo",
            }

    if not results:
        return {
            "answer": "No results found.",
            "citations": [],
            "hits": [],
            "provider": "DuckDuckGo",
        }

    snippets = []
    citations = []
    hits = []
    for result in results:
        title = result.get("title", "")
        body = result.get("body", "")
        href = result.get("href", "")
        snippets.append(f"{title}: {body}")
        if href:
            citations.append(href)
        hits.append(
            {
                "title": title,
                "body": body,
                "href": href,
                "locale": normalise_locale(locale),
            }
        )

    answer = "\n\n".join(snippets)
    return {
        "answer": answer,
        "citations": citations,
        "hits": hits,
        "provider": "DuckDuckGo",
    }


def search_internet(query: str, locale: str = "en", source_tier: str = "english_fallback") -> dict:
    """
    Search the internet using the best available provider.
    Uses Perplexity if USE_PERPLEXITY is true, otherwise falls back to DuckDuckGo.
    Returns a dict with 'answer' (str), 'citations' (list), 'hits' (list), and 'provider' (str).
    """

    locale = normalise_locale(locale)
    allowed_domains = _locale_domains(locale, source_tier)

    primary_search = search_perplexity if USE_PERPLEXITY and PERPLEXITY_API_KEY else search_duckduckgo
    primary_result = primary_search(query, locale=locale, allowed_domains=allowed_domains)
    results = [primary_result]

    supplemental_domains = _supplemental_domains_for_tier(source_tier)
    if supplemental_domains:
        supplemental_result = primary_search(
            query,
            locale=locale,
            allowed_domains=supplemental_domains,
        )
        results.append(supplemental_result)

    merged = _merge_search_results(results)
    merged["provider"] = merged.get("provider") or primary_result.get("provider", "")
    return merged


def _coerce_search_batches(queries: list) -> list[dict]:
    if not queries:
        return []
    if isinstance(queries[0], str):
        return [
            {
                "locale": "en",
                "queries": _unique([_normalise_space(query) for query in queries if query]),
                "source_tier": "english_fallback",
            }
        ]

    batches = []
    for batch in queries:
        raw_locale = batch.get("locale")
        locale = (
            default_search_locale_for_language(raw_locale)
            if "-" not in normalise_locale(raw_locale)
            else normalise_locale(raw_locale)
        )
        batch_queries = _unique(
            [_normalise_space(query) for query in batch.get("queries", []) if query]
        )
        if not batch_queries:
            continue
        batches.append(
            {
                "locale": locale,
                "queries": batch_queries,
                "source_tier": batch.get("source_tier") or _default_source_tier(locale),
            }
        )
    return batches


def _batch_rank(verified_match: dict | None, raw_answer: str) -> tuple:
    if not verified_match:
        return (0, 0, 0, raw_answer != "No results found.")
    return (
        int(bool(verified_match.get("narrative_coverage_available"))),
        int(bool(verified_match.get("match_identity_verified"))),
        len(verified_match.get("accepted_hits", [])),
        int(raw_answer != "No results found."),
    )


def search_multi(queries: list, match_context: dict | None = None) -> dict:
    """
    Run multiple targeted searches and combine results.
    Used for match queries (3 searches) and other multi-angle queries.
    Returns raw text plus optional verified_match metadata.
    """

    search_batches = _coerce_search_batches(queries)
    locale_attempts = []
    best_result = {
        "answer": "No results found.",
        "raw_answer": "No results found.",
        "citations": [],
        "provider": "",
        "verified_match": None,
        "winning_locale": None,
        "source_tier": None,
    }
    best_rank = (-1, -1, -1, -1)

    for batch in search_batches:
        locale = batch["locale"]
        source_tier = batch["source_tier"]
        raw_sections = []
        citations = []
        hits = []
        provider = ""

        for i, query in enumerate(batch["queries"], 1):
            result = search_internet(query, locale=locale, source_tier=source_tier)
            if result["answer"] and result["answer"] != "No results found.":
                raw_sections.append(f"=== Search {i}: {query} ===\n{result['answer']}")
            citations.extend(result.get("citations", []))
            for hit in result.get("hits", []):
                hits.append(
                    {
                        **hit,
                        "search_index": i,
                        "search_query": query,
                        "locale": hit.get("locale") or locale,
                        "source_tier": source_tier,
                    }
                )
            if not provider:
                provider = result.get("provider", "")

        raw_answer = "\n\n".join(raw_sections) if raw_sections else "No results found."
        verification_context = match_context
        if match_context:
            verification_context = {
                **match_context,
                "search_locales": _unique(
                    [locale, *match_context.get("search_locales", [])]
                ),
            }
        verified_match = (
            verify_match_hits(hits, verification_context)
            if verification_context
            else None
        )
        answer = raw_answer
        batch_citations = _dedupe_keep_order(citations)

        if verified_match and verified_match.get("accepted_hits"):
            answer = _format_hits_for_context(verified_match["accepted_hits"])
            batch_citations = _dedupe_keep_order(
                [
                    hit["href"]
                    for hit in verified_match["accepted_hits"]
                    if hit.get("href")
                ]
            ) or batch_citations

        locale_attempt = {
            "locale": locale,
            "queries": batch["queries"],
            "provider": provider,
            "source_tier": source_tier,
            "raw_hit_count": len(hits),
            "accepted_hit_count": len((verified_match or {}).get("accepted_hits", [])),
            "match_identity_verified": bool(
                (verified_match or {}).get("match_identity_verified")
            ),
            "narrative_coverage_available": bool(
                (verified_match or {}).get("narrative_coverage_available")
            ),
        }
        locale_attempts.append(locale_attempt)

        batch_result = {
            "answer": answer,
            "raw_answer": raw_answer,
            "citations": batch_citations,
            "provider": provider,
            "verified_match": verified_match,
            "winning_locale": locale,
            "source_tier": source_tier,
        }
        batch_rank = _batch_rank(verified_match, raw_answer)
        if batch_rank > best_rank:
            best_result = batch_result
            best_rank = batch_rank

        if match_context:
            if match_report_can_answer(verified_match):
                best_result = batch_result
                break
        elif raw_answer != "No results found.":
            best_result = batch_result
            break

    verified_match = best_result.get("verified_match")
    winning_locale = best_result.get("winning_locale")
    source_tier = best_result.get("source_tier")
    if verified_match:
        verified_match["searched_locales"] = [attempt["locale"] for attempt in locale_attempts]
        verified_match["winning_locale"] = winning_locale
        verified_match["source_tier"] = source_tier
        if not verified_match.get("verified_source_language") and winning_locale:
            verified_match["verified_source_language"] = locale_language(winning_locale)

    return {
        "answer": best_result["answer"],
        "raw_answer": best_result["raw_answer"],
        "citations": best_result["citations"],
        "provider": best_result["provider"],
        "verified_match": verified_match,
        "locale_attempts": locale_attempts,
        "winning_locale": winning_locale,
        "source_tier": source_tier,
    }
