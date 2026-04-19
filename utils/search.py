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

QUERY_CATEGORY_MATCH_NARRATIVE = "match_narrative"
QUERY_CATEGORY_POST_MATCH_REACTION = "post_match_reaction"
QUERY_CATEGORY_CONTEXT_SENTIMENT = "context_sentiment"
QUERY_CATEGORIES = (
    QUERY_CATEGORY_MATCH_NARRATIVE,
    QUERY_CATEGORY_POST_MATCH_REACTION,
    QUERY_CATEGORY_CONTEXT_SENTIMENT,
)

_MATCH_NARRATIVE_KEYWORDS = {
    "ar": ["تقرير", "مباراة", "تعليق مباشر", "تحليل", "ملخص"],
    "de": ["spielbericht", "live kommentar", "analyse", "bericht", "liveticker"],
    "en": ["match report", "live commentary", "live text commentary", "analysis", "tactical analysis", "how it played out"],
    "es": ["crónica", "cronica", "comentario en directo", "análisis", "analisis", "relato"],
    "fr": ["compte-rendu", "compte rendu", "direct commenté", "analyse", "récit du match", "recit du match"],
    "it": ["cronaca", "diretta", "analisi", "resoconto"],
    "nl": ["wedstrijdverslag", "liveblog", "analyse", "verslag"],
    "pl": ["relacja", "komentarz na żywo", "komentarz na zywo", "analiza", "przebieg meczu"],
    "pt": ["crónica", "cronica", "relato", "comentário ao vivo", "comentario ao vivo", "analise", "análise"],
    "tr": ["maç raporu", "mac raporu", "canlı anlatım", "canli anlatim", "analiz", "mac ozeti", "maç özeti"],
}

_POST_MATCH_REACTION_KEYWORDS = {
    "ar": ["ردود فعل", "آراء", "مؤتمر صحفي", "تقييمات", "تصريحات"],
    "de": ["reaktion", "meinung", "fazit", "pressekonferenz", "noten", "stimmen"],
    "en": ["post match", "reaction", "verdict", "opinion", "player ratings", "press conference", "quotes", "ratings"],
    "es": ["reacción", "reaccion", "opinión", "opinion", "valoraciones", "rueda de prensa", "declaraciones"],
    "fr": ["réaction", "reaction", "avis", "conférence de presse", "notes", "déclarations", "declarations"],
    "it": ["reazioni", "giudizio", "pagelle", "conferenza stampa", "dichiarazioni"],
    "nl": ["reactie", "oordeel", "persconferentie", "spelersbeoordelingen", "cijfers"],
    "pl": ["reakcje", "opinie", "oceny", "konferencja prasowa", "wypowiedzi"],
    "pt": ["reação", "reacao", "opinião", "opiniao", "notas", "pós-jogo", "pos-jogo", "pos jogo", "conferência de imprensa", "declaracoes", "declarações"],
    "tr": ["tepki", "yorum", "basın toplantısı", "basin toplantisi", "puanlar", "aciklamalar", "açıklamalar"],
}

