"""Deterministic regression cases. Synthetic provider fixtures are tests only."""
import math
import unittest
from search_engine import (Filters, Limits, ProviderError, ValidationError, build_queries,
                           evaluate, experience_evidence, experience_range, location_evidence,
                           normalize_profile_url, phrase, search, validate)

FAST = Limits(pause=0, max_seconds=60, retries=1)


def record(i=1, snippet='Location: Austin; Python; 7 years of experience; Bachelor of Science; Financial Services',
           title='Jane Doe - Software Engineer', url=None):
    return {'href': url or f'https://www.linkedin.com/in/person-{i}', 'title': title, 'body': snippet}


class FakeProvider:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []
    def fetch(self, query, page, page_size):
        self.calls.append((query, page, page_size))
        value = self.fn(query, page, len(self.calls))
        if isinstance(value, Exception):
            raise value
        return value


class FilterTests(unittest.TestCase):
    def test_all_filters_required(self):
        f = Filters('Software Engineer', 'Austin', 'Financial Services', '5+', 'Python', 'Bachelor of Science')
        self.assertEqual(evaluate(f, record()['title'], record()['body'])[1], '')
        for value in ('Austin', 'Financial Services', 'Python', 'Bachelor of Science', '7 years of experience'):
            self.assertTrue(evaluate(f, record()['title'], record()['body'].replace(value, ''))[1])
        self.assertEqual(evaluate(f, 'Jane Doe - Dentist', record()['body'])[1], 'Designation')

    def test_token_boundaries(self):
        for requested, text in [('Java', 'JavaScript'), ('SQL', 'MySQL'), ('MS', 'Systems'),
                                ('C', 'C++'), ('C', 'C#'), ('.NET', 'ASP.NET'), ('Python', 'Pythons')]:
            with self.subTest(requested=requested):
                self.assertFalse(phrase(requested, text))
        for requested, text in [('C++', 'C++ developer'), ('C#', 'C# developer'),
                                ('.NET', '.NET developer'), ('Node.js', 'Node.js developer'),
                                ('Java', 'Java, Python'), ('SQL', 'SQL.')]:
            self.assertTrue(phrase(requested, text))

    def test_arbitrary_designations(self):
        for title in ('Dental Surgeon', 'Quantity Surveyor', 'Développeur logiciel'):
            self.assertFalse(evaluate(Filters(designation=title), 'Jane Doe - ' + title, '')[1])

    def test_designation_is_role_not_random_mention(self):
        self.assertTrue(evaluate(Filters(designation='Software Engineer'),
                                'Jane Doe - Recruiter', 'I work with Software Engineer teams')[1])
        self.assertFalse(evaluate(Filters(designation='Software Engineer'),
                                 'Jane Doe | LinkedIn', 'Current role: Software Engineer')[1])
        self.assertTrue(evaluate(Filters(designation='Software Engineer'),
                                'Jane Doe - Former Software Engineer', 'Now a recruiter')[1])

    def test_name_not_role(self):
        self.assertTrue(evaluate(Filters(designation='Austin'), 'Austin Smith - Developer', 'Python')[1])

    def test_location_name_not_geography(self):
        self.assertFalse(location_evidence('Austin', 'Austin Smith - Engineer', 'Location: Dallas'))
        self.assertFalse(location_evidence('Austin', 'Austin Smith - Engineer', 'Python developer'))

    def test_arbitrary_locations_without_city_list(self):
        for city in ('Austin', 'Multan', 'Tbilisi', 'São Paulo', 'Kigali', '東京'):
            self.assertTrue(location_evidence(city, '', 'Location: ' + city))

    def test_historical_and_conflicting_locations(self):
        for text in ('Previously based in Austin; now in Dallas', 'Not based in Austin',
                     'Location: Dallas; based in Austin', 'Location: Austinville',
                     'Location: Dallas; Skills: Austin'):
            self.assertFalse(location_evidence('Austin', '', text), text)

    def test_full_location_requires_all_parts(self):
        self.assertFalse(location_evidence('Austin, TX, United States', '', 'Location: Austin, TX'))
        self.assertTrue(location_evidence('Austin, TX, United States', '', 'Location: Austin, TX, United States'))

    def test_area_location(self):
        self.assertTrue(location_evidence('Austin', '', 'Greater Austin Area'))

    def test_negated_terms(self):
        for snippet in ('No Java experience', 'Without Java skills', 'Previously used Java'):
            self.assertTrue(evaluate(Filters(skills='Java'), 'Jane Doe - Engineer', snippet)[1])

    def test_experience_minimum_and_range(self):
        self.assertEqual(experience_range('5'), (5, math.inf))
        self.assertEqual(experience_range('3-7'), (3, 7))
        for text in ('5 years of experience', '15 years experience', '7+ years of experience'):
            self.assertTrue(experience_evidence('5+', text))
        for text in ('15 years experience', '7+ years experience', 'under 5 years experience',
                     '5 years at Acme', 'No 5 years experience', '3 years experience'):
            self.assertFalse(experience_evidence('5-7', text), text)
        self.assertTrue(experience_evidence('5-7', '6 years of professional experience'))
        self.assertTrue(experience_evidence('3-7', '3-7 years of experience'))
        self.assertFalse(experience_evidence('5+', '2-7 years of experience'))

    def test_validation(self):
        for value in ('five', '7-3', '90', '-1', 'nan'):
            with self.assertRaises(ValidationError):
                experience_range(value)
        for value in (0, 501, True, 20.5):
            with self.assertRaises(ValidationError):
                validate(Filters(designation='Engineer'), value)
        with self.assertRaises(ValidationError):
            validate(Filters(), 100)
        with self.assertRaises(ValidationError):
            validate(Filters(skills=','.join(f's{i}' for i in range(21))), 100)
        validate(Filters(location='Austin'), 500)

    def test_queries_include_every_term_and_preserve_core(self):
        f = Filters('Software Engineer', 'Austin', 'Technology', '5+', 'Python, Django, PostgreSQL', 'BS, MS')
        queries = build_queries(f)
        for q in queries:
            self.assertTrue('"Software Engineer"' in q or ('"Software"' in q and '"Engineer"' in q))
            self.assertIn('"Austin"', q)
        for term in ('Technology', 'Python', 'Django', 'PostgreSQL', 'BS', 'MS'):
            self.assertIn('"' + term + '"', queries[0])
        self.assertEqual(len(queries), len(set(queries)))
        self.assertIn('"Austin"', build_queries(Filters(location='Austin'))[0])

    def test_url_validation_and_canonicalization(self):
        self.assertEqual(normalize_profile_url('https://pk.linkedin.com/in/jane-doe/?trk=abc#test'),
                         'https://www.linkedin.com/in/jane-doe')
        for url in ('https://badlinkedin.com/in/name', 'https://linkedin.com.evil.com/in/name',
                    'https://linkedin.com/company/name', 'javascript://linkedin.com/in/name',
                    'https://user@linkedin.com/in/name', 'https://linkedin.com/in/name/posts/',
                    'https://linkedin.com/in/name%2Fother', 'https://linkedin.com:999/in/name'):
            self.assertIsNone(normalize_profile_url(url), url)


