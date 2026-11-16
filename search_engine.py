"""Live indexed-profile discovery with mandatory, conservative snippet evidence.
No city/job lists, demo results, LinkedIn login, or direct profile crawling.
"""
from __future__ import annotations

import html
import math
import multiprocessing as mp
import re
import time
import unicodedata

import pycountry
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import quote, unquote, urlparse

FIELDS = ['Name (from search title)', 'LinkedIn URL', 'Designation evidence',
          'Location evidence', 'Industry evidence', 'Experience evidence',
          'Skills evidence', 'Qualifications evidence', 'Search title',
          'Search snippet', 'Source query']


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Filters:
    designation: str = ''
    location: str = ''
    industry: str = ''
    experience: str = ''
    skills: str = ''
    qualifications: str = ''


@dataclass(frozen=True)
class Limits:
    page_size: int = 100   # Transport batch size, NOT the overall result limit.
    max_requests: int = 120
    max_seconds: float = 240
    timeout: int = 15
    retries: int = 1
    pause: float = 0.5


@dataclass
class SearchReport:
    rows: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    rejection_examples: list[dict] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    requested: int = 100
    requests: int = 0
    successful_pages: int = 0
    failed_requests: int = 0
    scanned: int = 0
    duplicates: int = 0
    stop_reason: str = ''
    elapsed: float = 0


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool = False):
        super().__init__(code)
        self.code, self.retryable = code, retryable


class Provider(Protocol):
    def fetch(self, query: str, page: int, page_size: int) -> list[dict]: ...


def provider_failure(exc: Exception) -> tuple[str, bool]:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if any(x in name + ' ' + message for x in ('ratelimit', 'rate limit', '429', 'captcha', '403', 'forbidden')):
        return 'rate_limited', False
    if 'timeout' in name + ' ' + message or 'timed out' in message:
        return 'timeout', True
    if 'no results found' in message and not any(x in message for x in ('error', 'timeout', 'exception')):
        return 'empty', False
    return 'unavailable', False


def _ddgs_worker(connection, query, page, page_size, timeout):
    """A subprocess provides a wall-clock bound even if a backend stalls internally."""
    try:
        from ddgs import DDGS
        client = DDGS(timeout=timeout)
        rows = list(client.text(query, page=page, max_results=page_size,
                                safesearch='moderate', backend='auto') or [])
        connection.send(('ok', rows))
    except Exception as exc:
        code, retryable = provider_failure(exc)
        connection.send(('ok', []) if code == 'empty' else ('error', code, retryable))
    finally:
        connection.close()


class DDGSProvider:
    """Bounded live requests; no proxy rotation, CAPTCHA bypass or block retries."""
    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def fetch(self, query: str, page: int, page_size: int) -> list[dict]:
        context = mp.get_context('spawn')
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_ddgs_worker,
                                  args=(sender, query, page, page_size, self.timeout), daemon=True)
        started = False
        try:
            process.start()
            started = True
            sender.close()
            if not receiver.poll(self.timeout + 5):
                raise ProviderError('timeout', retryable=True)
            result = receiver.recv()
            if result[0] == 'error':
                raise ProviderError(result[1], result[2])
            return result[1]
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('unavailable') from None
        finally:
            receiver.close()
            sender.close()
            if started:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=1)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=1)
                process.close()


def clean(value: str) -> str:
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', html.unescape(value))).strip()


def terms(value: str) -> list[str]:
    return list(dict.fromkeys(clean(x) for x in re.split(r'[,;\n]+', value) if clean(x)))


def phrase_pattern(term: str) -> str:
    # Technical punctuation is meaningful: Java != JavaScript, C != C++, .NET != NET.
    body = r'\s+'.join(re.escape(t) for t in clean(term).split())
    return r'(?<![\w+#.])' + body + r'(?![\w+#]|\.[\w])'


def phrase(term: str, text: str) -> str:
    match = re.search(phrase_pattern(term), clean(text), re.I)
    return match.group(0) if match else ''


def experience_range(value: str) -> tuple[float, float] | None:
    if not value.strip():
        return None
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:(\+)\s*|[-–]\s*(\d+(?:\.\d+)?)\s*)?(?:years?|yrs?)?\s*', value, re.I)
    if not match:
        raise ValidationError('Experience must be a minimum such as 5 or 5+, or a range such as 3-7.')
    low = float(match[1]); high = float(match[3]) if match[3] else math.inf
    if low > 80 or (high != math.inf and high > 80) or low > high:
        raise ValidationError('Experience must be between 0 and 80 years, with minimum <= maximum.')
    return low, high