_CONTEXT_SENTIMENT_KEYWORDS = {
    "ar": ["احتجاج", "مطالبة برحيل المدرب", "أجواء", "توقعات", "أزمة", "جماهير", "ضغط", "ترحيب", "حماس", "تصريحات", "مقابلة", "تعافي", "عودة", "غياب", "تأثير", "بديل"],
    "de": ["druck", "krise", "proteste fans", "stimmung", "erwartungen", "entlassung", "unruhe", "pfiffe", "begeisterung", "willkommen", "interview", "eingewöhnung", "eingewohnung", "fan reaktion", "genesung", "comeback", "ausfall", "ersatz", "auswirkung", "reha"],
    "en": ["fan protest", "booing", "booed", "boo", "under pressure", "pressure", "sack", "crisis", "atmosphere", "unrest", "expectations", "dressing room", "fan reaction", "morale", "fan excitement", "welcome", "adaptation", "settling in", "interview", "social media", "fan opinion", "reception", "buzz", "recovery", "comeback", "rehab", "rehabilitation", "absence", "impact", "replacement", "without him", "missed", "return to training", "lifestyle"],
    "es": ["presion", "crisis", "protestas aficionados", "ambiente", "expectativas", "destitucion", "abucheos", "entusiasmo", "bienvenida", "adaptacion", "entrevista", "reaccion aficion", "ilusion", "recuperacion", "regreso", "ausencia", "impacto", "sustituto", "rehabilitacion"],
    "fr": ["pression", "crise", "protestations supporters", "ambiance", "attentes", "limogeage", "sifflets", "enthousiasme", "accueil", "adaptation", "interview", "reaction supporters", "recuperation", "retour", "absence", "impact", "remplacant", "reeducation"],
    "it": ["pressione", "crisi", "proteste tifosi", "atmosfera", "aspettative", "esonero", "contestazione", "entusiasmo", "accoglienza", "adattamento", "intervista", "reazione tifosi", "recupero", "ritorno", "assenza", "impatto", "sostituto", "riabilitazione"],
    "nl": ["druk", "crisis", "protesterende fans", "sfeer", "verwachtingen", "ontslag", "boegeroep", "enthousiasme", "welkom", "aanpassing", "interview", "fan reactie", "herstel", "comeback", "afwezigheid", "impact", "vervanger", "revalidatie"],
    "pl": ["kryzys", "protesty kibicow", "atmosfera", "oczekiwania", "zwolnienie trenera", "presja", "gwizdy", "entuzjazm", "powitanie", "adaptacja", "wywiad", "reakcja kibicow", "powrot", "rehabilitacja", "nieobecnosc", "wplyw", "zastepstwo"],
    "pt": ["pressao", "crise", "protestos adeptos", "ambiente", "expectativas", "demissao", "assobios", "entusiasmo", "recepcao", "adaptacao", "entrevista", "reacao adeptos", "euforia", "recuperacao", "regresso", "ausencia", "impacto", "substituto", "reabilitacao"],
    "tr": ["baski", "kriz", "taraftar protestosu", "atmosfer", "beklentiler", "kovulma", "yuhalama", "heyecan", "karsilama", "uyum", "roportaj", "taraftar tepkisi", "iyilesme", "donus", "yokluk", "etki", "yedek", "rehabilitasyon"],
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


def _normalise_query_category(category: str | None) -> str:
    category = _normalise_key(category or "")
    if category == _normalise_key(QUERY_CATEGORY_POST_MATCH_REACTION):
        return QUERY_CATEGORY_POST_MATCH_REACTION
    if category == _normalise_key(QUERY_CATEGORY_CONTEXT_SENTIMENT):
        return QUERY_CATEGORY_CONTEXT_SENTIMENT
    return QUERY_CATEGORY_MATCH_NARRATIVE


def _season_token_for_date(absolute_date: str | None, today: date | None = None) -> str:
    today = today or date.today()
    reference = date.fromisoformat(absolute_date) if absolute_date else today
    if reference.month < 8:
        start_year = reference.year - 1
        end_year = reference.year
    else:
        start_year = reference.year
        end_year = reference.year + 1
    return f"{start_year}/{str(end_year)[2:]}"


def _default_queries_for_locale(
    locale: str,
    entities: list,
    absolute_date: str | None,
    query_category: str = QUERY_CATEGORY_MATCH_NARRATIVE,
) -> list[str]:
    names = [entity.get("name", "") for entity in entities if entity.get("name")]
    joined = " vs ".join(names[:2]) if len(names) >= 2 else " ".join(names) or "football"
    language = locale_language(locale)
    team_a = names[0] if len(names) >= 1 else joined
    team_b = names[1] if len(names) >= 2 else ""
    date_fragment = absolute_date or _season_token_for_date(None)
    season_token = _season_token_for_date(absolute_date)
    locale_terms = {
        "en": {
            QUERY_CATEGORY_MATCH_NARRATIVE: [
                f"{team_a} vs {team_b} {date_fragment} match report tactical analysis",
                f"{team_b} vs {team_a} {date_fragment} live commentary analysis",
                f"{team_a} {team_b} {date_fragment} how the game was judged",
            ],
            QUERY_CATEGORY_POST_MATCH_REACTION: [
                f"{team_a} vs {team_b} {date_fragment} post match reaction verdict",
                f"{team_b} vs {team_a} {date_fragment} player ratings opinion",
                f"{team_a} {team_b} {date_fragment} press conference quotes",
            ],
            QUERY_CATEGORY_CONTEXT_SENTIMENT: [
                f"{team_a} fan reaction atmosphere {season_token}",
                f"{team_a} coach under pressure crisis {season_token}",
                f"{team_a} expectations supporters unrest {season_token}",
            ],
        },
        "pt": {
            QUERY_CATEGORY_MATCH_NARRATIVE: [
                f"{team_a} vs {team_b} {date_fragment} cronica analise tatica",
                f"{team_b} vs {team_a} {date_fragment} relato comentario ao vivo",
                f"{team_a} {team_b} {date_fragment} como foi o jogo analise",
            ],
            QUERY_CATEGORY_POST_MATCH_REACTION: [
                f"{team_a} vs {team_b} {date_fragment} reacoes opiniao pos-jogo",
                f"{team_b} vs {team_a} {date_fragment} notas ao jogo declaracoes",
                f"{team_a} {team_b} {date_fragment} conferencia de imprensa reacao",
            ],
            QUERY_CATEGORY_CONTEXT_SENTIMENT: [
                f"{team_a} adeptos reacao ambiente {season_token}",
                f"{team_a} treinador pressao crise {season_token}",
                f"{team_a} expectativas protestos adeptos {season_token}",
            ],
        },
        "pl": {
            QUERY_CATEGORY_MATCH_NARRATIVE: [
                f"{team_a} vs {team_b} {date_fragment} relacja analiza taktyczna",
                f"{team_b} vs {team_a} {date_fragment} komentarz na zywo analiza",
                f"{team_a} {team_b} {date_fragment} jak wygladal mecz",
            ],
            QUERY_CATEGORY_POST_MATCH_REACTION: [
                f"{team_a} vs {team_b} {date_fragment} reakcje opinie po meczu",
                f"{team_b} vs {team_a} {date_fragment} oceny zawodnikow",
                f"{team_a} {team_b} {date_fragment} konferencja prasowa wypowiedzi",
            ],
            QUERY_CATEGORY_CONTEXT_SENTIMENT: [
                f"{team_a} reakcja kibicow atmosfera {season_token}",
                f"{team_a} trener presja kryzys {season_token}",
                f"{team_a} oczekiwania protesty kibicow {season_token}",
            ],
        },
    }
    queries = locale_terms.get(language, locale_terms["en"]).get(
        query_category,
        locale_terms["en"][QUERY_CATEGORY_MATCH_NARRATIVE],
    )
    return _unique(queries)


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
    search_query_batches = []
    batch_index_by_key = {}
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
        source_tier = batch.get("source_tier") or _default_source_tier(locale)
        query_category = _normalise_query_category(batch.get("query_category"))
        key = (locale, query_category, source_tier)
        existing_index = batch_index_by_key.get(key)
        if existing_index is not None:
            search_query_batches[existing_index]["queries"] = _unique(
                [*search_query_batches[existing_index]["queries"], *queries]
            )
            continue
        batch_index_by_key[key] = len(search_query_batches)
        search_query_batches.append(
            {
                "locale": locale,
                "queries": queries,
                "source_tier": source_tier,
                "query_category": query_category,
            }
        )

    for locale in search_locales:
        for query_category in QUERY_CATEGORIES:
            if any(
                batch["locale"] == locale and batch["query_category"] == query_category
                for batch in search_query_batches
            ):
                continue
            search_query_batches.append(
                {
                    "locale": locale,
                    "queries": _default_queries_for_locale(
                        locale,
                        entities,
                        absolute_date,
                        query_category=query_category,
                    ),
                    "source_tier": _default_source_tier(locale),
                    "query_category": query_category,
                }
            )

    return {
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


def _keyword_languages(hit: dict, languages: list[str] | None = None) -> list[str]:
    return _unique([*(languages or []), locale_language(hit.get("locale")), "en"])


def _matches_keyword_map(
    hit: dict,
    keyword_map: dict[str, list[str]],
    languages: list[str] | None = None,
) -> bool:
    text = _normalise_key(_hit_text(hit))
    keyword_pool = []
    for language in _keyword_languages(hit, languages=languages):
        keyword_pool.extend(keyword_map.get(language, []))
    return any(_normalise_key(keyword) in text for keyword in keyword_pool)


def _is_supported_journalism_hit(hit: dict) -> bool:
    domain = _extract_domain(hit.get("href", ""))
    source_tier = hit.get("source_tier")
    if domain in _STATS_DOMAINS:
        return False
    if domain not in _JOURNALISM_DOMAINS and source_tier not in ("open_web_local", "english_fallback"):
        return False
    return True


_NARRATIVE_FALLBACK_PATTERNS = [
    "tactical analysis", "analise tatica", "análise tática",
    "player ratings", "notas dos jogadores", "puntuaciones",
    "how it played out", "match review", "game report",
    "match recap", "post-match", "pós-jogo", "pos jogo",
    "result reaction", "resultado e reação",
]


def _is_match_narrative_hit(hit: dict, languages: list[str] | None = None) -> bool:
    if not _is_supported_journalism_hit(hit):
        return False
    if _matches_keyword_map(hit, _MATCH_NARRATIVE_KEYWORDS, languages=languages):
        return True
    text = _normalise_key(_hit_text(hit))
    return any(pattern in text for pattern in _NARRATIVE_FALLBACK_PATTERNS)


def _is_reaction_hit(hit: dict, languages: list[str] | None = None) -> bool:
    if not _is_supported_journalism_hit(hit):
        return False
    return _matches_keyword_map(hit, _POST_MATCH_REACTION_KEYWORDS, languages=languages)


def _is_context_hit(hit: dict, languages: list[str] | None = None) -> bool:
    if not _is_supported_journalism_hit(hit):
        return False
    return _matches_keyword_map(hit, _CONTEXT_SENTIMENT_KEYWORDS, languages=languages)


def _season_tokens(reference_date: date | None = None) -> set[str]:
    reference_date = reference_date or date.today()
    if reference_date.month < 8:
        current_start = reference_date.year - 1
        current_end = reference_date.year
    else:
        current_start = reference_date.year
        current_end = reference_date.year + 1
    previous_start = current_start - 1
    previous_end = current_start

    season_ranges = [
        (current_start, current_end),
        (previous_start, previous_end),
    ]
    tokens = set()
    for start_year, end_year in season_ranges:
        tokens.update(
            {
                f"{start_year}/{str(end_year)[2:]}",
                f"{start_year}-{str(end_year)[2:]}",
                f"{start_year}/{end_year}",
                f"{start_year}-{end_year}",
            }
        )
    return tokens


def _match_context_languages(match_context: dict | None) -> list[str]:
    return _unique(
        [locale_language(locale) for locale in (match_context or {}).get("search_locales", [])]
        + [((match_context or {}).get("answer_language") or "en")]
    )


def _enrich_fixture_hit(
    hit: dict,
    match_context: dict,
    languages: list[str] | None = None,
    today: date | None = None,
) -> tuple[dict | None, dict | None]:
    team_a_aliases = set(match_context.get("team_a_aliases", []))
    team_b_aliases = set(match_context.get("team_b_aliases", []))
    requested_date = match_context.get("requested_date")
    text = _hit_text(hit)
    if _is_non_football_hit(hit):
        return None, {
            "title": hit.get("title", ""),
            "href": hit.get("href", ""),
            "reason": "non_football_result",
        }
    if _is_generic_team_page(hit, team_a_aliases, team_b_aliases):
        return None, {
            "title": hit.get("title", ""),
            "href": hit.get("href", ""),
            "reason": "generic_team_page",
        }
    if not _text_mentions_aliases(text, team_a_aliases):
        return None, {
            "title": hit.get("title", ""),
            "href": hit.get("href", ""),
            "reason": "missing_team_a",
        }
    if not _text_mentions_aliases(text, team_b_aliases):
        return None, {
            "title": hit.get("title", ""),
            "href": hit.get("href", ""),
            "reason": "missing_team_b",
        }
    if requested_date:
        combined_text = f"{text} {hit.get('href', '')}"
        date_found = _text_contains_target_date(
            combined_text,
            requested_date,
            today=today,
            languages=languages,
        )
        if not date_found:
            # Only apply the recent-match grace period when the article has NO
            # parseable date at all (relative phrasing like "last night"). If the
            # text mentions a different concrete date, reject — the article is
            # about another match.
            target = date.fromisoformat(requested_date)
            days_ago = ((today or date.today()) - target).days
            parsed_dates = _search_dates(
                combined_text,
                today or date.today(),
                languages=_unique([*(languages or []), "en"]),
            )
            within_grace = 0 <= days_ago <= 14 and not parsed_dates
            if not within_grace:
                return None, {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "wrong_or_missing_date",
                }
    return (
        {
            **hit,
            "domain": _extract_domain(hit.get("href", "")),
            "verified_source_language": locale_language(hit.get("locale") or hit.get("source_locale")),
        },
        None,
    )


def _has_recent_context_window(
    text: str,
    match_context: dict,
    languages: list[str] | None = None,
    today: date | None = None,
) -> bool:
    today = today or date.today()
    raw_text = (text or "").casefold()
    reference_dates = [today]
    if match_context.get("requested_date"):
        reference_dates.append(date.fromisoformat(match_context["requested_date"]))
    if any(token in raw_text for token in _season_tokens(today)):
        return True
    for reference_date in reference_dates:
        if any(token in raw_text for token in _season_tokens(reference_date)):
            return True
    parsed_dates = _search_dates(text, today, languages=_unique([*(languages or []), "en"]))
    return any(
        abs((parsed_date - reference_date).days) <= 90
        for parsed_date in parsed_dates
        for reference_date in reference_dates
    )


def _source_priority(source_tier: str | None) -> int:
    if source_tier == "curated_local":
        return 3
    if source_tier == "english_fallback":
        return 2
    if source_tier == "open_web_local":
        return 1
    return 0


def _rank_and_dedupe_hits(hits: list[dict], limit: int | None = None) -> list[dict]:
    deduped = {}
    for hit in hits:
        dedupe_key = hit.get("href") or _normalise_key(f"{hit.get('title', '')} {hit.get('body', '')}")
        incumbent = deduped.get(dedupe_key)
        if incumbent is None or (
            _source_priority(hit.get("source_tier")) > _source_priority(incumbent.get("source_tier"))
        ):
            deduped[dedupe_key] = hit

    ranked = sorted(
        deduped.values(),
        key=lambda hit: (
            -_source_priority(hit.get("source_tier")),
            hit.get("search_index", 99),
            -len(_normalise_key(_hit_text(hit))),
        ),
    )
    if limit is not None:
        return ranked[:limit]
    return ranked


def verify_match_hits(hits: list, match_context: dict | None, today: date | None = None) -> dict | None:
    if not match_context:
        return None

    today = today or date.today()
    team_a = match_context.get("team_a", "")
    team_b = match_context.get("team_b", "")
    languages = _match_context_languages(match_context)

    accepted_hits = []
    fixture_hits = []
    rejected_hits = []
    score_counter = Counter()
    fixture_source_language_counter = Counter()
    accepted_source_language_counter = Counter()

    for hit in hits:
        enriched_hit, rejected_hit = _enrich_fixture_hit(
            hit,
            match_context,
            languages=languages,
            today=today,
        )
        if rejected_hit:
            rejected_hits.append(rejected_hit)
            continue

        enriched_hit["is_match_narrative"] = _is_match_narrative_hit(hit, languages=languages)
        fixture_hits.append(enriched_hit)
        if enriched_hit["verified_source_language"]:
            fixture_source_language_counter[enriched_hit["verified_source_language"]] += 1
        if score := _extract_ordered_score(
            _hit_text(hit),
            team_a,
            team_b,
            set(match_context.get("team_a_aliases", [])),
            set(match_context.get("team_b_aliases", [])),
        ):
            score_counter[score] += 1
        if enriched_hit["is_match_narrative"]:
            accepted_hits.append(enriched_hit)
            if enriched_hit["verified_source_language"]:
                accepted_source_language_counter[enriched_hit["verified_source_language"]] += 1

    verified_score = score_counter.most_common(1)[0][0] if score_counter else None
    verified_source_language = (
        accepted_source_language_counter.most_common(1)[0][0]
        if accepted_source_language_counter
        else (
            fixture_source_language_counter.most_common(1)[0][0]
            if fixture_source_language_counter
            else None
        )
    )
    ranked_fixture_hits = _rank_and_dedupe_hits(fixture_hits)
    ranked_accepted_hits = _rank_and_dedupe_hits(accepted_hits)

    return {
        **match_context,
        "raw_hit_count": len(hits),
        "match_identity_verified": bool(ranked_fixture_hits),
        "match_result_verified": bool(verified_score),
        "narrative_coverage_available": bool(ranked_accepted_hits),
        "verified_date": match_context.get("requested_date") if ranked_fixture_hits else None,
        "verified_score": verified_score,
        "accepted_hits": ranked_accepted_hits,
        "fixture_hits": ranked_fixture_hits,
        "rejected_hits": rejected_hits,
        "verified_source_language": verified_source_language,
    }


def verify_reaction_hits(
    hits: list,
    match_context: dict | None,
    today: date | None = None,
) -> dict | None:
    if not match_context:
        return None

    today = today or date.today()
    languages = _match_context_languages(match_context)
    accepted_hits = []
    rejected_hits = []
    for hit in hits:
        enriched_hit, rejected_hit = _enrich_fixture_hit(
            hit,
            match_context,
            languages=languages,
            today=today,
        )
        if rejected_hit:
            rejected_hits.append(rejected_hit)
            continue
        if not _is_reaction_hit(hit, languages=languages):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "not_post_match_reaction",
                }
            )
            continue
        enriched_hit["is_post_match_reaction"] = True
        accepted_hits.append(enriched_hit)

    ranked_hits = _rank_and_dedupe_hits(accepted_hits)
    return {
        "accepted_hits": ranked_hits,
        "rejected_hits": rejected_hits,
        "reaction_coverage_available": bool(ranked_hits),
    }


