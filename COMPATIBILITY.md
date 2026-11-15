# Camera and app compatibility

Only add results that were **actually tested**, and differentiate "metadata found," "FFprobe reads SDP," and **live playable video**. The camera credentials and mobile session data must never be included in reports.

## Verified on November 15, 2026

| Camera model | Location (example only) | ADT app / API | Local media result | Subscription-independent? |
| --- | --- | --- | --- | --- |
| OC845 A (outdoor) | ADT Control iOS · `UberSeamlessLoginNew` | **Pass:** H.264 1920×1080 + G.711 μ-law audio track detected, FFplay, direct RTSP/TCP 554, Scrypted live preview; native PIR pulses decoded | **Not tested** |
| RC845 (indoor) | ADT Control iOS · `UberSeamlessLoginNew` | **Pass:** FFplay video (TLS bridge), direct Python RTSP/TCP session; metadata received but PIR field absent | **Not tested** |
| OC845 B (outdoor) | ADT Control iOS · `UberSeamlessLoginNew` | **Pass:** FFplay video (TLS bridge), direct Python RTSP/TCP session; native PIR pulses decoded | **Not tested** |

The three entries above describe **one ADT system**. Firmware revisions, OS/app versions, credential lifetime, stream protocols and audio availability may differ elsewhere. No hardware was modified, unenrolled, or factory-reset during these tests.

**Additional functional validation:** After the original setup, Scrypted/OpenCV triggered viewable **HomeKit Secure Video** recordings in Apple Home, including at least one outdoor-camera event. This does not establish that every individual camera's HKSV or audio path was independently tested, nor that HKSV works offline or after ADT cancellation. The PIR monitor was tested on both OC845 units. For packet counts and limitations, see [native motion research](docs/NATIVE_PIR_FINDINGS.md). All three cameras reported firmware `V1.0.01R53` during our investigation.

## Compatibility report template

Copy this into a GitHub issue **without** including device identifiers, camera IPs, passwords, RTSP URLs, API bodies, cookies, or tokens.

```text
Camera model:
Firmware version (if safely known):
App platform / version (if known):
API action observed (e.g., UberLoginNew / UberSeamlessLoginNew):
Found lre attribute? (yes/no):
Direct standard RTSP/TCP on port 554 tested? (yes/no, outcome):
Scrypted / Blue Iris tested? (which, version, outcome):
Local TLS relay started? (yes/no):
FFprobe detected streams? (yes/no, codecs if known):
FFplay displayed live video? (yes/no):
Internet disconnected test? (yes/no, outcome):
Other notes (redacted):
```

## Untested questions

- Other OC/RC/ADC camera models and firmware versions.
- Local credential stability across reboots, logouts, and password changes.
- Operation with WAN disconnected or after canceling ADT service.
- Scrypted live preview and HKSV recordings were observed, but per-camera end-to-end audio, day/night detection reliability, and long-duration stability remain uncharacterized. Blue Iris and other NVRs are untested.
- Scrypted's native PIR → HKSV integration (not used; OpenCV remained active), MQTT with a live broker, and whether the RC845 exposes useful events through a different interface.