def validate(f: Filters, maximum: int) -> None:
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 500:
        raise ValidationError('Requested results must be an integer between 1 and 500.')
    if not any(v.strip() for v in vars(f).values()):
        raise ValidationError('Enter at least one search filter.')
    for key, value in vars(f).items():
        if not isinstance(value, str) or len(value) > 500:
            raise ValidationError(f'{key.title()} must contain at most 500 characters.')
        if any(ord(c) < 32 and c not in '\n\t\r' for c in value):
            raise ValidationError(f'{key.title()} contains unsupported control characters.')
        if value.strip() and not re.search(r'\w', value):
            raise ValidationError(f'{key.title()} must contain a word or number.')
    for key in ('skills', 'qualifications'):
        values = terms(getattr(f, key))
        if len(values) > 20:
            raise ValidationError(f'Use at most 20 {key}; none will be silently dropped.')
        if getattr(f, key).strip() and not values:
            raise ValidationError(f'Enter valid {key}.')
    experience_range(f.experience)


def quoted(value: str) -> str:
    # User fields are literal phrases, never executable search operators.
    return '"' + clean(value).replace('"', ' ').replace('\\', ' ') + '"'


def build_queries(f: Filters) -> list[str]:
    base_terms = [v for v in (f.designation, f.location) if v.strip()]
    extra = [v for v in [f.industry, *terms(f.skills), *terms(f.qualifications)] if v.strip()]
    if f.experience.strip():
        extra.append('years experience')  # numeric range is applied locally, never exact-number retrieval
    def query(values):
        return 'site:linkedin.com/in/ ' + ' '.join(quoted(v) for v in dict.fromkeys(values))
    # Every search retains designation and location. Broader retrieval never relaxes acceptance.
    candidates = [query(base_terms + extra)]
    if base_terms:
        candidates += [query(base_terms)] + [query(base_terms + [v]) for v in extra]
    else:
        candidates += [query([v]) for v in extra]
    # Tokenized fallback retrieves punctuation variants without relaxing local checks.
    role_words = re.split(r'[\s\-‐‑‒–—]+', clean(f.designation))
    if len(role_words) > 1:
        candidates.append(query(role_words + ([f.location] if f.location.strip() else []) + extra))
    return list(dict.fromkeys(q.strip() for q in candidates))


def normalize_profile_url(value: str) -> str | None:
    try:
        p = urlparse(value)
        host = (p.hostname or '').lower()
        if p.scheme not in ('http', 'https') or p.username or p.password or p.port not in (None, 80, 443):
            return None
        if host != 'linkedin.com' and not host.endswith('.linkedin.com'):
            return None
        path = unquote(p.path).rstrip('/')
        if not re.fullmatch(r'/in/[\w-]+', path, flags=re.UNICODE):
            return None
        return 'https://www.linkedin.com' + quote(path.lower(), safe='/-')
    except (ValueError, TypeError):
        return None


def chunks(text: str) -> list[str]:
    # Keep commas inside geographical fields, and decimal points inside experience numbers.
    return [x.strip() for x in re.split(r'[;\n|·•]|\.{3}|(?<=[a-z0-9])\.\s+(?=[A-Z])', text) if x.strip()]


def historical(text: str) -> bool:
    return bool(re.search(r'\b(previously|formerly|former|past|used to|no longer|not based|not located|moved from|relocated from)\b', text, re.I))


def geographic_chain(block: str) -> str:
    """Recognize a compact city/region/country field using the ISO country dataset.
    No custom city/country list and no guessing geography from a person's name.
    """
    parts = [x.strip() for x in block.strip(' .').split(',')]
    if not 2 <= len(parts) <= 4:
        return ''
    if any(not re.fullmatch(r"[\w\s.'’()\-]+", p) or len(p.split()) > 6 for p in parts):
        return ''
    country = parts[-1].casefold()
    for item in pycountry.countries:
        names = [item.name, getattr(item, 'official_name', ''), getattr(item, 'common_name', '')]
        if country in [n.casefold() for n in names if n]:
            return ', '.join(parts)
    return ''


def location_evidence(location: str, title: str, snippet: str) -> str:
    """Only explicit geography; no hard-coded cities and no bare person-name matches.
    Missing/ambiguous geography is rejected instead of guessed. Historical clues rejected.
    """
    if not location.strip():
        return ''
    requested = terms(location)
    markers = r'(?:\blocation\s*[:\-]|\bcurrent city\s*[:\-]|\bbased in\b|\blocated in\b|\blives in\b|\bresides in\b|\bcurrently in\b|\bnow in\b)\s*'
    evidence = []
    for block in chunks(snippet) + chunks(title):
        if historical(block):
            continue
        labeled = re.search(markers + r'(.+)', block, re.I)
        if labeled:
            # Stop before the next structured attribute; skills are not geographic evidence.
            value = re.split(r'\b(?:skills|experience|education|industry|connections|followers)\s*:', labeled[1], flags=re.I)[0]
            evidence.append(value.strip())
        elif geographic_chain(block):
            evidence.append(geographic_chain(block))
        elif re.fullmatch(r'(?:Greater\s+)?[\w\s,\-]+\s+(?:Area|Region)', block, re.I):
            evidence.append(block)
    # Contradictory explicit locations are ambiguous; do not select whichever happens to match.
    if not evidence or any(not all(phrase(part, value) for part in requested) for value in evidence):
        return ''
    return evidence[0]


