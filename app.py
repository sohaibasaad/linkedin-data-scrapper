"""Streamlit entrypoint. Results belong to a submitted filter snapshot, not an edited form."""
from dataclasses import asdict
import logging
import time

import pandas as pd
import streamlit as st

from exports import csv_bytes, excel_bytes
from search_engine import FIELDS, Filters, ValidationError, search, validate

LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title='LinkedIn Candidate Finder', page_icon='🔎', layout='wide')
st.title('LinkedIn Candidate Finder')
st.caption('Live discovery of publicly indexed LinkedIn profile links. No preset cities, job titles, or sample records.')
st.info('Every entered filter must have supporting text in the search result. Missing evidence is excluded. '
        'Search snippets may be incomplete or outdated; these are not verified full LinkedIn profiles. '
        'The result target is a maximum, not a promise of available matches.')

with st.form('candidate_search'):
    first, second = st.columns(2)
    with first:
        designation = st.text_input('Designation', placeholder='Software Engineer', max_chars=500,
                                   help='Literal role phrase; no automatic synonyms or Boolean operators.')
        location = st.text_input('Location', placeholder='Austin', max_chars=500,
                                help='Any location. Use comma-separated city/state/country to require all parts. '
                                     'Requires explicit location wording; names alone never qualify. '
                                     'Spell locations as they appear in snippets; aliases are not guessed.')
        industry = st.text_input('Industry', placeholder='Financial Services', max_chars=500,
                                help='Required phrase in professional search-result text; not a verified LinkedIn industry field.')
    with second:
        experience = st.text_input('Experience (years; minimum or range)', placeholder='5+ or 3-7', max_chars=40,
                                   help='5 or 5+ means at least five years. 3-7 means inclusive three to seven. '
                                        'Requires an explicit years-of-experience statement; dates and tenure are not inferred.')
        skills = st.text_input('Skills (comma-separated; all required)', placeholder='Python, Django', max_chars=500,
                               help='Each skill is required as a whole term. Java does not match JavaScript.')
        qualifications = st.text_input('Qualifications (comma-separated; all required)', placeholder='Bachelor of Science', max_chars=500,
                                       help='Literal phrases, all required. No inferred degree equivalences.')
    maximum = st.slider('Maximum profiles', min_value=10, max_value=500, value=100, step=10)
    run = st.form_submit_button('Find candidates', type='primary', use_container_width=True)

if run:
    filters = Filters(designation, location, industry, experience, skills, qualifications)
    # Clear old exports immediately: failed/invalid searches must never show old records as new ones.
    for key in ('report', 'submitted_filters', 'exports'):
        st.session_state.pop(key, None)
    try:
        validate(filters, maximum)
        now = time.monotonic()
        if now - st.session_state.get('last_search_started', -100) < 5:
            st.warning('Please wait a few seconds before starting another search.')
        else:
            st.session_state['last_search_started'] = now
            bar = st.progress(0.0, text='Starting live search…')
            def update(stats):
                bar.progress(min(stats['matches'] / stats['requested'], 1.0),
                             text=f"{stats['matches']} / {stats['requested']} matches · "
                                  f"{stats['scanned']} results checked · {stats['requests']} requests")
            try:
                with st.spinner('Searching and checking every filter. Large searches can take several minutes.'):
                    report = search(filters, maximum, update)
                st.session_state['report'] = report
                st.session_state['submitted_filters'] = asdict(filters)
            finally:
                bar.empty()
    except ValidationError as exc:
        st.error(str(exc))
    except Exception:
        LOGGER.exception('Candidate search failed unexpectedly')
        st.error('An unexpected application error interrupted the search. No previous results are being shown. '
                 'Check the Streamlit app logs and retry after resolving the error.')

report = st.session_state.get('report')
if report is not None:
    filters_used = st.session_state.get('submitted_filters', {})
    st.caption('Results below belong to the last submitted search. Editing the form does not refresh them until Find candidates is pressed.')
    st.write('**Applied filters:** ' + '; '.join(f'{k.title()}: {v}' for k, v in filters_used.items() if v.strip()))
    a, b, c = st.columns(3)
    a.metric('Matching profiles', len(report.rows))
    b.metric('Result target', report.requested)
    c.metric('Search time', f'{report.elapsed:.1f}s')
    messages = {
        'target_reached': 'Requested maximum reached. All listed results passed the entered snippet-evidence checks.',
        'exhausted': 'The provider exhausted available pages. Fewer supported matches may exist in its index.',
        'budget_reached': 'Search stopped at the server time/request budget. The result set is partial.',
        'rate_limited': 'The provider blocked or rate-limited this search. This does not mean no matching profiles exist.',
        'provider_failed': 'The search provider is unavailable. This does not mean no matching profiles exist.',
        'partial_provider_failure': 'Some searches failed. The result set may be incomplete.',
    }
    message = messages.get(report.stop_reason, 'Search finished.')
    if report.stop_reason == 'target_reached':
        st.success(message)
    elif report.stop_reason in ('rate_limited', 'provider_failed') and not report.rows:
        st.error(message)
    else:
        st.warning(message)
    for warning in report.warnings:
        st.warning(warning)
    if report.rows:
        frame = pd.DataFrame(report.rows, columns=FIELDS)
        st.dataframe(frame, hide_index=True, use_container_width=True,
                     column_config={'LinkedIn URL': st.column_config.LinkColumn('LinkedIn URL')})
        try:
            if 'exports' not in st.session_state:
                st.session_state['exports'] = (excel_bytes(report.rows), csv_bytes(report.rows))
            xlsx, csv = st.session_state['exports']
            left, right = st.columns(2)
            left.download_button('Download Excel', xlsx, 'linkedin_candidates.xlsx',
                                 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
            right.download_button('Download CSV', csv, 'linkedin_candidates.csv', 'text/csv', use_container_width=True)
        except Exception:
            LOGGER.exception('Export failed')
            st.error('Results are available above, but the export failed. Check the application logs.')
    elif report.successful_pages:
        st.info('No results passed every evidence check in the pages retrieved. Check diagnostics before changing filters.')
    with st.expander('Search diagnostics'):
        st.write(f'Requests: {report.requests} · Successful pages: {report.successful_pages} · '
                 f'Failed requests: {report.failed_requests} · Results checked: {report.scanned} · '
                 f'Duplicates skipped: {report.duplicates}')
        st.caption('Rejected counts show the first failed check for each inspected result. '
                   'No profile is added to meet a target unless all checks pass.')
        if report.rejected:
            st.dataframe(pd.DataFrame(report.rejected.items(), columns=['Missing/invalid evidence', 'Count']), hide_index=True)
        st.write('Automatically generated queries:')
        for query in report.queries:
            st.code(query, language=None)
