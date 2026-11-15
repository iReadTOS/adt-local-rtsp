#!/usr/bin/env python3
"""Experimental, read-only native PIR monitor for authorized Sercomm/ADT cameras.

Uses RTSP/TCP interleaved RTP with padding=yes and a captured ADT response.
No video decoding, root access, or tshark. Plain monitoring uses only the
standard library; opt-in MQTT publishing requires paho-mqtt>=2.1.
This is a standalone research utility, not a supported 24/7 security sensor.
"""

import argparse
import base64
import hashlib
import ipaddress
from pathlib import Path
import re
import secrets
import socket
import sys
import time
from urllib.parse import urlsplit, urlunsplit

from adc_setup_wizard import load_cameras

MAX_RTSP_BODY = 131072
MAX_HEADER_BYTES = 16384


def private_camera_host(host):
    """Allow only explicit RFC1918 IPv4 camera addresses."""
    try:
        ip = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        return False
    return any(ip in net for net in (
        ipaddress.IPv4Network("10.0.0.0/8"),
        ipaddress.IPv4Network("172.16.0.0/12"),
        ipaddress.IPv4Network("192.168.0.0/16"),
    ))


def stream_url(cam):
    """Create a credential-free RTSP URL, preserving captured query bytes."""
    host = cam["host_override"] or cam["host"]
    if not private_camera_host(host):
        raise ValueError("Camera address must be a private RFC1918 IPv4 address")
    original = cam["query"]
    params = [p for p in original.split("&") if p and p.split("=", 1)[0].lower() != "padding"]
    params.append("padding=yes")
    return urlunsplit(("rtsp", f"{host}:554", cam["path"], "&".join(params), ""))


def pir_from_sercomm_padding(data):
    """Decode command 0x03 (PIR) from RTP padding, sans trailing count byte.

    Validates the big-endian declared payload length and command sizes.
    Some RC845 packets declare 28 useful bytes plus three zero filler bytes
    within their 31-byte RTP padding metadata. Those have no 0x03 PIR tag.
    Returns a raw one-byte status or None if PIR is absent or malformed.
    """
    if len(data) < 6 or len(data) > 2048:
        return None
    declared = int.from_bytes(data[:4], "big")
    if not 6 <= declared <= len(data) or any(data[declared:]):
        return None
    data = data[:declared]
    offset = 4
    found = None
    while offset < len(data):
        command = data[offset]
        offset += 1
        width = 1 if command < 0xC0 else 2 if command < 0xE0 else 4
        if offset + width > len(data):
            return None
        length = int.from_bytes(data[offset:offset + width], "big")
        offset += width
        if offset + length > len(data):
            return None
        if command == 0x03 and length == 1:
            found = data[offset]
        offset += length
    return found


def pir_from_rtp(packet):
    """Extract a Sercomm status from RTP padding; ignore video/media payload."""
    if len(packet) < 13 or packet[0] >> 6 != 2 or not packet[0] & 0x20:
        return None
    headlen = 12 + 4 * (packet[0] & 0x0F)
    if len(packet) < headlen:
        return None
    if packet[0] & 0x10:  # RTP extension
        if len(packet) < headlen + 4:
            return None
        words = int.from_bytes(packet[headlen + 2:headlen + 4], "big")
        headlen += 4 + words * 4
    padsize = packet[-1]  # RTP padding count includes this final byte
    if padsize < 2 or headlen > len(packet) - padsize:
        return None
    return pir_from_sercomm_padding(packet[-padsize:-1])


def parse_auth_params(value):
    return {m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3)
            for m in re.finditer(r'([\w-]+)\s*=\s*(?:"([^"]*)"|([^,\s]+))', value)}


