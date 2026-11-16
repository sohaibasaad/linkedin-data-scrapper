from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from search_engine import SearchReport

APP = Path(__file__).resolve().parents[1] / 'app.py'


def test_ui_removed_controls_and_limit():
    app = AppTest.from_file(str(APP)).run(timeout=15)
    assert not app.exception
    assert len(app.text_input) == 6
    assert not any(x.label == 'Job title' for x in app.text_input)
    assert len(app.slider) == 1
    assert app.slider[0].max == 500
    assert not app.checkbox


def test_empty_form_validation():
    app = AppTest.from_file(str(APP)).run(timeout=15)
    app.button[0].click().run(timeout=15)
    assert not app.exception
    assert 'Enter at least one search filter' in app.error[0].value


def test_search_snapshot_exports_and_failure_clear():
    report = SearchReport(rows=[{'Name (from search title)': 'Jane',
                                 'LinkedIn URL': 'https://www.linkedin.com/in/jane',
                                 'Search snippet': 'Location: Austin'}], requested=500,
                          successful_pages=1, stop_reason='exhausted')
    app = AppTest.from_file(str(APP)).run(timeout=15)
    app.text_input[0].set_value('Software Engineer')
    app.text_input[1].set_value('Austin')
    app.slider[0].set_value(500)
    with patch('search_engine.search', return_value=report) as mock:
        app.button[0].click().run(timeout=15)
        assert mock.call_args.args[1] == 500
        assert mock.call_args.args[0].designation == 'Software Engineer'
    assert not app.exception
    assert len(app.dataframe) == 1
    assert 'Review status' not in app.dataframe[0].value.columns
    assert app.session_state['exports'][0]
    # Invalid resubmission cannot leave old rows/downloads visible.
    app.text_input[3].set_value('invalid experience')
    app.button[0].click().run(timeout=15)
    assert not app.exception
    assert len(app.dataframe) == 0
    assert 'Experience must be' in app.error[0].value
