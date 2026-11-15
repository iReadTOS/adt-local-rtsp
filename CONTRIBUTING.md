# Contributing

Reports from other camera models, firmware versions, mobile app versions, and operating systems are welcome.

When filing an issue or pull request, include:

- Camera model and whether it is ADT Control, ADT Command, or another Alarm.com-branded setup.
- Whether you observed `UberSeamlessLoginNew`, `UberLoginNew`, or another response action.
- Whether the camera URL appeared in `lre` as an XML **attribute**, and whether the relay plus `-rtsp_transport http` worked.
- Video and audio codec names, and any **sanitized** error messages.
- Steps to reproduce, with *all passwords, userinfo, tokens, account IDs, full stream URLs, and public IPs removed*.

Please do not submit raw response captures, login data, or real RTSP URLs even in private pull requests. Use invented/sample values in tests.

**Scrypted / HomeKit:** Please mark untested configurations as hypotheses. We intend to add a separate, validated Part 2 after testing on an always-on installation.
