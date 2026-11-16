# LinkedIn Candidate Finder — revised deployment package

A Streamlit application that discovers live, publicly indexed LinkedIn profile links and keeps only results with evidence for every submitted filter. There are no preset cities, job titles, candidate lists, fabricated records, or runtime demo fallbacks.

## What changed

- One Designation field; redundant Job title removed.
- Result slider: 10–500. The former 40-result collection ceiling is removed.
- Automatic page traversal and query planning; no user-facing query-count slider.
- All filters are mandatory when supplied. There is no loose/strict toggle.
- Review status and misleading keyword percentage scores removed.
- Canonical LinkedIn profile URLs, deduplication, and page-repeat detection.
- Per-request hard timeout, bounded transient retries, a circuit breaker, and rate-limit stopping.
- Partial matches are preserved. Provider failure is distinguished from no supported results.
- CSV/Excel exports, clickable links, frozen headers, and formula-injection protection.
- Results and downloads remain bound to the submitted filter snapshot. Invalid resubmission clears old results.

## Important limits before deploying

This is **search-index discovery**, not a full LinkedIn profile scraper. It does not log into LinkedIn or retrieve complete profile histories. Search titles/snippets may be incomplete or outdated. Passing an evidence check does not establish a person's current employment, location, industry, or degree.

**500 is a maximum requested count, not a guaranteed yield.** Pagination continues until the target, exhaustion/repeated pages, provider failure, or a server budget is reached. Missing evidence means exclusion; the app never inserts irrelevant people just to fill the requested count.

The free DDGS search provider can time out or block shared hosting addresses. Code cannot guarantee service availability or make the provider return 500 relevant indexed profiles. During preparation, the live provider request timed out; genuine retrieval and 500 real matches were not verified. The code accurately reports this state instead of saying “no matching people exist.” Reliable higher-volume production retrieval may require replacing the provider with a licensed search/data API; no paid service or key is required by this package as delivered.

## Redeploy on Streamlit Community Cloud

1. Extract this ZIP.
2. Replace the existing application files in the GitHub repository with the **contents** of `linkedin_candidate_finder/`. Keep `app.py`, `search_engine.py`, `exports.py`, and `requirements.txt` together at the repository root. Commit all files, including the revised requirements.
3. Set the Streamlit entrypoint to `app.py` and use Python **3.12**. If you intentionally keep the folder, set the entrypoint to `linkedin_candidate_finder/app.py` and keep its requirements next to it.
4. Reboot/redeploy the app after the dependency installation finishes. No secrets or API keys are needed for DDGS.
5. Start with Designation = `Software Engineer`, Location = `Austin`, Maximum profiles = `10`, and leave other filters empty. Then test one additional filter at a time.
6. Check Search diagnostics. If the provider fails, changing filters does not fix connectivity. Check Streamlit logs and retry later; do not interpret a failed search as a candidate count.
7. Test 500 only after the provider successfully returns records for a broad search.

Pinned packages match the locally tested environment. Re-test before upgrading them. Installing the development dependencies is not necessary on Streamlit.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Precise filter behavior

| Field | Acceptance rule |
| --- | --- |
| Designation | Literal whole phrase in the role headline or an explicit current-role/designation label. Not inferred from a candidate name or an arbitrary mention of hiring that role. |
| Location | All comma-separated parts must occur in explicit geographical evidence such as `Location: Austin, TX`, `Based in Austin`, or `Greater Austin Area`. Bare person names and historical clues are excluded. Conflicting explicit location clues are rejected. No hard-coded city dictionary. |
| Industry | Literal whole phrase in non-negated professional search-result text. This is keyword evidence, not access to LinkedIn's structured industry field. |
| Experience | `5` / `5+` means minimum five years; `3-7` means inclusive range. Requires a numeric `years of experience` statement. Years at one employer, dates, and total careers are not inferred or added. Unbounded `7+` evidence cannot satisfy a finite maximum of seven. |
| Skills | Comma/semicolon-separated terms, all required as whole terms. Java does not match JavaScript; SQL does not match MySQL; C does not match C++/C#. |
| Qualifications | Literal comma/semicolon-separated phrases, all required. MS does not match Systems. BS/MS/MSc and full degree names are not silently treated as equivalent. |

