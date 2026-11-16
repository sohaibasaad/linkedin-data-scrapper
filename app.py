import io
import pandas as pd
import streamlit as st
from search_engine import Filters, FIELDS, build_queries, search

st.set_page_config(page_title='Candidate Discovery · Python', page_icon='🔎', layout='wide')
st.title('🔎 Candidate Discovery')
st.caption('Find publicly indexed LinkedIn profile links using an external search engine. No LinkedIn login or profile crawling.')
st.info('Search snippets are incomplete and may be outdated. Scores measure keyword overlap in snippets, NOT candidate suitability. Review each candidate manually and respect privacy, search-provider rules and LinkedIn terms.')

with st.form('search_form'):
    a,b,c = st.columns(3)
    with a:
        designation = st.text_input('Designation', placeholder='Software Engineer')
        title = st.text_input('Job title', placeholder='Senior Backend Developer')
        industry = st.text_input('Industry', placeholder='Information Technology')
    with b:
        location = st.text_input('Location', placeholder='Karachi, Pakistan')
        experience = st.text_input('Experience keywords', placeholder='5 years')
        skills = st.text_input('Skills (comma-separated)', placeholder='Python, Django, PostgreSQL')
    with c:
        qualifications = st.text_input('Qualifications (comma-separated)', placeholder='BS Computer Science, MS')
        max_profiles = st.slider('Maximum results to collect', 10, 200, 100, 10)
        max_queries = st.slider('Search queries (more may hit rate limits)', 1, 12, 6)
    run = st.form_submit_button('Find candidates', type='primary', use_container_width=True)

f = Filters(designation, title, industry, location, experience, skills, qualifications)
with st.expander('Show generated public web queries'):
    for q in build_queries(f, max_queries): st.code(q)

if run:
    bar = st.progress(0, text='Searching public web index…')
    def progress(i, total, found):
        bar.progress(min(1.0, i / max(total, 1)), text=f'Search queries: {i}/{total} · unique links: {found}')
    with st.spinner('Searching…'):
        try:
            rows, warnings = search(f, max_profiles, max_queries, progress)
            st.session_state['rows'] = rows
            st.session_state['warnings'] = warnings
        except Exception as e:
            st.session_state['rows'] = []
            st.session_state['warnings'] = [f'Search engine unavailable: {type(e).__name__}: {str(e)[:180]}']
    bar.empty()

for warning in st.session_state.get('warnings', []): st.warning(warning)
rows = st.session_state.get('rows', [])
if rows:
    df = pd.DataFrame(rows, columns=FIELDS)
    st.subheader(f'{len(df)} distinct indexed profile links')
    threshold = st.slider('Minimum snippet keyword overlap (%)', 0, 100, 0, 10)
    df = df[df['Match score'] >= threshold].copy()
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={'LinkedIn URL': st.column_config.LinkColumn('LinkedIn URL'),
                                'Match score': st.column_config.NumberColumn('Match score (%)', min_value=0, max_value=100)})
    st.caption(f'{len(df)} shown. Search engines may not return 100–500 links, even with a high requested limit. Qualification and years of experience are keyword searches, not verified structured filters.')
    xls = io.BytesIO()
    with pd.ExcelWriter(xls, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Candidates')
        sheet = writer.sheets['Candidates']
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for col, width in {'A':25,'B':55,'C':55,'D':85,'E':35,'F':18,'G':75,'H':20}.items():
            sheet.column_dimensions[col].width = width
    c1,c2=st.columns(2)
    with c1: st.download_button('⬇ Download Excel', xls.getvalue(), 'candidate_links.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', use_container_width=True)
    with c2: st.download_button('⬇ Download CSV', df.to_csv(index=False).encode('utf-8-sig'), 'candidate_links.csv', 'text/csv', use_container_width=True)
elif run:
    st.warning('No indexed profiles found. Try broader filters, fewer quoted phrases, or fewer search queries.')
