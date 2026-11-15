# Security and privacy

This project explains how to inspect **your own authorized ADT Control / Alarm.com session** and connect to cameras **you own or are authorized to administer**. It is not an authentication bypass.

## Do not share secrets

Captured API responses may contain camera usernames/passwords, session cookies, access tokens, personal data, and home network details. Do not post raw HAR/mitmproxy captures, downloaded response bodies, complete RTSP URLs, or screenshots showing credentials to GitHub issues or discussions.

- Save captured responses **outside the repository** (for example, `~/adt-private/login-response.bin`).
- The interactive wizard defaults to safe metadata-only output; secret-bearing formats require explicitly typing `REVEAL`. Prefer its new private file export (mode `0600`) rather than printing passwords to terminal history/scrollback.
- Keep private files readable only by your user (`chmod 600 ...`).
- Never publish the mitmproxy CA private key (`~/.mitmproxy/mitmproxy-ca.pem`).
- Inspect `git status`, `git diff --cached`, and proposed commits before pushing. `.gitignore` is a helpful safeguard, **not a guarantee**.
- The test script passes a credentials-bearing RTSP URL to FFmpeg through process arguments; run it on a trusted machine and avoid sharing process listings.
- Standard RTSP on port 554 is generally unencrypted; do not expose it to the internet or untrusted networks.
- Do not publish Scrypted logs without checking for RTSP URLs with embedded query tokens, even when the login and password were entered separately.
- Keep TLS relays bound to loopback until you deliberately design and secure an always-on deployment. `verify=0` disables verification only for the specified local camera connection.
- Remove the temporary iPhone proxy/certificate and restore Lockdown Mode after capturing.

## Reporting a security issue

Do **not** post real credentials or raw account data in a public issue. If you discover an issue with this repository's examples or helper code, first describe the impact **without reproduction secrets**, and use GitHub's private vulnerability reporting feature if enabled on this repository.

This project does not claim that cameras remain accessible after an ADT cancellation, a reboot, credential rotation, or an internet outage; these are untested.

## Experimental motion/MQTT and offline testing

The native PIR script reads the captured ADT response **locally in Python**, but RTSP port 554 is typically plaintext on the LAN. The publisher, if used, reads a separate mode-`0600` TOML credentials file **outside Git** and uses plaintext MQTT on the trusted LAN; do not port-forward 1883 or open a broker simply for this project. **The experimental MQTT integration is not required and has not been tested with a live broker here.** The RTSP client's default authentication prefers Digest and refuses Basic-only servers unless the operator explicitly requests `--auth basic`.

Never publish native packet captures: even when the extracted metadata is innocuous, a full network capture can include authenticated RTSP URLs, query tokens, credentials and camera footage. Public documentation deliberately uses generic camera labels and placeholder IPs.

For offline tests, block **only an authorized camera's WAN access** using reversible rules; do not disconnect the entire network or bypass alarms. Treat both cloud independence and operation after ADT cancellation as **unknown**. See [offline test plan](docs/OFFLINE_TEST_PLAN.md).
