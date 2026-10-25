"""The copied application must never reopen an unrelated local installation."""
import io
import json
from pathlib import Path
import unittest
from unittest import mock
from urllib.error import URLError

import fx_launch
import fx_server


class LauncherTests(unittest.TestCase):
    def test_same_copy_is_reused_without_a_new_server(self):
        status = {'app': 'Dataky FX Studio', 'library': str(Path(fx_launch.__file__).resolve().parent.parent)}
        with mock.patch.object(fx_launch.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(status).encode())), \
             mock.patch.object(fx_launch.webbrowser, 'open') as browser, mock.patch.object(fx_server, 'main') as server:
            self.assertEqual(fx_launch.main([]), 0)
            browser.assert_called_once_with('http://127.0.0.1:48754/')
            server.assert_not_called()

    def test_another_installation_is_left_running_and_next_port_is_used(self):
        foreign = io.BytesIO(json.dumps({'app':'Dataky FX Studio','library':str(Path.cwd() / 'other')}).encode())
        first_probe, second_probe = mock.MagicMock(), mock.MagicMock()
        first_probe.bind.side_effect = OSError('occupied')
        with mock.patch.object(fx_launch.urllib.request, 'urlopen', side_effect=[foreign, URLError('closed')]), \
             mock.patch.object(fx_launch.socket, 'socket', side_effect=[first_probe, second_probe]), \
             mock.patch.object(fx_server, 'main', return_value=0) as server, mock.patch.object(fx_launch.webbrowser, 'open') as browser:
            first_probe.__enter__.return_value = first_probe
            second_probe.__enter__.return_value = second_probe
            self.assertEqual(fx_launch.main(['--no-browser']), 0)
            server.assert_called_once_with(['--port','48755','--no-browser'])
            browser.assert_not_called()

    def test_free_explicit_port_is_forwarded(self):
        with mock.patch.object(fx_launch.urllib.request, 'urlopen', side_effect=URLError('closed')), \
             mock.patch.object(fx_launch.socket, 'socket') as socket, mock.patch.object(fx_server, 'main', return_value=0) as server:
            self.assertEqual(fx_launch.main(['--port','49000','--no-browser']), 0)
            server.assert_called_once_with(['--port','49000','--no-browser'])


if __name__ == '__main__':
    unittest.main()