def get_name(title: str) -> str:
    parts = re.split(r'\s+[|–—-]\s+', title, maxsplit=1)
    if len(parts) < 2 or 'linkedin' in parts[0].casefold() or len(parts[0]) > 100:
        return ''
    return parts[0].strip()


def professional_text(title: str, snippet: str) -> str:
    # Exclude the leading name from designation/skill/degree checks.
    parts = re.split(r'\s+[|–—-]\s+', title, maxsplit=1)
    rest = parts[1] if len(parts) > 1 else ''
    name = get_name(title)
    body = snippet
    if name and clean(body).casefold().startswith(name.casefold()):
        body = clean(body)[len(name):].lstrip(' ,:-–—')
    return rest + '\n' + body


def supported(term: str, text: str) -> str:
    for block in chunks(text):
        if historical(block) or re.search(r'\b(?:no|not|without|lack(?:s|ing)?|hiring|seeking|aspiring|recruiting)\b', block, re.I):
            continue
        match = phrase(term, block)
        if match:
            return block[:1000]
    return ''


def designation_evidence(value: str, title: str, snippet: str) -> str:
    """Match a role headline or explicit role label, not arbitrary mentions of jobs."""
    def role_text(text):
        text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
        return re.sub(r'(?<=[\w])[-‐‑‒–—]+(?=[\w])', ' ', text)
    role = role_text(value)
    parts = re.split(r'\s+[|–—-]\s+', title)
    if len(parts) > 1:
        headline = parts[1]
        match = supported(role, role_text(headline))
        if match:
            return match
    for block in chunks(snippet):
        labeled = re.search(r'\b(?:designation|job title|current role|current position|role|works as)\s*[:\-]?\s+(.+)', block, re.I)
        if labeled and not historical(block):
            match = supported(role, role_text(labeled[1]))
            if match:
                return block
        normalized = role_text(block)
        # Accept a snippet headline/self-description; not arbitrary role mentions.
        if re.match(r'(?:I am (?:a |an )?|(?:Senior|Junior|Lead|Staff|Principal)\s+)?' + phrase_pattern(role), normalized, re.I):
            if supported(role, normalized):
                return block
    return ''


def experience_evidence(value: str, text: str) -> str:
    desired = experience_range(value)
    if desired is None:
        return ''
    number = r'(\d+(?:\.\d+)?)'
    pattern = re.compile(r'(?<![\w.])(?:(over|more than|at least)\s+)?' + number +
                         r'\s*(?:(\+)|[-–]\s*' + number + r')?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional\s+|relevant\s+|total\s+|work\s+)?experience\b', re.I)
    for block in chunks(text):
        if historical(block) or re.search(r'\b(?:no|not|without|less than|under|up to)\b', block, re.I):
            continue
        for match in pattern.finditer(block):
            low = float(match[2])
            high = float(match[4]) if match[4] else (math.inf if match[1] or match[3] else low)
            if desired[0] <= low <= high <= desired[1]:
                return match.group(0)
    return ''


def evaluate(f: Filters, title: str, snippet: str) -> tuple[dict[str, str], str]:
    text = professional_text(title, snippet)
    evidence = {}
    clue = designation_evidence(f.designation, title, snippet) if f.designation.strip() else ''
    if f.designation.strip() and not clue:
        return {}, 'Designation'
    evidence['Designation evidence'] = clue
    for label, value in [('Industry', f.industry)]:
        clue = supported(value, text) if value.strip() else ''
        if value.strip() and not clue:
            return {}, label
        evidence[label + ' evidence'] = clue
    clue = location_evidence(f.location, title, snippet)
    if f.location.strip() and not clue:
        return {}, 'Location'
    evidence['Location evidence'] = clue
    clue = experience_evidence(f.experience, text)
    if f.experience.strip() and not clue:
        return {}, 'Experience'
    evidence['Experience evidence'] = clue
    for label, value in [('Skills', f.skills), ('Qualifications', f.qualifications)]:
        clues = [supported(term, text) for term in terms(value)]
        if any(not clue for clue in clues):
            return {}, label
        evidence[label + ' evidence'] = ' | '.join(dict.fromkeys(clues))
    return evidence, ''


