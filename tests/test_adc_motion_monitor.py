"""Offline tests: no real camera credentials or camera connections."""
import hashlib
import socket
import struct
import threading
import unittest
from unittest.mock import patch

from adc_motion_monitor import (
    MotionHold, RTSPClient, RTSPFailure, SocketReader, choose_video_control,
    digest_authorization, pir_from_rtp, pir_from_sercomm_padding,
    resolve_control, stream_url,
)

SAMPLE_OFF = bytes.fromhex(
    "00 00 00 1f 01 0d 00 00 00 00 00 00 00 00 00 00 00 00 00"
    "02 02 00 00 03 01 00 c1 00 00 bf 00"
)
SAMPLE_RC845 = bytes.fromhex(
    "00 00 00 1c 01 0d 00 00 00 00 00 00 00 00 00 00 00 00 00"
    "02 02 00 00 c1 00 00 bf 00 00 00 00"
)
SAMPLE_ON = bytes.fromhex(
    "00 00 00 1f 01 0d 00 00 00 00 00 00 00 00 00 00 00 00 00"
    "02 02 00 00 03 01 01 c1 00 00 bf 00"
)
CAM = {
    "host": "192.168.56.80", "host_override": None,
    "path": "/img/media.sav", "query": "stream=example-token",
    "username": "example", "password": "TEST_PASSWORD",
}


def fake_rtp(metadata=SAMPLE_ON, csrc=False, extension=False):
    first = 0x80 | 0x20 | (0x10 if extension else 0) | (1 if csrc else 0)
    pkt = bytes([first, 96]) + bytes(10)
    if csrc:
        pkt += bytes(4)
    if extension:
        pkt += struct.pack("!HH", 0xBEDE, 1) + bytes(4)
    return pkt + b"fake-video" + metadata + bytes([len(metadata) + 1])


