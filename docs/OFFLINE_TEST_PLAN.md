# Can these ADT cameras work without internet or an active ADT subscription?

**Status (2026-11-15): Unknown.** Local authenticated RTSP playback **while the cameras remain enrolled and online** has been verified on two OC845 and one RC845, firmware `V1.0.01R53`. This does not establish independent provisioning, a permanent local account, or service-after-cancellation operation.

The tests below are a **reversible research plan**, not an assertion that the cameras are standalone products. Do **not** cancel service, reset/unpair a camera, change its firmware, or remove a camera from ADT to test this. Avoid disrupting any monitored alarm/security functionality. Perform experiments only on devices/network equipment you own or are authorized to manage.

## Separate three different questions

1. **Can a currently provisioned camera stream with its WAN access temporarily denied?** A successful answer proves only that the *already provisioned* RTSP session can run locally for the test interval.
2. **Can it start again without WAN?** A power cycle may expose cloud-dependent time, certificate, licensing, configuration, or authentication dependencies hidden by an already running session.
3. **Can it function after ADT service ends, or after credentials are invalidated?** A temporary outage does **not** simulate cancellation or cloud-side device unenrollment. This remains unknown until separately observed; losing access could be permanent or difficult to reverse.

## Before touching the network

- Save the existing **working** Scrypted RTSP settings (securely, outside Git) and confirm each camera's live picture still works using its camera-specific path, query, and credentials. Protect these as secrets.
- Confirm Apple Home records and plays back an HKSV test clip using Scrypted/OpenCV. HKSV uploads require the **HomePod/iCloud side** to remain online; only restrict the *camera's* WAN connectivity during this test.
- Pick **one noncritical camera** and an appropriate maintenance window. Note its model, firmware, whether its power and RTSP connection have been stable, and whether ADT currently reports it healthy.
- If you cannot narrowly restrict outbound traffic from **one camera** while preserving its LAN access to Scrypted and your testing machine, **skip** the offline test until you have a suitable router/firewall. Some consumer-router “block device” features disable LAN as well as WAN and would make the result meaningless.
- Keep a simple baseline of locally viewed footage, HKSV motion recording, and any ADT app behavior before making changes. Do not publish screenshots with identifiable scenes or credentials.

## Reversible phase A — Camera WAN isolation (no reboot)

1. In a router/firewall that supports **per-device outbound policies**, identify the test camera by its current network assignment (prefer a stable DHCP reservation). Create a reversible rule denying its **internet-bound** IPv4 and IPv6 traffic while **preserving LAN communication**, including RTSP/TCP port 554 to the Scrypted host. Consider what DNS and NTP the camera normally reaches; changing those paths may affect startup or logs.
2. Verify the rule actually prevents **the camera** from reaching the internet; do not merely assume a switch labeled “block” works. The Scrypted server, HomePod, router, and other cameras must retain normal connectivity.
3. Without altering the camera's pairing or settings, check its Scrypted live view and whether OpenCV motion still triggers HKSV recordings. Check the camera's availability for at least a few test sessions. Note timestamps and any dropouts.
4. Remove the rule and verify normal behavior returns. If anything stops working, restore the previous network policy immediately and document the symptom before pursuing more tests.

**Interpretation:** Success means an *already enrolled, already running* camera served local RTSP during a temporary camera-only WAN outage. It does not prove that a new session will work after power loss, long-term token expiry, or subscription cancellation.

## Reversible phase B — Start-up while WAN-isolated (higher risk; optional)

Only if phase A succeeds and you can tolerate temporary loss of that camera, apply the same narrowly scoped rule, then reboot **only the test camera** using an authorized power cycle. Do not reset it, factory-default it, or remove it from ADT. Check whether it acquires a LAN address and serves authenticated port-554 RTSP after startup. Restore WAN access if it fails. Consider repeating phase A over longer periods before drawing any reliability conclusions. This phase can reveal cloud-dependent initialization but still says nothing conclusive about cancellation.

## Later, before any subscription decision

- Verify the cameras after *normal* reboots, lease renewal, extended uptime, and firmware updates where safe. Do not assume saved credentials are permanent.
- Identify an independent recording destination if recordings must survive loss of both ADT and Apple iCloud services. **HKSV itself depends on an operational Apple Home hub and Apple cloud account/network path; it is not a fully offline recording archive.** Local Scrypted video playback is distinct from continuous local recording.
- Ask ADT about camera behavior and entitlement changes when service ends; treat replies as policy/vendor claims, not tests of this specific firmware. Even with a successful temporary WAN test, plan for the possibility that cancellation revokes tokens, removes credentials, unenrolls devices, or changes provisioning.
- Do not cancel active ADT monitoring merely on the basis of RTSP working today. Preserve a fallback recording/safety arrangement before taking any irreversible step.

## Safe public results template

```text
Camera: OC845 / RC845 (firmware if known)
State before test: enrolled + working / other
Test: WAN blocked while running / reboot while WAN blocked / other
Network: camera-only outbound internet blocked, LAN RTSP allowed (yes/no)
Live local RTSP: pass/fail + duration
Scrypted/HKSV with HomePod still online: pass/fail/not tested
Camera reboot during test: yes/no
WAN restored and camera recovered: yes/no
Subscription status during test: active / canceled (do not guess)
Notes: sanitized; no camera IPs, screenshots, stream URLs, or credentials
```

## Related documentation

- [Current installation/compatibility evidence](../COMPATIBILITY.md)
- [Verified local RTSP discovery](DISCOVERY.md)
- [Scrypted camera setup](nvr-scrypted.md)
- [Security and credential handling](../SECURITY.md)
