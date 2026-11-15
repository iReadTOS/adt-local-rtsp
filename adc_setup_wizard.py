#!/usr/bin/env python3
"""Interactive local ADT/Alarm.com camera RTSP configuration wizard.

Reads an authenticated login response YOU captured from cameras you administer.
Standard-library only. Does not call ADT/Alarm.com or change camera settings.

Defaults to metadata-only, with no passwords or streaming query tokens shown.
Sensitive output requires typing REVEAL, and may be saved to a new 0600 file.
"""

import argparse
import gzip
import io
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import quote, unquote, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 8 * 1024 * 1024


def load_cameras(path: Path) -> list[dict]:
    """Load camera attributes from a gzip-encoded or plain XML response."""
    with path.expanduser().open("rb") as f:
        # Read at most the amount we are willing to parse, including gzip input.
        prefix = f.read(2)
        f.seek(0)
        if prefix == b"\x1f\x8b":
            with gzip.GzipFile(fileobj=f) as z:
                data = z.read(MAX_XML_BYTES + 1)
        else:
            data = f.read(MAX_XML_BYTES + 1)
    if len(data) > MAX_XML_BYTES:
        raise ValueError("Capture exceeds the supported XML size")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("DTD/entity declarations are not supported")

    root = ET.fromstring(data)
    cameras = []
    for el in root.iter():
        raw_url = el.attrib.get("lre")
        if not raw_url:
            continue
        try:
            parsed = urlsplit(raw_url)
            if parsed.scheme.lower() != "rtsp" or not parsed.hostname or parsed.port is None:
                continue
            username = unquote(parsed.username) if parsed.username is not None else el.attrib.get("l", "")
            password = unquote(parsed.password) if parsed.password is not None else el.attrib.get("p", "")
            if not username:
                username = el.attrib.get("l", "")
            if not password:
                password = el.attrib.get("p", "")
            cameras.append({
                "model": el.attrib.get("modelForDisplay") or el.attrib.get("model") or "Unknown",
                "host": parsed.hostname,
                "tls_port": parsed.port,
                "path": parsed.path,
                "query": parsed.query,
                "username": username,
                "password": password,
                "source_url": raw_url,
                "host_override": None,
            })
        except (ValueError, TypeError):
            # A non-RTSP or malformed lre should not prevent inspecting others.
            continue
    return cameras


def is_lan_ip(value: str) -> bool:
    """Override only to an RFC1918 IPv4 address, not an arbitrary remote host."""
    try:
        address = ipaddress.IPv4Address(value)
        return any(address in net for net in (
            ipaddress.IPv4Network("10.0.0.0/8"),
            ipaddress.IPv4Network("172.16.0.0/12"),
            ipaddress.IPv4Network("192.168.0.0/16"),
        ))
    except ipaddress.AddressValueError:
        return False


def format_url(cam: dict, port: int, *, with_credentials: bool) -> str:
    host = cam["host_override"] or cam["host"]
    authority = f"{host}:{port}"
    if with_credentials:
        if not cam["username"] or not cam["password"]:
            raise ValueError("No usable username/password in this camera record")
        userinfo = f"{quote(cam['username'], safe='')}:{quote(cam['password'], safe='')}"
        authority = f"{userinfo}@{authority}"
    return urlunsplit(("rtsp", authority, cam["path"], cam["query"], ""))


