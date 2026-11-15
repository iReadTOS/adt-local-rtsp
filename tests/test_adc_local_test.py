"""Tests use invented camera metadata only; never actual capture files."""

import contextlib
import gzip
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adc_local_test  # noqa: E402


SAMPLE_XML = b'''<?xml version="1.0"?>
<slnr><cli><gdr><cl>
<cli model="SampleModel" UnitId="0000"
 lre="rtsp://sampleuser:examplepassword@192.0.2.5:41926/img/media.sav?stream=1&amp;quality=high"
 l="sampleuser" p="examplepassword" />
</cl></gdr></cli></slnr>'''


class TestCameraDiscovery(unittest.TestCase):
    def test_plain_xml_and_gzip(self):
        with tempfile.TemporaryDirectory() as td:
            for name, payload in (
                ("sample.xml", SAMPLE_XML),
                ("sample.bin", gzip.compress(SAMPLE_XML)),
            ):
                path = Path(td) / name
                path.write_bytes(payload)
                cameras = adc_local_test.load_cameras(path)
                self.assertEqual(len(cameras), 1)
                self.assertEqual(cameras[0]["model"], "SampleModel")
                self.assertTrue(cameras[0]["has_credentials"])

    def test_relay_preserves_credentials_path_and_query(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.xml"
            path.write_bytes(SAMPLE_XML)
            cam = adc_local_test.load_cameras(path)[0]
        original = urlsplit(cam["url"])
        relayed = urlsplit(adc_local_test.relay_url(cam["url"], 8554))
        self.assertEqual(relayed.hostname, "127.0.0.1")
        self.assertEqual(relayed.port, 8554)
        self.assertEqual(original.username, relayed.username)
        self.assertEqual(original.password, relayed.password)
        self.assertEqual(original.path, relayed.path)
        self.assertEqual(original.query, relayed.query)

    def test_list_never_prints_password_or_full_url(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.xml"
            path.write_bytes(SAMPLE_XML)
            output = io.StringIO()
            with patch.object(sys, "argv", ["adc_local_test.py", str(path), "list"]), \
                    contextlib.redirect_stdout(output):
                self.assertEqual(adc_local_test.main(), 0)
            text = output.getvalue()
            self.assertIn("SampleModel", text)
            self.assertNotIn("examplepassword", text)
            self.assertNotIn("sampleuser", text)
            self.assertNotIn("rtsp://", text)


if __name__ == "__main__":
    unittest.main()