def digest_authorization(challenge, method, uri, username, password):
    """Build RFC2617-style Digest response (MD5 and auth qop only)."""
    options = parse_auth_params(challenge)
    realm, nonce = options.get("realm"), options.get("nonce")
    if realm is None or nonce is None:
        raise ValueError("Incomplete Digest challenge")
    algorithm = options.get("algorithm", "MD5").upper()
    if algorithm not in ("MD5", "MD5-SESS"):
        raise ValueError("Unsupported Digest algorithm")
    offered_qop = [p.strip() for p in options.get("qop", "").split(",") if p.strip()]
    if offered_qop and "auth" not in offered_qop:
        raise ValueError("Digest qop auth not available")
    h = lambda x: hashlib.md5(x.encode("utf-8")).hexdigest()
    cnonce = secrets.token_hex(8)
    ha1 = h(f"{username}:{realm}:{password}")
    if algorithm == "MD5-SESS":
        ha1 = h(f"{ha1}:{nonce}:{cnonce}")
    ha2 = h(f"{method}:{uri}")
    # Match FFmpeg's long-standing Digest header formatting. Some embedded
    # RTSP servers are stricter than RFC 2617: omit unadvertised algorithm
    # and quote qop, which FFmpeg does for broad camera compatibility.
    parts = [f'username="{username}"', f'realm="{realm}"', f'nonce="{nonce}"',
             f'uri="{uri}"']
    if "algorithm" in options:
        parts.append(f'algorithm="{options["algorithm"]}"')
    if offered_qop:
        response = h(f"{ha1}:{nonce}:00000001:{cnonce}:auth:{ha2}")
        parts += ['qop="auth"', "nc=00000001", f'cnonce="{cnonce}"']
    else:
        response = h(f"{ha1}:{nonce}:{ha2}")
        if algorithm == "MD5-SESS":
            parts.append(f'cnonce="{cnonce}"')
    parts.append(f'response="{response}"')
    if "opaque" in options:
        parts.append(f'opaque="{options["opaque"]}"')
    return "Digest " + ", ".join(parts)


def choose_video_control(sdp):
    """Return the video media a=control value, or * if aggregate only."""
    in_video = False
    for raw_line in sdp.splitlines():
        line = raw_line.strip()
        if line.startswith("m="):
            in_video = line.startswith("m=video ")
        elif in_video and line.startswith("a=control:"):
            return line.partition(":")[2].strip()
    return "*"


def resolve_control(base, control):
    if control == "*":
        return base
    origin = urlsplit(base)
    if control.startswith("rtsp://"):
        target = urlsplit(control)
        if target.hostname != origin.hostname or (target.port or 554) != (origin.port or 554):
            raise ValueError("SDP references an unexpected RTSP host")
        return control
    if control.startswith("/"):
        target = urlsplit(control)
        return urlunsplit((origin.scheme, origin.netloc, target.path, target.query, ""))
    # Most servers send a trailing slash in Content-Base when controls are relative.
    # Retain the stream query token even if Content-Base lacks that trailing slash.
    path = origin.path.rstrip("/") + "/" + control
    return urlunsplit((origin.scheme, origin.netloc, path, origin.query, ""))


class RTSPFailure(Exception):
    """Sanitized diagnostic: never include credential-bearing URLs."""