def render(cameras: list[dict], mode: str, port: int) -> str:
    lines = []
    if mode != "safe":
        lines.extend([
            "SENSITIVE CAMERA CONFIGURATION — NEVER SHARE, SCREENSHOT OR COMMIT",
            "Camera credentials and stream query parameters may grant access to live video.",
            "",
        ])
    for i, cam in cameras:
        lines.append(f"Camera {i} — {cam['model']} ({cam['host_override'] or cam['host']})")
        if mode == "safe":
            lines.append(f"  Capture TLS endpoint: {cam['host']}:{cam['tls_port']}")
            lines.append(f"  Credentials present: {bool(cam['username'] and cam['password'])}")
        elif mode == "scrypted":
            lines.append(f"  RTSP Stream URL: {format_url(cam, port, with_credentials=False)}")
            lines.append(f"  Username: {cam['username']}")
            lines.append(f"  Password: {cam['password']}")
        elif mode == "nvr":
            lines.append(f"  Authenticated RTSP URL: {format_url(cam, port, with_credentials=True)}")
            lines.append("  Transport: standard RTSP/TCP; may be plaintext on your LAN")
        elif mode == "tls":
            original = cam["source_url"]
            parsed_original = urlsplit(original)
            # Preserve the captured URL byte-for-byte when it already includes
            # credentials and the user has not overridden the camera IP.
            if cam["host_override"] or parsed_original.username is None or parsed_original.password is None:
                original = format_url(cam, cam["tls_port"], with_credentials=True)
            lines.append(f"  Original-port URL: {original}")
            lines.append("  CAUTION: This high port uses RTSP-over-HTTPS, not normal RTSP/TCP.")
            lines.append("  It is NOT directly usable in standard RTSP clients.")
        else:
            raise ValueError("Unsupported output mode")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_private_file(path: Path, content: str) -> None:
    """Create-only, no-follow, never inside a Git repository; mode 0600."""
    path = path.expanduser().absolute()
    resolved_parent = path.parent.resolve()
    for parent in [resolved_parent, *resolved_parent.parents]:
        if (parent / ".git").exists() or (parent / ".github").exists():
            raise ValueError("Refusing to store sensitive exports in a Git repository")
    # The standard project-private directory is created if needed.
    if path.parent == Path.home() / "adt-private":
        path.parent.mkdir(mode=0o700, exist_ok=True)
    if not path.parent.is_dir():
        raise ValueError("Destination directory does not exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def ask(prompt: str, default: str | None = None) -> str:
    label = f"{prompt} [{default}]: " if default is not None else f"{prompt}: "
    answer = input(label).strip()
    return answer if answer else (default or "")


def yes(prompt: str, default: bool = False) -> bool:
    answer = ask(prompt, "Y/n" if default else "y/N").lower()
    return answer in ("y", "yes")


def choose_capture(explicit_path: Path | None) -> Path:
    if explicit_path:
        return explicit_path.expanduser()
    candidates = []
    for dirname, patterns in (
        (Path.home() / "adt-private", ("*.bin", "*.xml")),
        (Path.home() / "Downloads", ("adt-response*.bin", "login-response*.bin", "*.xml")),
    ):
        if dirname.is_dir():
            for pattern in patterns:
                candidates.extend(f for f in dirname.glob(pattern) if f.is_file())
    candidates = sorted(set(candidates))[:15]
    print("\nSelect your captured ADT response (XML or gzip .bin).")
    for i, path in enumerate(candidates, 1):
        print(f"  {i}. {path}")
    if candidates:
        print("  0. Enter a different file path")
    while True:
        answer = ask("File number or full file path", "1" if candidates else "~/adt-private/login-response.bin")
        if candidates and answer.isdigit() and 1 <= int(answer) <= len(candidates):
            return candidates[int(answer) - 1]
        if not candidates or answer != "0":
            p = Path(answer).expanduser()
            if p.is_file():
                return p
        if answer == "0":
            new_path = Path(ask("Full capture file path")).expanduser()
            if new_path.is_file():
                return new_path
        print("That file was not found. Try again.")


def choose_cameras(cameras: list[dict]) -> list[tuple[int, dict]]:
    print("\nCameras discovered (no secrets shown):")
    for i, cam in enumerate(cameras, 1):
        print(f"  {i}. {cam['model']} — {cam['host']} (captured high port {cam['tls_port']})")
    print("Choose 'all', a camera number, comma-separated numbers, or an exact camera IP.")
    while True:
        choice = ask("Select camera(s)", "all").strip()
        if choice.lower() == "all":
            return list(enumerate(cameras, 1))
        if choice in (cam["host"] for cam in cameras):
            result = [(i, cam) for i, cam in enumerate(cameras, 1) if cam["host"] == choice]
            if len(result) == 1:
                return result
            print("That IP matches multiple camera records. Select by number instead.")
            continue
        try:
            indices = [int(p.strip()) for p in choice.split(",")]
            if indices and len(set(indices)) == len(indices) and all(1 <= n <= len(cameras) for n in indices):
                return [(i, cameras[i - 1]) for i in indices]
        except ValueError:
            pass
        print("Invalid selection. Example: 1,3 or all")


def choose_port() -> int:
    while True:
        value = ask("Standard RTSP port", "554")
        if value.isdigit() and 1 <= int(value) <= 65535:
            return int(value)
        print("Enter a TCP port from 1 to 65535.")


def choose_mode() -> str:
    print("\nOutput format:")
    print("  1. Safe summary (no passwords or stream query tokens)")
    print("  2. Scrypted / RTSP plugin (separate RTSP URL, username, password)")
    print("  3. Blue Iris / generic NVR (full authenticated direct RTSP URL)")
    print("  4. Original camera high-port URL (advanced HTTPS tunnel diagnostics)")
    while True:
        selection = ask("Choose output", "1")
        if selection in ("1", "2", "3", "4"):
            return {"1": "safe", "2": "scrypted", "3": "nvr", "4": "tls"}[selection]
        print("Please choose 1, 2, 3 or 4.")


def probe_one(cam: dict, port: int) -> str:
    """Read metadata only; never pass FFmpeg diagnostics through to the terminal."""
    if not shutil.which("ffprobe"):
        return "Skipped (ffprobe not installed)"
    try:
        url = format_url(cam, port, with_credentials=True)
        result = subprocess.run([
            "ffprobe", "-v", "error", "-rtsp_transport", "tcp",
            "-show_entries", "stream=codec_type,codec_name,width,height",
            "-of", "json", "-i", url,
        ], text=True, capture_output=True, timeout=20)
        if result.returncode:
            return "Could not authenticate/read RTSP; inspect locally (details suppressed)"
        streams = json.loads(result.stdout).get("streams", [])
        if not streams:
            return "Connected, but no tracks reported"
        summaries = [f"{s.get('codec_type', '?')}:{s.get('codec_name', '?')}" for s in streams]
        return "Success — " + ", ".join(summaries)
    except subprocess.TimeoutExpired:
        return "Timed out (20 seconds)"
    except (ValueError, OSError, json.JSONDecodeError):
        return "Could not complete probe (details suppressed)"


def run(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Interactive ADT/Alarm.com RTSP configuration wizard")
    parser.add_argument("--capture", type=Path, help="Optional capture file; otherwise choose interactively")
    args = parser.parse_args(argv)
    print("ADT / Alarm.com RTSP configuration wizard")
    print("For authorized cameras only. Nothing is uploaded or sent to a cloud API.")
    path = choose_capture(args.capture)
    try:
        cameras = load_cameras(path)
    except (OSError, ValueError, ET.ParseError, EOFError) as exc:
        print(f"Unable to read capture ({type(exc).__name__}). No secret details displayed.", file=sys.stderr)
        return 1
    if not cameras:
        print("No lre RTSP cameras found in this response.")
        return 1

    chosen = choose_cameras(cameras)
    if yes("Change a camera IP address from the capture?", False):
        for _, cam in chosen:
            while True:
                requested = ask(f"LAN IP for {cam['model']} (captured {cam['host']})", cam["host"])
                if requested == cam["host"]:
                    break
                if is_lan_ip(requested):
                    cam["host_override"] = requested
                    break
                print("Enter a private IPv4 address (10.x, 172.16–31.x, or 192.168.x).")

    port = choose_port()
    mode = choose_mode()
    if mode == "safe":
        print("\n" + render(chosen, mode, port))
        return 0

    if any(not c["username"] or not c["password"] for _, c in chosen):
        print("A selected camera is missing credentials; refusing sensitive export.")
        return 1

    print("\nSECURITY WARNING: Output contains reusable camera credentials and/or stream tokens.")
    print("Never share it in chats, screenshots, logs, tickets, or Git commits.")
    print("Direct port 554 is standard RTSP but typically unencrypted on the LAN.")
    if ask("Type REVEAL to continue (anything else cancels)") != "REVEAL":
        print("Cancelled without revealing any secrets.")
        return 0

    if mode != "tls" and yes("Test direct RTSP on this computer with FFprobe? (credentials visible in process list)", False):
        print("\nFFprobe results (media metadata only):")
        for i, cam in chosen:
            print(f"  Camera {i}: {probe_one(cam, port)}")

    contents = render(chosen, mode, port)
    print("\n1. Show in this terminal (visible in scrollback)")
    print("2. Save to NEW private text file (mode 0600; never overwrite)")
    while True:
        destination = ask("Choose destination", "2")
        if destination in ("1", "2"):
            break
        print("Select 1 or 2.")
    if destination == "1":
        print("\n" + contents)
        return 0

    target = Path(ask("New output filename", "~/adt-private/adt-camera-settings.txt")).expanduser()
    try:
        write_private_file(target, contents)
    except (OSError, ValueError) as exc:
        print(f"File not created ({type(exc).__name__}). Existing files were not overwritten.", file=sys.stderr)
        return 1
    print(f"Private file saved: {target} (0600 on POSIX). Keep it outside Git.")
    return 0


def main(argv=None) -> int:
    try:
        return run(argv)
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled. No credentials displayed by the wizard.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
