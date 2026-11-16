# Free Python Candidate Discovery

Streamlit dashboard that discovers **publicly indexed links** to LinkedIn member profiles using external web search, filters search results using conservative location clues, and exports CSV or Excel. **This is not a LinkedIn profile scraper:** it never fetches LinkedIn pages, does not authenticate, and does not bypass rate limits, CAPTCHAs or access controls.

## What it does

- Inputs: designation, job title, industry, location, experience text, comma-separated skills, qualifications.
- Builds multiple search queries using `site:linkedin.com/in/`.
- Uses the open-source `ddgs` metasearch client to obtain search-result titles, snippets and public URLs (subject to search-provider availability and rules).
- Deduplicates profile URLs and scores **snippet keyword overlap only**.
- Displays links in a Streamlit table and downloads Excel or CSV.

**Limitations:** Search results can be absent, throttled, stale or inaccurate. Availability of 100–500 profiles is not guaranteed. Degree, skills, seniority, industry, and experience are *query terms*, not verified fields. It does not extract emails, phone numbers, private details or full LinkedIn bios. Do not treat its output as a validated recruitment database. Manually verify results and respect applicable privacy, licensing, and platform terms. LinkedIn's user agreement places restrictions on copying or reusing LinkedIn-derived information even via third parties; assess your usage before collecting or retaining results.

## Local setup (Python 3.10+)

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Visit http://localhost:8501. No API key or paid account required. Network access is needed for search.

## Publish via GitHub + free Streamlit hosting

1. Create an empty GitHub repository.
2. Upload `app.py`, `search_engine.py`, `requirements.txt`, `.gitignore`, `README.md` and `tests/` to the repository. Do **not** upload candidate export files or personal data.
3. Open https://share.streamlit.io and sign in with GitHub.
4. Create a new app, select your repository, main branch and `app.py` entry point.
5. Deploy. You receive a `*.streamlit.app` website to open in the browser.

GitHub hosts the code, **not the running Python server**. Streamlit Community Cloud hosts the running Python app free under its resource and usage limits. A publicly deployed app can be used by anyone with access; choose private sharing/access appropriately for recruitment work.

## Test

```bash
python -m unittest discover -s tests -v
```

## Design choices

- There are no requests to `linkedin.com` and no Selenium/Playwright or cookie collection.
- The result name is explicitly *unverified*, inferred at most from search-result title.
- Exports contain search-result snippets and discovery metadata, not verified candidate records.
- The number of returned links depends on the search provider, indexing and rate limits.

## Next steps

For reliable structured filtering against qualifications, years of experience, and skills, use a consent-based applicant database or a suitably licensed recruiting data source, and replace the `search` adapter in `search_engine.py`.

## Location filter fix (v2)

Previously the word `Austin` in `Austin Smith` could satisfy the location filter, because matching was a substring check and no location check was mandatory. Now **every search query** contains the requested location, and the result is only included when the search result title/snippet explicitly suggests a geographic location (e.g., `Location: Austin`, `Based in Austin`, `Austin, TX`, `Greater Austin Area`). A name match alone is rejected.

This is intentionally conservative: **unknown locations are excluded** and search snippets are **not proof of current candidate location**. A match is a review lead, not a validated fact. Other input fields are search query hints; enable the checkbox to require every entered keyword to appear in the snippet/title (this may sharply reduce recall).

After replacing the files on GitHub, Streamlit Community Cloud normally rebuilds the app. Confirm you can see the checkbox and `Location evidence` column; otherwise restart/redeploy the app in Streamlit's dashboard.
