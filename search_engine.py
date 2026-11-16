"""Discovery of indexed LinkedIn profile *links* via an external search engine.

Never requests LinkedIn pages, uses cookies, login credentials or bypasses access controls.
Search results are leads, not verified candidate records.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse, unquote

FIELDS = ["Name (unverified)", "LinkedIn URL", "Search title", "Search snippet",
          "Matched terms (snippet)", "Match score", "Location evidence", "Source query", "Review status"]


@dataclass
class Filters:
    designation: str = ""
    title: str = ""
    industry: str = ""
    location: str = ""
    experience: str = ""
    skills: str = ""
    qualifications: str = ""


def terms(value: str) -> list[str]:
    return [x.strip() for x in re.split(r"[,;\n]+", value) if x.strip()][:10]


def quoted(term: str) -> str:
    term = re.sub(r'["\\\r\n]+', ' ', term).strip()
    return '"' + term[:90] + '"'


def build_queries(f: Filters, max_queries: int = 8) -> list[str]:
    """Search hints only: query matching never constitutes verified profile attributes."""
    core = list(dict.fromkeys(x.strip() for x in (f.designation, f.title) if x.strip()))
    if not core and not any((f.skills, f.industry, f.qualifications)):
        return []
    base = 'site:linkedin.com/in/ ' + ' '.join(map(quoted, core[:2]))
    # Location is present in EVERY query when requested, not merely a few variants.
    loc = ' ' + quoted(f.location.strip()) if f.location.strip() else ''
    extras = [f.industry.strip(), f.experience.strip()] + terms(f.skills) + terms(f.qualifications)
    extras = list(dict.fromkeys(x for x in extras if x))
    queries = []
    for extra in extras:
        q = (base + loc + ' ' + quoted(extra)).strip()
        if q not in queries:
            queries.append(q)
    fallback = (base + loc).strip()
    if fallback not in queries:
        queries.append(fallback)
    return queries[:max_queries]


def normalize_profile_url(url: str) -> str | None:
    try:
        p = urlparse(url)
        host = (p.hostname or '').lower()
        if host not in ('linkedin.com', 'www.linkedin.com', 'pk.linkedin.com', 'uk.linkedin.com', 'in.linkedin.com') and not host.endswith('.linkedin.com'):
            return None
        path = unquote(p.path).rstrip('/')
        parts = path.split('/')
        if len(parts) != 3 or parts[1] != 'in' or not re.fullmatch(r'[\w.%-]+', parts[2], re.UNICODE):
            return None
        return urlunparse(('https', 'www.linkedin.com', path, '', '', ''))
    except (ValueError, TypeError):
        return None


def get_name(title: str) -> str:
    """Only a hint from a search result title; never verified."""
    part = re.split(r'\s+[|–—-]\s+', title, maxsplit=1)[0].strip()
    if part.lower().endswith(' | linkedin'): part = part[:-11]
    if 'linkedin' in part.lower() or len(part) > 75: return ''
    return part[:75]


def location_evidence(location: str, title: str, snippet: str) -> str | None:
    """Conservative search-snippet *clue*, NOT verified residence/employment location.

    Reject bare city words (often candidate names), and demand an explicit location
    marker or city+region notation. Return a clue to make decisions auditable.
    """
    requested = location.strip()
    if not requested:
        return None
    # Search snippets are the primary evidence. The title may contain a name,
    # but explicit 'Location: ...' text there is still admissible.
    content = snippet + '  ' + title
    loc_re = re.escape(requested)
    sep = r"(?:\s*[,·|]\s*|\s+in\s+)"
    markers = [
        rf"\b(?:location|based in|located in|lives in|resides in|current city|city|area)\s*[:\-]?\s*{loc_re}(?=\b|\W|$)",
        rf"\b(?:greater|metro(?:politan)?)\s+{loc_re}\s+(?:area|region)\b",
        rf"\b{loc_re}\s+(?:metro(?:politan)?\s+area|area|region)\b",
    ]
    # 'Austin, TX' / 'Austin, Texas' / 'Karachi, Sindh' look like locations;
    # avoid generic 'Austin, Python' which could be keyword spam.
    cities = {
        'austin': ('tx', 'texas', 'united states', 'usa'),
        'karachi': ('sindh', 'pakistan'),
        'lahore': ('punjab', 'pakistan'),
        'islamabad': ('pakistan', 'islamabad capital territory'),
        'new york': ('ny', 'new york', 'united states', 'usa'),
        'san francisco': ('ca', 'california', 'united states', 'usa'),
        'london': ('uk', 'united kingdom', 'england'),
    }
    city = requested.split(',')[0].strip().casefold()
    qualifiers = [x.strip() for x in requested.split(',')[1:] if x.strip()]
    if not qualifiers:
        qualifiers = list(cities.get(city, ()))
    if qualifiers:
        city_pattern = re.escape(requested.split(',')[0].strip())
        region_pattern = '|'.join(re.escape(q) for q in qualifiers)
        markers.append(rf"\b{city_pattern}\s*,\s*(?:{region_pattern})\b")
    for pat in markers:
        match = re.search(pat, content, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def match_terms(f: Filters, title: str, snippet: str) -> tuple[str, int]:
    text = (title + ' ' + snippet).casefold()
    candidates = [f.designation, f.title, f.industry, f.location, f.experience] + terms(f.skills) + terms(f.qualifications)
    candidates = list(dict.fromkeys(x.strip() for x in candidates if x.strip()))
    matched = [x for x in candidates if x.casefold() in text]
    return ', '.join(matched), round(100 * len(matched) / max(1, len(candidates)))


def search(f: Filters, max_profiles: int = 100, max_queries: int = 8, on_progress=None, strict_all: bool = False) -> tuple[list[dict], list[str]]:
    """Fetch search-engine results only; cap queries and retain only public link metadata."""
    from ddgs import DDGS
    queries = build_queries(f, max_queries=max_queries)
    if not queries:
        return [], ["Enter a designation, job title, industry, skill or qualification to search."]
    found: dict[str, dict] = {}
    warnings = []
    with DDGS(timeout=15) as client:
        for index, query in enumerate(queries):
            if len(found) >= max_profiles: break
            if on_progress: on_progress(index, len(queries), len(found))
            try:
                results = client.text(query, max_results=min(40, max_profiles), safesearch='moderate') or []
                for result in results:
                    url = normalize_profile_url(result.get('href') or result.get('url') or '')
                    if not url or url in found: continue
                    title = str(result.get('title') or '')[:250]
                    snippet = str(result.get('body') or '')[:600]
                    evidence = location_evidence(f.location, title, snippet)
                    # If location is requested, exclude profiles with no explicit
                    # geographic evidence in the *search result*. No guessing.
                    if f.location.strip() and not evidence:
                        continue
                    matches, score = match_terms(f, title, snippet)
                    if strict_all:
                        requested = [f.designation, f.title, f.industry, f.experience] + terms(f.skills) + terms(f.qualifications)
                        combined = (title + ' ' + snippet).casefold()
                        if any(x.strip().casefold() not in combined for x in requested if x.strip()):
                            continue
                    found[url] = {FIELDS[0]: get_name(title), FIELDS[1]: url,
                                  FIELDS[2]: title, FIELDS[3]: snippet,
                                  FIELDS[4]: matches, FIELDS[5]: score,
                                  FIELDS[6]: evidence or 'Not requested', FIELDS[7]: query, FIELDS[8]: 'Not verified'}
                    if len(found) >= max_profiles: break
            except Exception as exc:
                warnings.append(f"Query {index+1} unavailable ({type(exc).__name__}); external search may rate-limit requests.")
    if on_progress: on_progress(len(queries), len(queries), len(found))
    return sorted(found.values(), key=lambda r: r[FIELDS[5]], reverse=True), warnings
