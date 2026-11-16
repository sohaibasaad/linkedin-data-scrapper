"""Discovery of indexed LinkedIn profile *links* via an external search engine.

Never requests LinkedIn pages, uses cookies, login credentials or bypasses access controls.
Search results are leads, not verified candidate records.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse, unquote

FIELDS = ["Name (unverified)", "LinkedIn URL", "Search title", "Search snippet",
          "Matched terms (snippet)", "Match score", "Source query", "Review status"]


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
    """Balance specificity and recall; do not assert that result attributes are accurate."""
    core = [f.designation.strip(), f.title.strip()]
    core = list(dict.fromkeys(x for x in core if x))
    if not core and not any((f.skills, f.industry, f.qualifications)):
        return []
    base = 'site:linkedin.com/in/ ' + ' '.join(map(quoted, core[:2]))
    facets = []
    if f.location.strip(): facets.append(quoted(f.location.strip()))
    if f.industry.strip(): facets.append(quoted(f.industry.strip()))
    if f.experience.strip(): facets.append(quoted(f.experience.strip()))
    skill_terms = terms(f.skills)
    qualification_terms = terms(f.qualifications)
    queries = []
    def add(q):
        if q not in queries: queries.append(q)
    add(base + (' ' + ' '.join(facets[:2]) if facets else ''))
    for skill in skill_terms:
        add(base + ' ' + quoted(skill) + (' ' + facets[0] if facets else ''))
    for degree in qualification_terms:
        add(base + ' ' + quoted(degree) + (' ' + facets[0] if facets else ''))
    if f.experience.strip():
        add(base + ' ' + quoted(f.experience.strip()) + (' ' + facets[0] if facets else ''))
    if f.industry.strip(): add(base + ' ' + quoted(f.industry.strip()))
    if f.location.strip(): add(base + ' ' + quoted(f.location.strip()))
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


def match_terms(f: Filters, title: str, snippet: str) -> tuple[str, int]:
    text = (title + ' ' + snippet).casefold()
    candidates = [f.designation, f.title, f.industry, f.location, f.experience] + terms(f.skills) + terms(f.qualifications)
    candidates = list(dict.fromkeys(x.strip() for x in candidates if x.strip()))
    matched = [x for x in candidates if x.casefold() in text]
    return ', '.join(matched), round(100 * len(matched) / max(1, len(candidates)))


def search(f: Filters, max_profiles: int = 100, max_queries: int = 8, on_progress=None) -> tuple[list[dict], list[str]]:
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
                    matches, score = match_terms(f, title, snippet)
                    found[url] = {FIELDS[0]: get_name(title), FIELDS[1]: url,
                                  FIELDS[2]: title, FIELDS[3]: snippet,
                                  FIELDS[4]: matches, FIELDS[5]: score,
                                  FIELDS[6]: query, FIELDS[7]: 'Not verified'}
                    if len(found) >= max_profiles: break
            except Exception as exc:
                warnings.append(f"Query {index+1} unavailable ({type(exc).__name__}); external search may rate-limit requests.")
    if on_progress: on_progress(len(queries), len(queries), len(found))
    return sorted(found.values(), key=lambda r: r[FIELDS[5]], reverse=True), warnings
