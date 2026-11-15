"""The interactive wizard is tested ONLY with synthetic camera credentials."""

import contextlib
import gzip
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

import adc_setup_wizard as w

FAKE_XML = b'''<?xml version="1.0"?>
<slnr><cli><gdr><cli model="OC845" lre="rtsp://fakeuser:secret%40pw@192.168.20.8:41926/img/media.sav?stream=TEST_TOKEN&amp;source=high" />
<cli model="RC845" lre="rtsp://192.168.20.26:41927/img/media.sav?stream=SECOND_TOKEN" l="seconduser" p="secondpass" /></gdr></cli></slnr>'''


class WizardTests(unittest.TestCase):
    def load(self, td, compressed=False):
        path = Path(td) / "sample.bin"
        path.write_bytes(gzip.compress(FAKE_XML) if compressed else FAKE_XML)
        return w.load_cameras(path)

    def test_gzip_plain_and_separate_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            for compressed in (False, True):
                cams = self.load(td, compressed=compressed)
                self.assertEqual([c["model"] for c in cams], ["OC845", "RC845"])
                self.assertEqual(cams[0]["password"], "secret@pw")
                self.assertEqual(cams[1]["username"], "seconduser")
                self.assertEqual(cams[1]["password"], "secondpass")

    def test_direct_scrypted_format_no_credentials_in_url(self):
        with tempfile.TemporaryDirectory() as td:
            cam = self.load(td)[0]
        direct = w.format_url(cam, 554, with_credentials=False)
        parsed = urlsplit(direct)
        self.assertEqual(parsed.hostname, "192.168.20.8")
        self.assertEqual(parsed.port, 554)
        self.assertEqual(parsed.query, "stream=TEST_TOKEN&source=high")
        self.assertNotIn("fakeuser", direct)
        self.assertNotIn("secret", direct)
        result = w.render([(1, cam)], "scrypted", 554)
        self.assertIn("Username: fakeuser", result)
        self.assertIn("Password: secret@pw", result)
        self.assertIn("RTSP Stream URL: "+direct, result)

    def test_nvr_includes_encoded_auth_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            cam = self.load(td)[0]
        url = w.format_url(cam, 554, with_credentials=True)
        p = urlsplit(url)
        self.assertEqual(p.port, 554)
        self.assertEqual(p.username, "fakeuser")
        self.assertEqual(p.password, "secret%40pw")
        self.assertEqual(p.query, "stream=TEST_TOKEN&source=high")
        self.assertIn("secret%40pw", w.render([(1, cam)], "nvr", 554))

    def test_safe_mode_has_no_password_or_stream_token(self):
        with tempfile.TemporaryDirectory() as td:
            cams = self.load(td)
        safe = w.render(list(enumerate(cams, 1)), "safe", 554)
        for forbidden in ("secret@pw", "secondpass", "TEST_TOKEN", "SECOND_TOKEN", "rtsp://"):
            self.assertNotIn(forbidden, safe)

    def test_manual_ip_override_must_be_rfc1918(self):
        self.assertTrue(w.is_lan_ip("192.168.22.5"))
        self.assertTrue(w.is_lan_ip("10.1.2.3"))
        self.assertTrue(w.is_lan_ip("172.16.0.1"))
        self.assertFalse(w.is_lan_ip("8.8.8.8"))
        self.assertFalse(w.is_lan_ip("example.org"))
        with tempfile.TemporaryDirectory() as td:
            cam = self.load(td)[0]
        cam["host_override"] = "10.1.2.3"
        self.assertIn("@10.1.2.3:554", w.format_url(cam, 554, with_credentials=True))

    def test_private_file_0600_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "credentials.txt"
            w.write_private_file(path, "secret")
            self.assertEqual(path.read_text(), "secret")
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                w.write_private_file(path, "overwritten")
            self.assertEqual(path.read_text(), "secret")

    def test_refuses_to_save_inside_git_repository(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".git").mkdir()
            with self.assertRaises(ValueError):
                w.write_private_file(Path(td) / "output.txt", "secret")

    def test_interactive_cancel_never_leaks_secret(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.bin"
            path.write_bytes(FAKE_XML)
            answers = iter(["all", "", "", "2", "not now"])
            output = io.StringIO()
            with patch("builtins.input", side_effect=lambda _: next(answers)), contextlib.redirect_stdout(output):
                self.assertEqual(w.main(["--capture", str(path)]), 0)
            self.assertIn("Cancelled", output.getvalue())
            self.assertNotIn("secret@pw", output.getvalue())
            self.assertNotIn("TEST_TOKEN", output.getvalue())

    def test_interactive_scrypted_terminal_explicit_reveal(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.bin"
            path.write_bytes(FAKE_XML)
            # Camera by IP, no IP change, default 554, Scrypted, REVEAL,
            # no FFprobe, output to terminal.
            answers = iter(["192.168.20.8", "", "", "2", "REVEAL", "", "1"])
            output = io.StringIO()
            with patch("builtins.input", side_effect=lambda _: next(answers)), contextlib.redirect_stdout(output):
                self.assertEqual(w.main(["--capture", str(path)]), 0)
            self.assertIn("Password: secret@pw", output.getvalue())
            self.assertIn("192.168.20.8:554", output.getvalue())
            self.assertNotIn("secondpass", output.getvalue())

    def test_doctype_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "bad.xml"
            path.write_bytes(b'<!DOCTYPE foo><slnr/>')
            with self.assertRaises(ValueError):
                w.load_cameras(path)


if __name__ == "__main__":
    unittest.main()
