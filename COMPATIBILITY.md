# Camera and app compatibility

Only add results that were **actually tested**, and differentiate "metadata found," "FFprobe reads SDP," and **live playable video**. The camera credentials and mobile session data must never be included in reports.

## Verified on November 15, 2026

| Camera model | Location (example only) | ADT app / API | Local media result | Subscription-independent? |
| --- | --- | --- | --- | --- |
| OC845 | Driveway | ADT Control iOS · `UberSeamlessLoginNew` | **Pass:** H.264 1920×1080 + G.711 μ-law audio; FFplay; **direct RTSP:554** metadata; **Scrypted v0.147.0 live preview** | **Not tested** |
| RC845 | Basement | ADT Control iOS · `UberSeamlessLoginNew` | **Pass:** Live video in FFplay (TLS bridge); added to Scrypted RTSP plugin | **Not tested** |
| OC845 | Lake | ADT Control iOS · `UberSeamlessLoginNew` | **Pass:** Live video in FFplay (TLS bridge); added to Scrypted RTSP plugin | **Not tested** |

The three entries above describe **one ADT system**. Firmware revisions, OS/app versions, credential lifetime, stream protocols and audio availability may differ elsewhere. No hardware was modified, unenrolled, or factory-reset during these tests.

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
- Scrypted was tested with the driveway camera (live preview); the other two were added but long-run stability, events, and audio in Scrypted are not yet characterized. Blue Iris and other NVRs are untested.
- Motion events, snapshots, HomeKit Secure Video, audio playback in the NVR, and long-duration stability.