class SocketReader:
    def __init__(self, sock):
        self.sock = sock
        self.buffer = bytearray()

    def read(self, count):
        if count < 0 or count > 1024 * 1024:
            raise RTSPFailure("Excessive response length")
        while len(self.buffer) < count:
            fragment = self.sock.recv(max(4096, min(65536, count - len(self.buffer))))
            if not fragment:
                raise ConnectionError("Camera closed the connection")
            self.buffer.extend(fragment)
        value = bytes(self.buffer[:count])
        del self.buffer[:count]
        return value

    def line(self):
        while True:
            end = self.buffer.find(b"\r\n")
            if end >= 0:
                value = bytes(self.buffer[:end])
                del self.buffer[:end + 2]
                return value.decode("iso-8859-1", "replace")
            if len(self.buffer) >= MAX_HEADER_BYTES:
                raise RTSPFailure("RTSP header too large")
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Camera closed the connection")
            self.buffer.extend(chunk)

    def message(self):
        initial = self.read(1)
        if initial == b"$":
            framing = self.read(3)
            channel = framing[0]
            length = int.from_bytes(framing[1:3], "big")
            return "rtp", channel, self.read(length)
        # Ignore blank lines between RTSP messages.
        if initial in (b"\r", b"\n"):
            return "blank", None, None
        first_line = initial.decode("iso-8859-1") + self.line()
        if not first_line.startswith("RTSP/"):
            raise RTSPFailure("Unexpected data on RTSP control connection")
        parts = first_line.split(" ", 2)
        if len(parts) < 2 or not parts[1].isdigit():
            raise RTSPFailure("Malformed RTSP response")
        headers = {}
        while True:
            line = self.line()
            if not line:
                break
            if ":" in line:
                key, value = line.split(":", 1)
                headers.setdefault(key.strip().lower(), []).append(value.strip())
        try:
            length = int(headers.get("content-length", ["0"])[0])
        except ValueError as exc:
            raise RTSPFailure("Invalid RTSP Content-Length") from exc
        if not 0 <= length <= MAX_RTSP_BODY:
            raise RTSPFailure("Unexpected RTSP response body size")
        return "response", int(parts[1]), (headers, self.read(length))