class CollectionTests(unittest.TestCase):
    def test_pagination_reaches_500_unique_not_40(self):
        provider = FakeProvider(lambda q, p, n: [record(i) for i in range((p-1)*100, p*100)])
        report = search(Filters('Software Engineer', 'Austin'), 500, provider=provider, limits=FAST)
        self.assertEqual(len(report.rows), 500)
        self.assertEqual([c[1] for c in provider.calls], [1, 2, 3, 4, 5])
        self.assertEqual(report.stop_reason, 'target_reached')
        self.assertEqual(len({r['LinkedIn URL'] for r in report.rows}), 500)

    def test_exact_limit_and_partial_batch(self):
        provider = FakeProvider(lambda q, p, n: [record(i) for i in range(100)])
        report = search(Filters(designation='Software Engineer'), 17, provider=provider, limits=FAST)
        self.assertEqual(len(report.rows), 17)

    def test_mandatory_filters_with_broad_retrieval(self):
        provider = FakeProvider(lambda q, p, n: [record(1, 'Location: Dallas; Python'),
                                                 record(2, 'Location: Austin; JavaScript'),
                                                 record(3, 'Location: Austin; Python')] if p == 1 else [])
        report = search(Filters('Software Engineer', 'Austin', skills='Python'), 500, provider=provider, limits=FAST)
        self.assertEqual(len(report.rows), 1)
        self.assertTrue(report.rows[0]['LinkedIn URL'].endswith('person-3'))

    def test_duplicate_changed_snippet_rechecked(self):
        provider = FakeProvider(lambda q, p, n: [record(1, 'Unknown')] if p == 1 else
                                [record(1)] if p == 2 else [])
        report = search(Filters(location='Austin'), 100, provider=provider, limits=FAST)
        self.assertEqual(len(report.rows), 1)

    def test_repeat_page_stops(self):
        provider = FakeProvider(lambda q, p, n: [record(1)])
        report = search(Filters(designation='Software Engineer'), 500, provider=provider, limits=FAST)
        self.assertEqual(len(report.rows), 1)
        self.assertLessEqual(len(provider.calls), 6)
        self.assertTrue(report.warnings)

    def test_empty_page_exhaustion(self):
        provider = FakeProvider(lambda q, p, n: [])
        report = search(Filters(location='Austin'), 500, provider=provider, limits=FAST)
        self.assertEqual(report.stop_reason, 'exhausted')
        self.assertEqual(report.successful_pages, 1)

    def test_timeout_retry_then_success(self):
        provider = FakeProvider(lambda q, p, n: ProviderError('timeout', True) if n == 1 else [record()])
        report = search(Filters(location='Austin'), 1, provider=provider, limits=FAST, sleep=lambda _: None)
        self.assertEqual(report.stop_reason, 'target_reached')
        self.assertEqual(report.failed_requests, 1)
        self.assertEqual(report.requests, 2)

    def test_rate_limit_stops_without_retry_and_retains_results(self):
        provider = FakeProvider(lambda q, p, n: [record()] if n == 1 else ProviderError('rate_limited'))
        report = search(Filters(location='Austin'), 500, provider=provider, limits=FAST)
        self.assertEqual(report.stop_reason, 'rate_limited')
        self.assertEqual(len(report.rows), 1)
        self.assertEqual(report.requests, 2)

    def test_circuit_breaker(self):
        provider = FakeProvider(lambda q, p, n: ProviderError('timeout', True))
        report = search(Filters('Engineer', 'Austin', skills='Python'), 500,
                        provider=provider, limits=FAST, sleep=lambda _: None)
        self.assertEqual(report.stop_reason, 'provider_failed')
        self.assertEqual(report.requests, 3)

    def test_unavailable_not_no_matches(self):
        provider = FakeProvider(lambda q, p, n: ProviderError('unavailable'))
        report = search(Filters(location='Austin'), 500, provider=provider, limits=FAST)
        self.assertEqual(report.stop_reason, 'provider_failed')
        self.assertEqual(report.successful_pages, 0)

    def test_request_budget(self):
        provider = FakeProvider(lambda q, p, n: [record(n)])
        report = search(Filters(location='Austin'), 500, provider=provider,
                        limits=Limits(max_requests=2, pause=0))
        self.assertEqual(report.stop_reason, 'budget_reached')
        self.assertEqual(report.requests, 2)
        self.assertEqual(len(report.rows), 2)

    def test_time_budget(self):
        clock_values = iter([0, 100, 101])
        provider = FakeProvider(lambda q, p, n: [])
        report = search(Filters(location='Austin'), 500, provider=provider,
                        limits=Limits(max_seconds=1), clock=lambda: next(clock_values))
        self.assertEqual(report.stop_reason, 'budget_reached')
        self.assertEqual(report.requests, 0)

    def test_invalid_rows_do_not_crash(self):
        provider = FakeProvider(lambda q, p, n: [None, {'href': []}, {'href': 'https://evil.com'}, record()] if p == 1 else [])
        report = search(Filters(location='Austin'), 500, provider=provider, limits=FAST)
        self.assertEqual(len(report.rows), 1)
        self.assertTrue(report.rejected)

    def test_no_review_status(self):
        report = search(Filters(location='Austin'), 1, provider=FakeProvider(lambda *a: [record()]), limits=FAST)
        self.assertNotIn('Review status', report.rows[0])


if __name__ == '__main__':
    unittest.main()