def verify_context_hits(
    hits: list,
    match_context: dict | None,
    today: date | None = None,
) -> dict | None:
    if not match_context:
        return None

    today = today or date.today()
    team_a_aliases = set(match_context.get("team_a_aliases", []))
    team_b_aliases = set(match_context.get("team_b_aliases", []))
    languages = _match_context_languages(match_context)
    accepted_hits = []
    rejected_hits = []

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
        mentions_team = _text_mentions_aliases(text, team_a_aliases) or _text_mentions_aliases(
            text,
            team_b_aliases,
        )
        if not mentions_team:
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "missing_fixture_club",
                }
            )
            continue
        if not _is_context_hit(hit, languages=languages):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "not_context_sentiment",
                }
            )
            continue
        if not _has_recent_context_window(
            f"{text} {hit.get('href', '')}",
            match_context,
            languages=languages,
            today=today,
        ):
            rejected_hits.append(
                {
                    "title": hit.get("title", ""),
                    "href": hit.get("href", ""),
                    "reason": "not_season_relevant",
                }
            )
            continue
        accepted_hits.append(
            {
                **hit,
                "domain": _extract_domain(hit.get("href", "")),
                "verified_source_language": locale_language(hit.get("locale") or hit.get("source_locale")),
                "is_context_hit": True,
            }
        )

    ranked_hits = _rank_and_dedupe_hits(accepted_hits)
    return {
        "accepted_hits": ranked_hits,
        "rejected_hits": rejected_hits,
        "context_coverage_available": bool(ranked_hits),
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


def _format_evidence_blocks_for_context(evidence_blocks: dict[str, list[dict]]) -> str:
    section_titles = {
        QUERY_CATEGORY_MATCH_NARRATIVE: "Match narrative evidence",
        QUERY_CATEGORY_POST_MATCH_REACTION: "Post-match reaction evidence",
        QUERY_CATEGORY_CONTEXT_SENTIMENT: "Context & mood evidence",
    }
    sections = []
    for query_category in QUERY_CATEGORIES:
        hits = evidence_blocks.get(query_category, [])
        label = section_titles[query_category]
        section = [f"--- {label} ---"]
        if hits:
            section.append(_format_hits_for_context(hits))
        else:
            section.append("No evidence found.")
        sections.append("\n".join(section))
    return "\n\n".join(sections)


def _format_raw_sections_by_category(raw_sections_by_category: dict[str, list[str]]) -> str:
    section_titles = {
        QUERY_CATEGORY_MATCH_NARRATIVE: "Raw match narrative searches",
        QUERY_CATEGORY_POST_MATCH_REACTION: "Raw post-match reaction searches",
        QUERY_CATEGORY_CONTEXT_SENTIMENT: "Raw context & mood searches",
    }
    sections = []
    for query_category in QUERY_CATEGORIES:
        raw_sections = raw_sections_by_category.get(query_category, [])
        if not raw_sections:
            continue
        sections.append(
            "\n".join([f"--- {section_titles[query_category]} ---", "\n\n".join(raw_sections)])
        )
    return "\n\n".join(sections) if sections else "No results found."


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
                "query_category": QUERY_CATEGORY_MATCH_NARRATIVE,
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
                "query_category": _normalise_query_category(batch.get("query_category")),
            }
        )
    return batches


