"""Optional live deployment check: python smoke_test.py (requires Internet).
Prints counts/status only, never candidate details. No mock records.
"""
import json
from search_engine import Filters, Limits, search


def main():
    report = search(Filters(designation='Software Engineer', location='Austin'), 10,
                    limits=Limits(max_requests=1, retries=0, timeout=10, max_seconds=20))
    print(json.dumps({'matches': len(report.rows), 'requests': report.requests,
                      'successful_pages': report.successful_pages,
                      'stop_reason': report.stop_reason, 'warnings': report.warnings,
                      'elapsed': report.elapsed}, indent=2))


if __name__ == '__main__':
    main()
