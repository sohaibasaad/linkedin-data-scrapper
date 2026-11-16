from unittest.mock import MagicMock, patch
import pytest
from search_engine import DDGSProvider, ProviderError, provider_failure


@pytest.mark.parametrize('message, expected', [
    ('429 Too many requests', ('rate_limited', False)),
    ('CAPTCHA required', ('rate_limited', False)),
    ('request timed out', ('timeout', True)),
    ('No results found.', ('empty', False)),
    ('No results found: backend timeout', ('timeout', True)),
    ('Some internal error', ('unavailable', False)),
])
def test_provider_error_mapping(message, expected):
    assert provider_failure(RuntimeError(message)) == expected


def test_hard_timeout_terminates_worker():
    context = MagicMock()
    receiver, sender, process = MagicMock(), MagicMock(), MagicMock()
    context.Pipe.return_value = receiver, sender
    context.Process.return_value = process
    receiver.poll.return_value = False
    process.is_alive.side_effect = [True, False]
    with patch('search_engine.mp.get_context', return_value=context):
        with pytest.raises(ProviderError) as exc:
            DDGSProvider(timeout=2).fetch('query', 1, 100)
    assert exc.value.code == 'timeout'
    receiver.poll.assert_called_once_with(7)
    process.terminate.assert_called_once()
    process.close.assert_called_once()
    receiver.close.assert_called_once()


def test_worker_response_returned_and_connections_closed():
    context = MagicMock()
    receiver, sender, process = MagicMock(), MagicMock(), MagicMock()
    context.Pipe.return_value = receiver, sender
    context.Process.return_value = process
    receiver.poll.return_value = True
    receiver.recv.return_value = ('ok', [{'title': 'Example'}])
    process.is_alive.return_value = False
    with patch('search_engine.mp.get_context', return_value=context):
        rows = DDGSProvider().fetch('query', 2, 100)
    assert rows == [{'title': 'Example'}]
    process.close.assert_called_once()
    receiver.close.assert_called_once()