class RTSPClient:
    def __init__(self, cam, auth_mode="auto"):
        if auth_mode not in ("auto", "basic"):
            raise ValueError("Unsupported RTSP authentication mode")
        self.auth_mode = auth_mode
        self.username = cam["username"]
        self.password = cam["password"]
        self.url = stream_url(cam)
        self.host = cam["host_override"] or cam["host"]
        self.sock = None
        self.reader = None
        self.cseq = 0
        self.challenge = None
        self.auth_scheme = None
        self.session = None
        self.channel = 0

    def __enter__(self):
        self.sock = socket.create_connection((self.host, 554), timeout=6)
        self.sock.settimeout(8)
        self.reader = SocketReader(self.sock)
        return self

    def __exit__(self, *_):
        if self.sock is not None:
            try:
                if self.session:
                    self._send("TEARDOWN", self.url, {"Session": self.session})
            except (OSError, ValueError, RTSPFailure):
                pass
            self.sock.close()

    def _send(self, method, url, headers=None):
        self.cseq += 1
        fields = {"CSeq": str(self.cseq), "User-Agent": "ADT-PIR-Research/0.1"}
        fields.update(headers or {})
        if self.auth_scheme == "digest":
            fields["Authorization"] = digest_authorization(
                self.challenge, method, url, self.username, self.password)
        elif self.auth_scheme == "basic":
            token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            fields["Authorization"] = f"Basic {token}"
        request = f"{method} {url} RTSP/1.0\r\n" + "".join(
            f"{k}: {v}\r\n" for k, v in fields.items()) + "\r\n"
        self.sock.sendall(request.encode("utf-8"))

    def request(self, method, url, headers=None):
        self._send(method, url, headers)
        for attempt in range(2):
            while True:
                kind, code, result = self.reader.message()
                if kind == "response":
                    break
                # Ignore any media frames while waiting for control reply.
            resp_headers, body = result
            if code != 401 or attempt == 1:
                break
            challenges = resp_headers.get("www-authenticate", [])
            digest = next((x.partition(" ")[2] for x in challenges
                           if x.lower().startswith("digest ")), None)
            basic = any(x.lower().startswith("basic ") for x in challenges)
            if self.auth_mode == "basic":
                if not basic:
                    raise RTSPFailure("Camera did not advertise Basic RTSP authentication")
                self.auth_scheme = "basic"
            elif digest:
                self.auth_scheme, self.challenge = "digest", digest
            elif basic:
                raise RTSPFailure("Camera offers Basic RTSP authentication only; explicit --auth basic required")
            else:
                raise RTSPFailure("Camera requires unsupported RTSP authentication")
            self._send(method, url, headers)
        if code != 200:
            raise RTSPFailure(f"RTSP {method} returned status {code}")
        return resp_headers, body

    def start(self):
        # Match FFmpeg's RTSP handshake: OPTIONS first, then DESCRIBE.
        # This also lets some embedded servers establish the Digest challenge
        # on OPTIONS rather than the SDP request.
        self.request("OPTIONS", self.url)
        headers, body = self.request("DESCRIBE", self.url, {"Accept": "application/sdp"})
        sdp = body.decode("utf-8", "replace")
        control = choose_video_control(sdp)
        base = headers.get("content-base", [self.url])[0]
        parsed_base = urlsplit(base)
        if not parsed_base.hostname:
            base = self.url
        elif parsed_base.hostname != self.host or (parsed_base.port or 554) != 554:
            raise RTSPFailure("Camera SDP returned an unexpected control host")
        setup_url = resolve_control(base, control)
        setup_headers, _ = self.request(
            "SETUP", setup_url,
            {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"}
        )
        session = setup_headers.get("session", [""])[0].split(";", 1)[0]
        if not session:
            raise RTSPFailure("RTSP SETUP did not return a session")
        self.session = session
        transport = setup_headers.get("transport", [""])[0]
        m = re.search(r"interleaved=(\d+)(?:-(\d+))?", transport, re.I)
        if m:
            self.channel = int(m.group(1))
        self.request("PLAY", self.url, {"Session": session})
        return self.reader


class MotionHold:
    """Turn pulse reports into state transitions with a configurable hold time."""
    def __init__(self, hold):
        self.hold = hold
        self.active_until = None
        self.active = False

    def update(self, status, now):
        events = []
        if status in (0x01, 0x11):
            self.active_until = now + self.hold
            if not self.active:
                self.active = True
                events.append("ON")
        if self.active and now >= self.active_until:
            self.active = False
            self.active_until = None
            events.append("OFF")
        return events


def run(argv=None):
    parser = argparse.ArgumentParser(
        description="Experimental Sercomm PIR monitor: local RTSP, read-only, no video saved"
    )
    parser.add_argument("--capture", required=True, type=Path,
                        help="Your private ADT response (gzip/XML); never commit it")
    parser.add_argument("--camera", required=True, help="Camera LAN IPv4 as recorded in capture")
    parser.add_argument("--duration", type=int, default=60, help="Seconds to monitor (default 60)")
    parser.add_argument("--hold", type=float, default=5.0, help="Motion hold seconds (default 5)")
    parser.add_argument("--retries", type=int, default=1, help="Reconnect attempts if disconnected (default 1)")
    parser.add_argument("--auth", choices=("auto", "basic"), default="auto",
                        help="auto prefers Digest; basic only if explicitly selected (unencrypted credential transport)")
    parser.add_argument("--mqtt-config", type=Path,
                        help="Opt-in MQTT publishing using a private 0600 TOML file outside this repository")
    parser.add_argument("--name", help="Stable name for MQTT discovery, e.g. driveway or lake")
    args = parser.parse_args(argv)
    if not 1 <= args.duration <= 86400 or not 0.1 <= args.hold <= 300 or not 0 <= args.retries <= 10:
        parser.error("Check duration (1-86400), hold (0.1-300) and retries (0-10)")
    if args.mqtt_config and not args.name:
        parser.error("--name is required with --mqtt-config")
    if args.name and not args.mqtt_config:
        parser.error("--name requires --mqtt-config")
    try:
        cam = next((x for x in load_cameras(args.capture) if x["host"] == args.camera), None)
    except (OSError, ValueError):
        print("Cannot read capture (OSError or invalid data)", file=sys.stderr)
        return 1
    if not cam or not cam.get("username") or not cam.get("password"):
        print("Selected camera not found or has no credentials", file=sys.stderr)
        return 1
    if not private_camera_host(args.camera):
        print("Camera address is not an RFC1918 LAN IPv4", file=sys.stderr)
        return 1

    publisher = None
    if args.mqtt_config:
        from adc_mqtt import MQTTFailure, PIRPublisher
        try:
            publisher = PIRPublisher(args.mqtt_config, args.name, cam.get("model", "Sercomm camera"))
            publisher.start()
        except (MQTTFailure, OSError, ValueError, ImportError) as exc:
            if publisher is not None:
                try:
                    publisher.close()
                except (MQTTFailure, OSError):
                    pass
            detail = str(exc) if isinstance(exc, MQTTFailure) else type(exc).__name__
            print(f"MQTT setup failed: {detail}", file=sys.stderr)
            return 3

    if args.auth == "basic":
        print("WARNING: Basic RTSP authentication exposes reusable credentials to LAN observers.", flush=True)
    print(f"Monitoring {args.camera} for {args.duration}s (PIR hold {args.hold:g}s)", flush=True)
    print("Research only. No footage saved. Existing Scrypted/HKSV sessions are unchanged.", flush=True)
    if publisher:
        print(f"MQTT enabled: adt_local_rtsp/pir/{args.name} (Home Assistant discovery published)", flush=True)
        print("MQTT is plaintext on the local network. Do not expose the broker to the internet.", flush=True)
    deadline = time.monotonic() + args.duration
    hold = MotionHold(args.hold)
    counts = {"samples": 0, "pulses": 0, "events": 0}
    retry = 0
    last_status = None
    last_pir_sample = None
    last_missing_report = False
    outcome = 0
    try:
        while time.monotonic() < deadline:
            try:
                with RTSPClient(cam, auth_mode=args.auth) as client:
                    reader = client.start()
                    print("RTSP connected; waiting for PIR samples...", flush=True)
                    retry = 0
                    last_pir_sample = None
                    last_status = None
                    last_missing_report = False
                    while time.monotonic() < deadline:
                        kind, channel, packet = reader.message()
                        if kind != "rtp" or channel != client.channel:
                            continue
                        status = pir_from_rtp(packet)
                        now = time.monotonic()
                        if status is None:
                            if (publisher and last_pir_sample is not None
                                    and now - last_pir_sample >= 20 and not last_missing_report):
                                print("PIR metadata stopped; marking MQTT sensor unavailable.", flush=True)
                                publisher.unavailable()
                                hold.active, hold.active_until = False, None
                                last_status, last_missing_report = None, True
                            continue
                        last_pir_sample = now
                        last_missing_report = False
                        counts["samples"] += 1
                        if status != last_status:
                            print(f"{time.strftime('%H:%M:%S')}  PIR raw state: 0x{status:02x}", flush=True)
                            last_status = status
                        if status in (1, 0x11):
                            counts["pulses"] += 1
                        for event in hold.update(status, now):
                            if event == "ON":
                                counts["events"] += 1
                            print(f"{time.strftime('%H:%M:%S')}  MOTION {event}", flush=True)
                        if publisher:
                            publisher.sample(hold.active)
            except (OSError, ValueError, RTSPFailure, ConnectionError) as exc:
                retry += 1
                detail = str(exc) if isinstance(exc, RTSPFailure) else type(exc).__name__
                if retry > args.retries:
                    print(f"RTSP interruption ({detail}); no retries remaining.", flush=True)
                    print("Stopping after failed connection attempts.", file=sys.stderr)
                    outcome = 2
                    break
                print(f"RTSP interruption ({detail}); retry {retry}/{args.retries}", flush=True)
                time.sleep(min(2, max(0, deadline - time.monotonic())))
            # RTSP ended; never keep an active or falsely available sensor.
            if hold.active:
                print(f"{time.strftime('%H:%M:%S')}  MOTION OFF (stream ended)", flush=True)
                hold.active, hold.active_until = False, None
            if publisher:
                publisher.unavailable()
        print(f"Done. PIR samples: {counts['samples']}; trigger pulses: {counts['pulses']};"
              f" motion events: {counts['events']}")
    except MQTTFailure as exc:
        print(f"MQTT publish failed: {exc}", file=sys.stderr)
        outcome = 3
    finally:
        if publisher:
            try:
                publisher.close()
            except MQTTFailure:
                print("MQTT shutdown did not confirm offline state; check broker availability.", file=sys.stderr)
    return outcome


if __name__ == "__main__":
    try:
        sys.exit(run())
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(130)