def search(f: Filters, max_profiles: int = 100, on_progress: Callable | None = None,
           *, provider: Provider | None = None, limits: Limits = Limits(),
           clock=time.monotonic, sleep=time.sleep) -> SearchReport:
    validate(f, max_profiles)
    report = SearchReport(requested=max_profiles, queries=build_queries(f))
    started = clock()
    rejected = Counter()
    found: dict[str, dict] = {}
    fingerprints: dict[str, set] = {}
    pending_queries = iter(report.queries)
    queue = deque([(next(pending_queries), 1, 0)])
    try:
        provider = provider or DDGSProvider(limits.timeout)
    except Exception:
        report.stop_reason = 'provider_failed'
        report.warnings.append('Search provider could not start. Check dependencies and server connectivity.')
        return report
    consecutive_errors = 0
    def warn(message):
        if message not in report.warnings:
            report.warnings.append(message)
    while len(found) < max_profiles:
        if not queue:
            next_query = next(pending_queries, None)
            if next_query is None:
                break
            queue.append((next_query, 1, 0))
        if report.requests >= limits.max_requests or clock() - started >= limits.max_seconds:
            report.stop_reason = 'budget_reached'; break
        query, page, stale = queue.popleft()
        if on_progress:
            on_progress({'matches': len(found), 'requested': max_profiles, 'requests': report.requests,
                         'scanned': report.scanned, 'page': page})
        batch = None
        for attempt in range(limits.retries + 1):
            if report.requests >= limits.max_requests or clock() - started >= limits.max_seconds:
                report.stop_reason = 'budget_reached'; break
            report.requests += 1
            try:
                batch = provider.fetch(query, page, limits.page_size)
                if not isinstance(batch, list):
                    raise ProviderError('invalid_response')
                report.successful_pages += 1
                consecutive_errors = 0
                break
            except Exception as exc:
                report.failed_requests += 1
                consecutive_errors += 1
                code = exc.code if isinstance(exc, ProviderError) else 'unavailable'
                if code == 'rate_limited':
                    warn('The search provider rate-limited or blocked requests. Search stopped; retained matches are available.')
                    report.stop_reason = 'rate_limited'; break
                warn(f'Search provider {code.replace("_", " ")}; some pages could not be retrieved.')
                if consecutive_errors >= 3:
                    report.stop_reason = 'provider_failed'; break
                if not isinstance(exc, ProviderError) or not exc.retryable or attempt >= limits.retries:
                    break
                sleep(min(2 ** attempt, 4))
        if report.stop_reason:
            break
        if batch is None:
            continue
        if not batch:
            continue  # This query is exhausted; do not pretend the requested total was reached.
        seen = fingerprints.setdefault(query, set())
        fresh = 0
        for item in batch:
            if not isinstance(item, dict):
                rejected['Malformed provider result'] += 1; continue
            raw_url = item.get('href') or item.get('url') or ''
            title, snippet = item.get('title') or '', item.get('body') or ''
            if not all(isinstance(v, str) for v in (raw_url, title, snippet)):
                rejected['Malformed provider result'] += 1; continue
            title, snippet = clean(title), clean(snippet)
            fingerprint = (raw_url, title, snippet)
            if fingerprint in seen:
                report.duplicates += 1; continue
            seen.add(fingerprint); fresh += 1; report.scanned += 1
            url = normalize_profile_url(raw_url)
            if not url:
                rejected['Not a LinkedIn profile URL'] += 1; continue
            if url in found:
                report.duplicates += 1; continue
            evidence, failure = evaluate(f, title, snippet)
            if failure:
                rejected[failure] += 1
                if len(report.rejection_examples) < 10:
                    report.rejection_examples.append({'Reason': failure, 'Title': title, 'Snippet': snippet, 'URL': url})
                continue
            found[url] = {'Name (from search title)': get_name(title), 'LinkedIn URL': url,
                          **evidence, 'Search title': title, 'Search snippet': snippet, 'Source query': query}
            if len(found) >= max_profiles:
                break
        stale = stale + 1 if fresh == 0 else 0
        if stale < 2:
            queue.append((query, page + 1, stale))
        else:
            warn('A query stopped because the provider repeated pages without new results.')
        if queue and len(found) < max_profiles:
            sleep(limits.pause)
    report.rows = list(found.values())
    report.rejected = dict(rejected)
    report.elapsed = round(clock() - started, 2)
    report.stop_reason = report.stop_reason or ('target_reached' if len(found) >= max_profiles else
                                              ('partial_provider_failure' if report.successful_pages else 'provider_failed') if report.failed_requests else 'exhausted')
    if on_progress:
        on_progress({'matches': len(found), 'requested': max_profiles, 'requests': report.requests,
                     'scanned': report.scanned, 'page': 0})
    return report