def search_multi(queries: list, match_context: dict | None = None) -> dict:
    """
    Run multiple targeted searches and combine results.
    Used for match queries (3 searches) and other multi-angle queries.
    Returns raw text plus optional verified_match metadata.
    """

    search_batches = _coerce_search_batches(queries)
    locale_attempts = []
    provider_order = []

    if not match_context:
        raw_sections = []
        citations = []
        winning_locale = None
        source_tier = None
        all_hits_by_category = {category: [] for category in QUERY_CATEGORIES}
        for batch in search_batches:
            locale = batch["locale"]
            query_category = batch["query_category"]
            batch_hits = []
            batch_has_results = False
            provider = ""
            for i, query in enumerate(batch["queries"], 1):
                result = search_internet(query, locale=locale, source_tier=batch["source_tier"])
                if result["answer"] and result["answer"] != "No results found.":
                    raw_sections.append(f"=== Search {i}: {query} ===\n{result['answer']}")
                    batch_has_results = True
                citations.extend(result.get("citations", []))
                for hit in result.get("hits", []):
                    enriched_hit = {
                        **hit,
                        "search_index": i,
                        "search_query": query,
                        "locale": hit.get("locale") or locale,
                        "source_tier": batch["source_tier"],
                        "query_category": query_category,
                        "domain": _extract_domain(hit.get("href", "")),
                    }
                    batch_hits.append(enriched_hit)
                if not provider:
                    provider = result.get("provider", "")
            if provider:
                provider_order.append(provider)
            all_hits_by_category.setdefault(query_category, []).extend(batch_hits)
            locale_attempts.append(
                {
                    "locale": locale,
                    "queries": batch["queries"],
                    "provider": provider,
                    "source_tier": batch["source_tier"],
                    "query_category": query_category,
                    "raw_hit_count": len(batch_hits),
                    "accepted_hit_count": len(batch_hits),
                    "match_identity_verified": False,
                    "narrative_coverage_available": False,
                    "reaction_coverage_available": False,
                    "context_coverage_available": False,
                }
            )
            if batch_has_results and winning_locale is None:
                winning_locale = locale
                source_tier = batch["source_tier"]

        evidence_blocks = {
            category: _rank_and_dedupe_hits(hits, limit=6)
            for category, hits in all_hits_by_category.items()
        }
        ordered_evidence_hits = [
            hit
            for category in QUERY_CATEGORIES
            for hit in evidence_blocks.get(category, [])
        ]
        evidence_citations = _dedupe_keep_order(
            [hit.get("href", "") for hit in ordered_evidence_hits if hit.get("href")]
        )
        if not evidence_citations:
            evidence_citations = _dedupe_keep_order(citations)

        combined_raw = "\n\n".join(raw_sections) if raw_sections else "No results found."
        return {
            "answer": combined_raw,
            "raw_answer": combined_raw,
            "citations": evidence_citations or _dedupe_keep_order(citations),
            "provider": " + ".join(_unique(provider_order)),
            "verified_match": None,
            "locale_attempts": locale_attempts,
            "winning_locale": winning_locale,
            "primary_match_locale": winning_locale,
            "source_tier": source_tier,
            "evidence_blocks": evidence_blocks,
        }

    raw_sections_by_category = {category: [] for category in QUERY_CATEGORIES}
    raw_hits_by_category = {category: [] for category in QUERY_CATEGORIES}
    best_match_locale = None
    best_match_source_tier = None
    best_match_rank = (-1, -1, -1, -1)

    for batch in search_batches:
        locale = batch["locale"]
        source_tier = batch["source_tier"]
        query_category = batch["query_category"]
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
                        "query_category": query_category,
                    }
                )
            if not provider:
                provider = result.get("provider", "")

        if provider:
            provider_order.append(provider)
        raw_sections_by_category.setdefault(query_category, []).extend(raw_sections)
        raw_hits_by_category.setdefault(query_category, []).extend(hits)

        verification_context = {
            **match_context,
            "search_locales": _unique([locale, *match_context.get("search_locales", [])]),
        }
        batch_attempt = {
            "locale": locale,
            "queries": batch["queries"],
            "provider": provider,
            "source_tier": source_tier,
            "query_category": query_category,
            "raw_hit_count": len(hits),
            "accepted_hit_count": 0,
            "match_identity_verified": False,
            "narrative_coverage_available": False,
            "reaction_coverage_available": False,
            "context_coverage_available": False,
        }

        if query_category == QUERY_CATEGORY_MATCH_NARRATIVE:
            batch_match = verify_match_hits(hits, verification_context)
            batch_attempt["accepted_hit_count"] = len((batch_match or {}).get("accepted_hits", []))
            batch_attempt["match_identity_verified"] = bool(
                (batch_match or {}).get("match_identity_verified")
            )
            batch_attempt["narrative_coverage_available"] = bool(
                (batch_match or {}).get("narrative_coverage_available")
            )
            batch_rank = (
                int(bool((batch_match or {}).get("narrative_coverage_available"))),
                int(bool((batch_match or {}).get("match_identity_verified"))),
                len((batch_match or {}).get("accepted_hits", [])),
                int(bool(raw_sections)),
            )
            if batch_rank > best_match_rank:
                best_match_rank = batch_rank
                best_match_locale = locale
                best_match_source_tier = source_tier
        elif query_category == QUERY_CATEGORY_POST_MATCH_REACTION:
            batch_reaction = verify_reaction_hits(hits, verification_context)
            batch_attempt["accepted_hit_count"] = len((batch_reaction or {}).get("accepted_hits", []))
            batch_attempt["reaction_coverage_available"] = bool(
                (batch_reaction or {}).get("reaction_coverage_available")
            )
            batch_attempt["match_identity_verified"] = bool(batch_attempt["accepted_hit_count"])
        else:
            batch_context = verify_context_hits(hits, verification_context)
            batch_attempt["accepted_hit_count"] = len((batch_context or {}).get("accepted_hits", []))
            batch_attempt["context_coverage_available"] = bool(
                (batch_context or {}).get("context_coverage_available")
            )

        locale_attempts.append(batch_attempt)

    combined_context = {
        **match_context,
        "search_locales": _unique([attempt["locale"] for attempt in locale_attempts]),
    }
    verified_match = verify_match_hits(
        [
            *raw_hits_by_category.get(QUERY_CATEGORY_MATCH_NARRATIVE, []),
            *raw_hits_by_category.get(QUERY_CATEGORY_POST_MATCH_REACTION, []),
        ],
        combined_context,
    )
    reaction_summary = verify_reaction_hits(
        raw_hits_by_category.get(QUERY_CATEGORY_POST_MATCH_REACTION, []),
        combined_context,
    ) or {"accepted_hits": [], "reaction_coverage_available": False}
    context_summary = verify_context_hits(
        raw_hits_by_category.get(QUERY_CATEGORY_CONTEXT_SENTIMENT, []),
        combined_context,
    ) or {"accepted_hits": [], "context_coverage_available": False}

    # Use fixture_hits as supplement when accepted match narrative hits are thin.
    # fixture_hits passed both-teams + date verification but missed the narrow
    # "match report" / "analysis" keyword filter — they are still relevant articles.
    match_accepted = (verified_match or {}).get("accepted_hits", [])
    match_fixture = (verified_match or {}).get("fixture_hits", [])
    if len(match_accepted) < 4 and match_fixture:
        accepted_hrefs = {h.get("href") for h in match_accepted}
        combined_match = match_accepted + [
            h for h in match_fixture if h.get("href") not in accepted_hrefs
        ]
        match_evidence = _rank_and_dedupe_hits(combined_match, limit=10)
    else:
        match_evidence = _rank_and_dedupe_hits(match_accepted, limit=10)

    evidence_blocks = {
        QUERY_CATEGORY_MATCH_NARRATIVE: match_evidence,
        QUERY_CATEGORY_POST_MATCH_REACTION: _rank_and_dedupe_hits(
            reaction_summary.get("accepted_hits", []),
            limit=8,
        ),
        QUERY_CATEGORY_CONTEXT_SENTIMENT: _rank_and_dedupe_hits(
            context_summary.get("accepted_hits", []),
            limit=6,
        ),
    }
    ordered_evidence_hits = [
        *evidence_blocks[QUERY_CATEGORY_MATCH_NARRATIVE],
        *evidence_blocks[QUERY_CATEGORY_POST_MATCH_REACTION],
        *evidence_blocks[QUERY_CATEGORY_CONTEXT_SENTIMENT],
    ]
    evidence_citations = _dedupe_keep_order(
        [hit.get("href", "") for hit in ordered_evidence_hits if hit.get("href")]
    )
    if not evidence_citations:
        evidence_citations = _dedupe_keep_order(
            [
                hit.get("href", "")
                for category_hits in raw_hits_by_category.values()
                for hit in category_hits
                if hit.get("href")
            ]
        )

    if verified_match is None:
        verified_match = {**combined_context}
    verified_match["accepted_hits"] = evidence_blocks[QUERY_CATEGORY_MATCH_NARRATIVE]
    verified_match["reaction_hits"] = evidence_blocks[QUERY_CATEGORY_POST_MATCH_REACTION]
    verified_match["context_hits"] = evidence_blocks[QUERY_CATEGORY_CONTEXT_SENTIMENT]
    verified_match["context_coverage_available"] = bool(
        evidence_blocks[QUERY_CATEGORY_CONTEXT_SENTIMENT]
    )
    verified_match["reaction_coverage_available"] = bool(
        evidence_blocks[QUERY_CATEGORY_POST_MATCH_REACTION]
    )
    verified_match["searched_locales"] = _unique([attempt["locale"] for attempt in locale_attempts])
    verified_match["winning_locale"] = best_match_locale
    verified_match["primary_match_locale"] = best_match_locale
    verified_match["source_tier"] = best_match_source_tier
    if not verified_match.get("verified_source_language") and best_match_locale:
        verified_match["verified_source_language"] = locale_language(best_match_locale)

    formatted_evidence = _format_evidence_blocks_for_context(evidence_blocks)
    raw_answer = _format_raw_sections_by_category(raw_sections_by_category)

    return {
        "answer": formatted_evidence,
        "raw_answer": raw_answer,
        "citations": evidence_citations,
        "provider": " + ".join(_unique(provider_order)),
        "verified_match": verified_match,
        "locale_attempts": locale_attempts,
        "winning_locale": best_match_locale,
        "primary_match_locale": best_match_locale,
        "source_tier": best_match_source_tier,
        "evidence_blocks": evidence_blocks,
    }
