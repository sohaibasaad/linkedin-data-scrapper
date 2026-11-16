import unittest
from search_engine import Filters, build_queries, normalize_profile_url, match_terms

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
    def test_matching(self):
        matched, score = match_terms(Filters(skills='Python, SQL'), 'Python Engineer', 'SQL developer')
        self.assertIn('Python', matched)
        self.assertEqual(score, 100)

if __name__ == '__main__': unittest.main()
