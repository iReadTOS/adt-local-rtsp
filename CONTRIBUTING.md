# Contributing

Reports from other camera models, firmware versions, mobile app versions, and operating systems are welcome.

When filing an issue or pull request, include:

- Camera model and whether it is ADT Control, ADT Command, or another Alarm.com-branded setup.
- Whether you observed `UberSeamlessLoginNew`, `UberLoginNew`, or another response action.
- Whether the camera URL appeared in `lre` as an XML **attribute**, whether **standard RTSP/TCP on port 554** worked, and whether the optional TLS relay plus `-rtsp_transport http` worked.
- Video and audio codec names, and any **sanitized** error messages.
- Steps to reproduce, with *all passwords, userinfo, tokens, account IDs, full stream URLs, and public IPs removed*.

Please do not submit raw response captures, login data, or real RTSP URLs even in private pull requests. Use invented/sample values in tests.

**Scrypted / HomeKit:** We have verified a live OC845 picture in the Scrypted RTSP plugin under HAOS, and added the two other cameras. Please label untested models and features as hypotheses. HomeKit Secure Video, recording, motion events, and prolonged stability are not yet established.

## Contributing a compatibility report

Use the template in [COMPATIBILITY.md](COMPATIBILITY.md). Only report observations you actually verified, and never upload raw login response files, logs, complete stream URLs, credential-bearing screenshots, or camera passwords.
