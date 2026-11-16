import pytest
from search_engine import Filters, evaluate, location_evidence, build_queries

@pytest.mark.parametrize('title', [
    'Jane Doe - Full-Stack Developer',
    'Jane Doe - Senior Full‑Stack Developer at Acme',
    'Jane Doe - Full Stack Developer',
    'Jane Doe - FullStack Developer',
])
def test_canadian_role_punctuation(title):
    evidence, rejected = evaluate(Filters(designation='full stack developer', location='canada'),
                                  title, 'Toronto, Ontario, Canada')
    assert not rejected
    assert evidence['Location evidence'] == 'Toronto, Ontario, Canada'

@pytest.mark.parametrize('snippet', ['Full-Stack Developer at Acme; Toronto, Ontario, Canada',
                                      'I am a full-stack developer; Vancouver, Canada'])
def test_role_snippet_without_role_label(snippet):
    assert not evaluate(Filters('full stack developer', 'canada'), 'Jane Doe | LinkedIn', snippet)[1]

@pytest.mark.parametrize('snippet', ['Austin, Python', 'Python, Java', 'Works with Canada clients',
                                      'Previously in Toronto, Ontario, Canada', 'Location: Dallas, Texas, United States'])
def test_geography_not_inferred_from_unrelated_text(snippet):
    assert not location_evidence('canada', 'Canada Smith - Developer', snippet)


def test_wrong_role_rejected():
    assert evaluate(Filters('full stack developer', 'canada'),
                    'Jane Doe - Recruiter', 'Hiring full-stack developer; Toronto, Ontario, Canada')[1] == 'Designation'


def test_fallback_query_retains_requested_terms():
    queries = build_queries(Filters('full stack developer', 'canada'))
    assert len(queries) == 2
    assert queries[1] == 'site:linkedin.com/in/ "full" "stack" "developer" "canada"'
