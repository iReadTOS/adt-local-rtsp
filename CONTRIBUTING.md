# Contributing

Reports from other camera models, firmware versions, mobile app versions, and operating systems are welcome.

When filing an issue or pull request, include:

- Camera model and whether it is ADT Control, ADT Command, or another Alarm.com-branded setup.
- Whether you observed `UberSeamlessLoginNew`, `UberLoginNew`, or another response action.
- Whether the camera URL appeared in `lre` as an XML **attribute**, whether **standard RTSP/TCP on port 554** worked, and whether the optional TLS relay plus `-rtsp_transport http` worked.
- Video and audio codec names, and any **sanitized** error messages.
- Steps to reproduce, with *all passwords, userinfo, tokens, account IDs, full stream URLs, and public IPs removed*.

Please do not submit raw response captures, login data, or real RTSP URLs even in private pull requests. Use invented/sample values in tests.

**Scrypted / HomeKit:** We verified an OC845 live picture in Scrypted on HAOS and viewable HomeKit Secure Video recordings triggered by OpenCV. The two other cameras were added; prolonged reliability, per-camera audio, and camera operation after cancellation remain unverified. Native PIR was independently verified on both OC845 cameras, **not** as an HKSV trigger. Label untested models/features and MQTT experiments as hypotheses; see [native motion evidence](docs/NATIVE_PIR_FINDINGS.md).

## Contributing a compatibility report

Use the template in [COMPATIBILITY.md](COMPATIBILITY.md). Only report observations you actually verified, and never upload raw login response files, logs, complete stream URLs, credential-bearing screenshots, or camera passwords.
