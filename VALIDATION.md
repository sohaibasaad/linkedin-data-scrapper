# v2.2 validation — 16 November 2026

54 tests and 7 subtests passed on Python 3.12 with pandas 2.3.3 and pycountry 24.6.1. This includes the existing collection/export/UI tests and new regression cases for Full-Stack, FullStack, role-leading snippets, Toronto/Ontario/Canada geography, wrong roles, unrelated Canada mentions, and query fallback.

The provided screenshot proves that the deployed provider returned seven inspected results: four failed designation, two failed location, and one had a non-profile URL. It does not include the original result text, so this revision has NOT been verified against those exact seven records. Regression fixtures are synthetic; no claims of live candidate accuracy or 500 available matches are made.

Kept Python 3.12 as the recommended deployment runtime. Updated deprecated layout parameters. The earlier network check below remains historical, not a new v2.2 live test.

---

# Validation — 16 November 2026

## Passed

- 41 automated tests passed, plus 7 subtests, using Python 3.12.
- Streamlit initial render, six input fields, single result slider with a maximum of 500, and removal of Job title, query-count control, and loose-match toggle.
- All-filter evidence checks; role-headline validation; token boundaries; arbitrary input locations; rejection of bare Austin names, historical/conflicting location clues, and missing location components.
- Numeric minimum/range experience checks, including finite maximum versus plus/open-ended evidence.
- Automatic paging collected exactly 500 unique accepted records across five simulated 100-record pages. This verifies code behavior, NOT real provider capacity.
- Timeout retry, circuit breaking, rate-limit stopping, hard-timeout worker cleanup, partial-result preservation, malformed records, URL canonicalization, duplicate pages, request/time budgets.
- Excel/CSV headers, removal of Review status, spreadsheet formula protection, and safe link export.
- Submitted-search snapshot, exports, and clearing stale results after invalid input.

## Live provider check

One request using the final subprocess adapter for `Software Engineer` / `Austin`:

- Provider calls: 1.
- Successful pages: 0.
- Accepted matches: 0.
- Outcome: `provider_failed` with a timeout warning.
- Observed elapsed time: approximately 15.6 seconds using the smoke-test timeout configuration.

The local code, UI, and simulated 500-result flow passed validation. Real profile accuracy, live 500-result collection, and access from the user's Streamlit host remain unverified. The deployment has not been changed.

## Remaining external limitations

DDGS availability/rate limits, search-index coverage, and the accuracy/completeness of search snippets cannot be corrected by a filter function. This package does not claim verified current profile attributes. Conservative evidence rules intentionally exclude ambiguous records and may miss valid people.

## Dependency environment

- Python 3.12
- streamlit 1.67.0
- pandas 2.2.3
- ddgs 9.16.1
- openpyxl 3.1.5

A pytest plugin installed in the execution environment emitted a deprecation warning; there were no test failures.
