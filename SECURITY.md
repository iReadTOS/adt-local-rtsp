# Security and privacy

This project explains how to inspect **your own authorized ADT Control / Alarm.com session** and connect to cameras **you own or are authorized to administer**. It is not an authentication bypass.

## Do not share secrets

Captured API responses may contain camera usernames/passwords, session cookies, access tokens, personal data, and home network details. Do not post raw HAR/mitmproxy captures, downloaded response bodies, complete RTSP URLs, or screenshots showing credentials to GitHub issues or discussions.

- Save captured responses **outside the repository** (for example, `~/adt-private/login-response.bin`).
- Keep private files readable only by your user (`chmod 600 ...`).
- Never publish the mitmproxy CA private key (`~/.mitmproxy/mitmproxy-ca.pem`).
- Inspect `git status`, `git diff --cached`, and proposed commits before pushing. `.gitignore` is a helpful safeguard, **not a guarantee**.
- The test script passes a credentials-bearing RTSP URL to FFmpeg through process arguments; run it on a trusted machine and avoid sharing process listings.
- Keep TLS relays bound to loopback until you deliberately design and secure an always-on deployment. `verify=0` disables verification only for the specified local camera connection.
- Remove the temporary iPhone proxy/certificate and restore Lockdown Mode after capturing.

## Reporting a security issue

Do **not** post real credentials or raw account data in a public issue. If you discover an issue with this repository's examples or helper code, first describe the impact **without reproduction secrets**, and use GitHub's private vulnerability reporting feature if enabled on this repository.

This project does not claim that cameras remain accessible after an ADT cancellation, a reboot, credential rotation, or an internet outage; these are untested.