class SercommRTPTests(unittest.TestCase):
    def test_observed_captured_31_byte_samples(self):
        self.assertEqual(len(SAMPLE_OFF), 31)
        self.assertEqual(len(SAMPLE_ON), 31)
        self.assertEqual(pir_from_sercomm_padding(SAMPLE_OFF), 0)
        self.assertEqual(pir_from_sercomm_padding(SAMPLE_ON), 1)

    def test_rc845_metadata_declared_length_without_pir(self):
        self.assertEqual(len(SAMPLE_RC845), 31)
        self.assertIsNone(pir_from_sercomm_padding(SAMPLE_RC845))
        self.assertIsNone(pir_from_rtp(fake_rtp(SAMPLE_RC845)))
        # The shorter declared length is allowed only if filler is zero.
        tampered = SAMPLE_RC845[:-1] + b"\x55"
        self.assertIsNone(pir_from_sercomm_padding(tampered))
        # A correctly declared PIR block with additional zero filler decodes.
        self.assertEqual(pir_from_sercomm_padding(SAMPLE_ON + b"\x00" * 3), 1)

    def test_rtp_padding_valid_and_invalid(self):
        self.assertEqual(pir_from_rtp(fake_rtp(SAMPLE_ON)), 1)
        self.assertEqual(pir_from_rtp(fake_rtp(SAMPLE_OFF)), 0)
        self.assertEqual(pir_from_rtp(fake_rtp(SAMPLE_ON, csrc=True, extension=True)), 1)
        self.assertIsNone(pir_from_rtp(fake_rtp(SAMPLE_ON)[:-1] + b"\x00"))
        self.assertIsNone(pir_from_rtp(bytes([0x80]) + fake_rtp()[1:]))
        self.assertIsNone(pir_from_rtp(b"invalid"))

    def test_malformed_sercomm_length_and_commands(self):
        self.assertIsNone(pir_from_sercomm_padding(b"\0\0\0\x20" + SAMPLE_ON[4:]))
        self.assertIsNone(pir_from_sercomm_padding(bytes.fromhex("00000006 03 05")))
        self.assertIsNone(pir_from_sercomm_padding(b""))

    def test_pulse_hold_does_not_flicker(self):
        state = MotionHold(5)
        self.assertEqual(state.update(0, 0), [])
        self.assertEqual(state.update(1, 1), ["ON"])
        self.assertEqual(state.update(0, 2), [])
        self.assertEqual(state.update(1, 4), [])
        self.assertEqual(state.update(0, 8), [])
        self.assertEqual(state.update(0, 9), ["OFF"])
        self.assertEqual(state.update(0x11, 10), ["ON"])

    def test_url_preserves_query_and_no_credentials(self):
        self.assertEqual(
            stream_url(CAM),
            "rtsp://192.168.56.80:554/img/media.sav?stream=example-token&padding=yes",
        )
        self.assertNotIn(CAM["password"], stream_url(CAM))
        twice = dict(CAM, query="stream=abc&padding=no&other=1")
        self.assertEqual(stream_url(twice).count("padding="), 1)
        bad = dict(CAM, host="8.8.8.8")
        with self.assertRaises(ValueError):
            stream_url(bad)

    def test_digest_header_without_password_leak(self):
        value = digest_authorization(
            'realm="Authorization", nonce="abc", qop="auth"',
            "DESCRIBE", stream_url(CAM), CAM["username"], CAM["password"],
        )
        self.assertIn("Digest ", value)
        self.assertIn('qop="auth"', value)
        self.assertNotIn('algorithm=', value)  # Not advertised in the challenge.
        self.assertNotIn(CAM["password"], value)
        self.assertIn("response=", value)


    def test_ffmpeg_compatible_digest_format_and_response(self):
        """Strictly compare with independently computed Digest MD5 (qop auth)."""
        from adc_motion_monitor import parse_auth_params
        from unittest.mock import patch
        challenge = 'realm="Camera", nonce="abc", qop="auth", opaque="opaque-x"'
        with patch('adc_motion_monitor.secrets.token_hex', return_value='1122334455667788'):
            header = digest_authorization(challenge, 'DESCRIBE', 'rtsp://192.168.56.80:554/img/media.sav?stream=sample',
                                          'example', 'TEST_PASSWORD')
        self.assertIn('qop="auth"', header)
        self.assertIn('cnonce="1122334455667788"', header)
        self.assertIn('opaque="opaque-x"', header)
        self.assertNotIn('algorithm=', header)
        ha1 = hashlib.md5(b'example:Camera:TEST_PASSWORD').hexdigest()
        ha2 = hashlib.md5(b'DESCRIBE:rtsp://192.168.56.80:554/img/media.sav?stream=sample').hexdigest()
        expected = hashlib.md5(f'{ha1}:abc:00000001:1122334455667788:auth:{ha2}'.encode()).hexdigest()
        self.assertIn(f'response="{expected}"', header)
        self.assertNotIn('TEST_PASSWORD', header)
        self.assertEqual(parse_auth_params(header).get('qop'), 'auth')

    def test_basic_auth_is_explicit_only(self):
        default = RTSPClient(CAM)
        explicit = RTSPClient(CAM, auth_mode='basic')
        self.assertEqual(default.auth_mode, 'auto')
        self.assertEqual(explicit.auth_mode, 'basic')
        with self.assertRaises(ValueError):
            RTSPClient(CAM, auth_mode='anonymous')
    def test_basic_only_challenge_is_not_used_automatically(self):
        from unittest.mock import Mock
        from adc_motion_monitor import RTSPFailure

        client = RTSPClient(CAM)
        client.reader = Mock()
        client.reader.message.return_value = (
            "response", 401, ({"www-authenticate": ['Basic realm="Camera"']}, b""))
        client._send = Mock()
        with self.assertRaisesRegex(RTSPFailure, "explicit --auth basic"):
            client.request("DESCRIBE", client.url)
        self.assertEqual(client._send.call_count, 1)
        self.assertIsNone(client.auth_scheme)

    def test_sdp_control_resolution(self):
        sdp = "v=0\r\nm=audio 0 RTP/AVP 0\r\na=control:trackID=1\r\n" \
              "m=video 0 RTP/AVP 96\r\na=control:trackID=0\r\n"
        self.assertEqual(choose_video_control(sdp), "trackID=0")
        url = resolve_control("rtsp://192.168.56.80:554/img/media.sav/", "trackID=0")
        self.assertEqual(url, "rtsp://192.168.56.80:554/img/media.sav/trackID=0")
        with self.assertRaises(ValueError):
            resolve_control("rtsp://192.168.56.80:554/img/media.sav", "rtsp://8.8.8.8:554/abc")

    def test_buffered_frame_and_rtsp_response(self):
        left, right = socket.socketpair()
        try:
            r = SocketReader(left)
            pkt = fake_rtp()
            data = b"$\x00" + len(pkt).to_bytes(2, "big") + pkt
            data += b"RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Length: 4\r\n\r\nTEST"
            right.sendall(data)
            self.assertEqual(r.message(), ("rtp", 0, pkt))
            self.assertEqual(r.message(), ("response", 200, ({"cseq": ["2"], "content-length": ["4"]}, b"TEST")))
        finally:
            left.close()
            right.close()

    def test_full_rtsp_digest_handshake_mock_camera(self):
        client_sock, server_sock = socket.socketpair()
        server_sock.settimeout(3)
        observations = []
        errors = []

        def server():
            file = server_sock.makefile("rb")
            try:
                for code in (401, 200, 200, 200, 200):
                    request = file.readline().decode()
                    headers = {}
                    while True:
                        line = file.readline().decode().strip()
                        if not line:
                            break
                        k, v = line.split(":", 1)
                        headers[k.lower()] = v.strip()
                    observations.append((request.split(" ")[0], headers))
                    cseq = headers["cseq"]
                    if code == 401:
                        server_sock.sendall(
                            ("RTSP/1.0 401 Unauthorized\r\n"
                             f"CSeq: {cseq}\r\n"
                             'WWW-Authenticate: Digest realm="Camera", nonce="abc", qop="auth"\r\n'
                             "Content-Length: 0\r\n\r\n").encode()
                        )
                    elif request.startswith("OPTIONS"):
                        server_sock.sendall(("RTSP/1.0 200 OK\r\n"
                            f"CSeq: {cseq}\r\nPublic: OPTIONS, DESCRIBE, SETUP, PLAY\r\n\r\n").encode())
                    elif request.startswith("DESCRIBE"):
                        sdp = b"v=0\r\nm=video 0 RTP/AVP 96\r\na=control:trackID=0\r\n"
                        server_sock.sendall(("RTSP/1.0 200 OK\r\n"
                            f"CSeq: {cseq}\r\nContent-Base: rtsp://192.168.56.80:554/img/media.sav/\r\n"
                            f"Content-Length: {len(sdp)}\r\n\r\n").encode() + sdp)
                    elif request.startswith("SETUP"):
                        server_sock.sendall(("RTSP/1.0 200 OK\r\n"
                            f"CSeq: {cseq}\r\nSession: abcd123\r\n"
                            "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n\r\n").encode())
                    elif request.startswith("PLAY"):
                        rtp = fake_rtp()
                        server_sock.sendall(("RTSP/1.0 200 OK\r\n"
                            f"CSeq: {cseq}\r\n\r\n").encode() +
                            b"$\x00" + len(rtp).to_bytes(2,"big") + rtp)
            except Exception as exc:
                errors.append(exc)
            finally:
                file.close()
                server_sock.close()

        worker = threading.Thread(target=server)
        worker.start()
        try:
            client = RTSPClient(CAM)
            client.sock = client_sock
            client.reader = SocketReader(client_sock)
            reader = client.start()
            kind, channel, payload = reader.message()
            self.assertEqual((kind, channel), ("rtp", 0))
            self.assertEqual(pir_from_rtp(payload), 1)
            self.assertEqual([x[0] for x in observations], ["OPTIONS", "OPTIONS", "DESCRIBE", "SETUP", "PLAY"])
            self.assertIn("authorization", observations[1][1])
            self.assertNotIn("authorization", observations[0][1])
            self.assertIn('qop="auth"', observations[1][1]["authorization"])
            self.assertNotIn("algorithm=", observations[1][1]["authorization"])
            for _, headers in observations:
                self.assertNotIn("TEST_PASSWORD", str(headers))
        finally:
            client_sock.close()
            worker.join(timeout=4)
        self.assertFalse(errors, errors)


if __name__ == "__main__":
    unittest.main()