Use plain phrases; Boolean expressions and semantic equivalences are not interpreted. Exact wording favors precision over recall. Up to 20 skills and 20 qualifications are accepted; excess input is rejected instead of silently truncated. The required terms are never relaxed during result acceptance, even when the automatic query planner uses broader retrieval queries.

Location-only and other single-field searches are supported. A city, state, or country can be any user-entered name; aliases (`TX` versus `Texas`, `USA` versus `United States`) are not guessed. A snippet containing only `Austin, TX` without an explicit location marker may be excluded. This is deliberate: arbitrary comma-separated words can be names or skills, not verified geography. Even these conservative checks cannot prove that every accepted snippet describes the person's current state.

## Collection, performance, and exceptions

- Transport batches request up to 100 raw results **per page**, not a total cap of 100. Collection supports up to 500 accepted, unique links.
- Query/page traversal is round-robin. Short pages do not prematurely end pagination; empty pages and repeated pages terminate a query.
- New evidence for a previously rejected URL is re-evaluated. Accepted URLs are deduplicated across queries, pages, tracking parameters, and LinkedIn country subdomains.
- Default server budgets: 120 provider calls, 240 seconds, 0.5-second spacing, 15-second internal network timeout, one retry for a timeout, and a three-consecutive-error circuit breaker. These are operational bounds, not candidate presets.
- Each DDGS call runs in a disposable subprocess with a hard wall-clock wait of `timeout + 5` seconds plus brief process cleanup. This prevents a backend thread from indefinitely hanging the UI. A search time budget can overrun by the final in-flight request and cleanup.
- Rate limits/blocks stop the search without retries, proxy rotation, or CAPTCHA handling.
- No cross-user result cache or candidate database. Results live in the Streamlit session; users choose when to export them.
- No network calls happen in unit tests. Synthetic provider responses exist only in `tests/`; production never uses them.

The `Provider` protocol in `search_engine.py` is the integration point for a future authorized API. Its `fetch(query, page, page_size)` method returns `{href, title, body}` records and raises `ProviderError` for failures. Do not treat an API's page size as its total result allowance; implement the API's documented pagination and quotas.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The suite covers required filters, token boundaries, location-name ambiguity, historical/conflicting locations, experience ranges, query completeness, profile URL validation, 500-record pagination with simulated responses, duplicates, repeated pages, retries, rate limits, budgets, process timeout cleanup, spreadsheet export protection, and Streamlit form/session behavior.

Optional live connectivity check (prints only status/counts):

```bash
python smoke_test.py
```

This sends one real query and can return `provider_failed` or `budget_reached`. It is a connectivity diagnostic, not a claim that ten or 500 real matches exist. Run standalone Python scripts that call the subprocess provider under an `if __name__ == '__main__':` guard, as shown in `smoke_test.py`.

## Files

- `app.py`: UI and session lifecycle.
- `search_engine.py`: filters, query planning, provider, pagination, errors, evidence.
- `exports.py`: Excel/CSV generation.
- `requirements.txt`: pinned deployment dependencies.
- `requirements-dev.txt`: development/test dependencies.
- `smoke_test.py`: optional one-request live check.
- `tests/`: deterministic regression/UI tests.
- `VALIDATION.md`: validation performed on this revision.

## Upstream documentation

The DDGS project documents the `page`, `max_results`, `backend`, and `timeout` parameters:
https://github.com/deedy5/ddgs

Public indexing, provider availability, and snippet completeness remain external dependencies. Respect applicable source/provider terms when deploying and using the app.
