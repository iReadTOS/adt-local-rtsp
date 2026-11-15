#!/usr/bin/env python3
"""Explicitly export authentication-bearing RTSP URLs from your own ADT capture.

This command is intentionally separate from adc_local_test.py, which never
prints credentials. Use only for cameras and accounts you administer.
"""

import argparse
import os
from pathlib import Path
import sys

from adc_local_test import load_cameras, relay_url
from urllib.parse import urlsplit, urlunsplit


def render(cam: dict, index: int, relay_port: int) -> str:
    """Produce a plain-text secret bundle. Call only with explicit user consent."""
    original_url = cam["url"]
    via_socat = relay_url(original_url, relay_port)
    parsed = urlsplit(original_url)
    userinfo = parsed.netloc.rsplit("@", 1)[0]
    direct_url = urlunsplit(("rtsp", f"{userinfo}@{cam['host']}:554", parsed.path, parsed.query, ""))
    scrypted_url = urlunsplit(("rtsp", f"{cam['host']}:554", parsed.path, parsed.query, ""))
    return (
        "SENSITIVE CAMERA ACCESS INFORMATION — DO NOT PUBLISH\n"
        f"Camera index: {index}\n"
        f"Model: {cam['model']}\n"
        f"Camera endpoint: {cam['host']}:{cam['port']}\n\n"
        "DIRECT RTSP/TCP PORT 554 URL (for generic NVRs; contains credentials):\n"
        f"{direct_url}\n\n"
        "SCRYPTED PORT 554 URL (enter credentials in separate fields):\n"
        f"{scrypted_url}\n\n"
        "ORIGINAL CAMERA URL (HTTPS tunnel high port; contains authentication):\n"
        f"{original_url}\n\n"
        "LOCAL SOCAT URL (also contains camera authentication):\n"
        f"{via_socat}\n\n"
        "IMPORTANT: Port 554 provides standard RTSP/TCP on verified OC845/RC845 cameras.\n"
        "Original high port: camera-specific RTSP-over-HTTPS tunnel.\n"
        "Local socat: requires a running socat TLS relay on 127.0.0.1 and a client\n"
        "configured for RTSP-over-HTTP (-rtsp_transport http in FFmpeg).\n"
        "Scrypted worked directly on port 554 in our HAOS test; Blue Iris remains unverified.\n"
        "Never share this file or paste either URL into a public issue or log.\n"
    )


def write_new_secret_file(path: Path, content: str) -> None:
    """Create, do not overwrite, a permissions-restricted secret file."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except BaseException:
        # Exception in fdopen or writing: do not leave partial plaintext secrets.
        try:
            path.unlink()
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="ADVANCED / SENSITIVE: show full credential-bearing camera URLs from an authorized capture."
    )
    parser.add_argument("capture", type=Path, help="Private saved login response (.bin or XML)")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--index", type=int, help="Camera index from adc_local_test.py list")
    selector.add_argument("--camera-ip", help="Select camera by its local IP address")
    dest = parser.add_mutually_exclusive_group(required=True)
    dest.add_argument("--show-secrets", action="store_true", help="PRINT secrets on terminal (may remain in scrollback)")
    dest.add_argument("--save-to", type=Path, metavar="PATH", help="Create a PRIVATE file (0600); refuses overwrite")
    parser.add_argument("--relay-port", type=int, default=8554, help="Local socat TCP port (default 8554)")
    parser.add_argument("--i-understand-the-risk", action="store_true", required=True,
                        help="Required explicit opt-in; URLs contain reusable credentials")
    args = parser.parse_args(argv)

    if not 1 <= args.relay_port <= 65535:
        parser.error("--relay-port must be 1–65535")
    try:
        cameras = load_cameras(args.capture)
    except Exception as exc:
        # Do not accidentally include arbitrary secret body content in an error.
        print(f"Could not read the private capture ({type(exc).__name__}).", file=sys.stderr)
        return 2
    if not cameras:
        print("No camera records found.", file=sys.stderr)
        return 2

    if args.index is not None:
        if not 1 <= args.index <= len(cameras):
            parser.error(f"--index must be between 1 and {len(cameras)}")
        index = args.index
    else:
        matches = [i for i, camera in enumerate(cameras, start=1)
                   if camera["host"] == args.camera_ip]
        if len(matches) != 1:
            parser.error("--camera-ip must match exactly one camera; use 'list' first")
        index = matches[0]
    cam = cameras[index - 1]
    if not cam["has_credentials"]:
        print("Selected camera has no embedded credentials; refusing export.", file=sys.stderr)
        return 2
    try:
        secret_text = render(cam, index, args.relay_port)
    except ValueError:
        print("Selected camera URL cannot be converted to the local bridge format.", file=sys.stderr)
        return 2

    if args.show_secrets:
        print("WARNING: The following text contains camera credentials. Keep it private.", file=sys.stderr)
        sys.stdout.write(secret_text)
        return 0

    # Prevent accidentally creating a plaintext credentials file in this source tree.
    try:
        args.save_to.resolve().relative_to(Path(__file__).resolve().parent)
    except ValueError:
        pass
    else:
        print("Refusing to save secrets inside this Git repository.", file=sys.stderr)
        return 2

    try:
        # Parent must exist; use a directory outside the git repo, e.g. ~/adt-private.
        write_new_secret_file(args.save_to, secret_text)
    except FileExistsError:
        print("Refusing to overwrite an existing file.", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Could not create private file ({type(exc).__name__}).", file=sys.stderr)
        return 2
    print("Private file created (mode 0600). Keep it OUTSIDE your Git repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
