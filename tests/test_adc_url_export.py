"""Exporter tests use imaginary camera identities and credentials only."""
import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest

from adc_url_export import main, render

TEST_URL = "rtsp://fakeuser:fakepassword@192.0.2.8:41926/img/media.sav?stream=exampletoken"
TEST_XML = (f'<slnr><cli lre="{TEST_URL}" model="TestCamera" /></slnr>').encode()

class ExporterTests(unittest.TestCase):
    def test_render_preserves_url_and_query_and_relay_port(self):
        cam = {"model": "TestCamera", "host":"192.0.2.8", "port":41926, "url":TEST_URL}
        txt = render(cam, 1, 8558)
        self.assertIn(TEST_URL, txt)
        self.assertIn("rtsp://fakeuser:fakepassword@127.0.0.1:8558/img/media.sav?stream=exampletoken", txt)
        self.assertIn("rtsp://fakeuser:fakepassword@192.0.2.8:554/img/media.sav?stream=exampletoken", txt)
        self.assertIn("rtsp://192.0.2.8:554/img/media.sav?stream=exampletoken", txt)

    def test_private_file_is_0600_and_will_not_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            capture = Path(td) / 'capture.xml'
            out = Path(td) / 'private.txt'
            capture.write_bytes(TEST_XML)
            args = [str(capture), '--index', '1', '--save-to', str(out), '--i-understand-the-risk']
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args), 0)
                self.assertEqual(main(args), 2)
            self.assertIn('fakepassword', out.read_text())
            if os.name == 'posix':
                self.assertEqual(out.stat().st_mode & 0o777, 0o600)

    def test_stdout_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as td:
            capture = Path(td) / 'capture.xml'
            capture.write_bytes(TEST_XML)
            std = io.StringIO()
            with contextlib.redirect_stdout(std), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    main([str(capture), '--index', '1', '--show-secrets'])
            self.assertEqual(cm.exception.code, 2)
            self.assertNotIn('fakepassword', std.getvalue())

if __name__ == '__main__':
    unittest.main()
