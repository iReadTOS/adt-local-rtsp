#!/usr/bin/env python3
"""Inspect and test RTSP URLs from your *own* Alarm.com/ADT mobile login response.

Read-only: this script never calls the Alarm.com API or changes camera settings.
It does not print embedded usernames, passwords, or full stream URLs.
A local ffprobe/ffplay process will briefly contain the authenticated URL in argv.
"""

import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET


def load_cameras(path: Path) -> list[dict]:
    data = path.read_bytes()
    if data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
    if len(data) > 3_000_000:
        raise ValueError("XML body is unusually large; refusing to process")

    root = ET.fromstring(data)
    cameras = []
    for element in root.iter():
        url = element.attrib.get("lre", "")
        if not url:
            continue
        parts = urlsplit(url)
        if parts.scheme.lower() != "rtsp" or not parts.hostname or not parts.port:
            continue
        cameras.append({
            "model": element.attrib.get("modelForDisplay") or element.attrib.get("model", "Unknown"),
            "host": parts.hostname,
            "port": parts.port,
            "url": url,
            "has_credentials": bool(parts.username and parts.password),
        })
    return cameras


def relay_url(authenticated_url: str, relay_port: int) -> str:
    parts = urlsplit(authenticated_url)
    if "@" not in parts.netloc:
        raise ValueError("No credentials in URL; expected a userinfo component")
    userinfo = parts.netloc.rsplit("@", 1)[0]
    return urlunsplit((
        "rtsp", f"{userinfo}@127.0.0.1:{relay_port}",
        parts.path, parts.query, parts.fragment,
    ))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("capture", type=Path, help="Saved response body (.bin), or decoded XML")
    p.add_argument("action", choices=("list", "probe", "play"))
    p.add_argument("--index", type=int, help="1-based index from 'list' output")
    p.add_argument("--relay-port", type=int, default=8554,
                   help="The LOCAL loopback port where socat is listening (default 8554)")
    args = p.parse_args()
    try:
        cameras = load_cameras(args.capture)
    except (OSError, ValueError, ET.ParseError, gzip.BadGzipFile) as exc:
        print(f"Cannot read capture: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not cameras:
        print("No lre RTSP camera attributes found in the response.")
        return 1

    if args.action == "list":
        print(f"Found {len(cameras)} local RTSP camera record(s):")
        for i, cam in enumerate(cameras, start=1):
            print(f"  {i}. {cam['model']} - {cam['host']}:{cam['port']} "
                  f"(credentials present: {cam['has_credentials']})")
        print("No credentials or full URLs are displayed.")
        return 0

    if not args.index or not 1 <= args.index <= len(cameras):
        p.error(f"--index must be between 1 and {len(cameras)} for {args.action}")
    if not 1 <= args.relay_port <= 65535:
        p.error("--relay-port must be a valid TCP port")

    cam = cameras[args.index - 1]
    url = relay_url(cam["url"], args.relay_port)
    print(f"Testing {cam['model']} ({cam['host']}:{cam['port']}) "
          f"through 127.0.0.1:{args.relay_port}")

    if args.action == "probe":
        cmd = [
            "ffprobe", "-v", "error", "-rtsp_transport", "http",
            "-show_entries", "stream=codec_type,codec_name,width,height",
            "-of", "json", "-i", url,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            print("TIMEOUT: no response within 30 seconds")
            return 2
        if result.returncode:
            print(f"FFprobe failed (exit code {result.returncode}).")
            error = result.stderr.lower()
            for term, label in (
                ("401", "Authentication rejected"),
                ("403", "Access forbidden"),
                ("404", "Stream endpoint not found"),
                ("connection refused", "Local relay not running or not accessible"),
                ("invalid data", "Unexpected stream response"),
                ("end of file", "Connection closed"),
                ("timed out", "Connection timeout"),
            ):
                if term in error:
                    print("Diagnostic:", label)
                    break
            else:
                print("Diagnostic: See socat log, or inspect FFmpeg errors locally.")
            return 2
        try:
            streams = json.loads(result.stdout).get("streams", [])
        except (ValueError, TypeError):
            print("FFprobe returned unexpected metadata")
            return 2
        print("SUCCESS. Discovered media streams:")
        for stream in streams:
            print(" ", stream)
        return 0

    print("Opening live view. Press Q in the FFplay window to close it.")
    try:
        result = subprocess.run([
            "ffplay", "-loglevel", "error", "-rtsp_transport", "http",
            "-window_title", f"Local ADT/ADC Camera {args.index}", "-i", url,
        ], capture_output=True, text=True)
    except KeyboardInterrupt:
        print("Playback interrupted")
        return 0
    if result.returncode and "decodeframe failed" in result.stderr.lower():
        print("FFplay H.264 decoder failed. Check your available FFmpeg decoders.")
    elif result.returncode:
        print(f"FFplay closed with exit code {result.returncode}.")
    else:
        print("Player closed")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
