import unittest
from search_engine import Filters, build_queries, normalize_profile_url, match_terms, location_evidence, search

class SearchTests(unittest.TestCase):
    def test_queries(self):
        q = build_queries(Filters(title='Data Engineer', skills='Python, SQL', location='Karachi'))
        self.assertTrue(q)
        self.assertTrue(all('site:linkedin.com/in/' in x for x in q))
    def test_profile_urls(self):
        self.assertEqual(normalize_profile_url('https://pk.linkedin.com/in/example-person/?trk=abc'), 'https://www.linkedin.com/in/example-person')
        self.assertIsNone(normalize_profile_url('https://linkedin.com/company/example'))
        self.assertIsNone(normalize_profile_url('https://badlinkedin.com/in/example'))
        self.assertIsNone(normalize_profile_url('https://linkedin.com.evil.com/in/example'))
    def test_austin_false_positives(self):
        self.assertIsNone(location_evidence('Austin', 'Austin Smith - Software Engineer', 'Works in Dallas, TX'))
        self.assertIsNone(location_evidence('Austin', 'Michael Austin - Engineer', 'New York City'))
        self.assertIsNone(location_evidence('Austin', 'David Brown - Developer', 'Python and Django'))

    def test_austin_positive_geography(self):
        self.assertTrue(location_evidence('Austin', 'Sarah Johnson - Developer', 'Austin, TX'))
        self.assertTrue(location_evidence('Austin', 'James Lee', 'Location: Austin, Texas'))
        self.assertTrue(location_evidence('Austin', 'K Lee', 'Based in Austin'))
        self.assertTrue(location_evidence('Austin, TX', 'Jane Lee', 'Location: Austin, TX'))

    def test_location_in_all_queries(self):
        queries = build_queries(Filters(title='Developer', location='Austin', skills='Python, SQL', industry='Technology'))
        self.assertTrue(all('"Austin"' in q for q in queries))

    def test_matching(self):
        matched, score = match_terms(Filters(skills='Python, SQL'), 'Python Engineer', 'SQL developer')
        self.assertIn('Python', matched)
        self.assertEqual(score, 100)

if __name__ == '__main__': unittest.main()
