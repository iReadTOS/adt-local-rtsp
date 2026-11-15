# Reverse engineering: Sercomm RTP padding and native motion events

**Experimental research (November 15, 2026).** This page records **observations** from three owned, enrolled ADT cameras, not a supported vendor API. It does not establish compatibility with other models or firmware. The native motion monitor is read-only and optional; Scrypted/OpenCV/HKSV can continue working without it.

## Key discovery: RTSP `padding=yes`

An authenticated RTSP/TCP connection to port 554 may deliver Sercomm-specific metadata in the RTP padding when the existing camera-specific stream query includes `padding=yes`. The **stream path/query must be taken from the user's own authorized capture**; do not assume a universal stream token.

On an outdoor OC845, a comparison using the same RTSP transport with `padding=no` versus `padding=yes` changed the fraction of padded RTP packets from zero to nonzero. On an indoor RC845, a later comparison counted **0/299** padded packets with `padding=no` and **71/231** padded packets with `padding=yes`; each padded packet carried **32 bytes of RTP padding** (31 bytes of metadata plus one trailing RTP pad-length byte). The runs are short and not controlled measurements of throughput.

These **example packet bytes are sanitized, non-secret protocol metadata from the observed format** (no video, passwords, tokens, or identifiable imagery):

```text
OC845 inactive:
00 00 00 1f 01 0d 00 00 00 00 00 00 00 00 00 00 00 00 00 02 02 00 00 03 01 00 c1 00 00 bf 00
OC845 trigger:
00 00 00 1f 01 0d 00 00 00 00 00 00 00 00 00 00 00 00 00 02 02 00 00 03 01 01 c1 00 00 bf 00
RC845 observed (31-byte RTP padding metadata, 28 meaningful bytes):
00 00 00 1c 01 0d 00 00 00 00 00 00 00 00 00 00 00 00 00 02 02 00 00 c1 00 00 bf 00 00 00 00
```

The first **four bytes** are a big-endian length of *meaningful metadata*, **not always the full 31 bytes**. Commands follow as a type and length with an associated data field. The OC845 samples carry `0x03 0x01 0x00` and `0x03 0x01 0x01` (one-byte `0x03` values observed as inactive and momentary triggered while moving). A five-second software hold is used in the prototype to turn brief trigger pulses into usable ON/OFF events; it is **not** a camera setting or native event duration.

## Hardware results (one installation, firmware `V1.0.01R53`)

| Model | Standard RTSP/TCP | Native motion evidence | Limitations |
| --- | --- | --- | --- |
| OC845 A (outdoor) | Authentication and RTP worked | 1,337 decoded PIR samples, 8 trigger pulses, 3 held events in a 90s run | Trigger range and false-positive rate not quantified |
| OC845 B (outdoor) | Authentication and RTP worked | 882 decoded PIR samples, 28 trigger pulses, 4 held events in a 60s run | Trigger range and false-positive rate not quantified |
| RC845 (indoor) | Authentication and RTP worked | 177 padded packets in 12s; **no `0x03` PIR command**; `0x01` 13-byte payload stayed all zero for 595 samples during deliberate movement | Cannot infer lack of a physical sensor, disabled firmware feature, or global lack of motion alerts from this stream alone |

An HTTPS capability query returned `pir_sensor=on` for all three tested cameras. That is a **capability flag**, not proof that the RC845 publishes an active PIR state or that motion detection is enabled. The RC845's three trailing zeros caused the prototype's first strict-length parser to reject its samples; the published parser now accepts correctly bounded trailing zero filler and still reports **PIR absent**.

Older Sercomm documentation provides clues about command `0x01` and other status fields, but **the exact semantics of every field have not been established for ADT's firmware**. Do not label its all-zero payload "motion disabled" as a proven fact. Reading `padding=yes` does not enable the sensor or change its schedule.

## Reliability and why PIR is not a drop-in OpenCV replacement

The outdoor OC845's PIR detection range is specified as approximately **16 ft / 5 m** in its installation literature. Its video field of view extends farther. Native PIR may miss cars, animals, or people at distance that image-based detection can see. The prototype also requires a full RTSP media connection over the network even though it discards media frames and performs no video decode. This is not a measured CPU or network improvement for any particular deployment.

For our installation, Scrypted/OpenCV has already triggered **actual HomeKit Secure Video recordings**, so there's no operational reason to replace it solely to use experimental PIR. Leave OpenCV in service unless separate comparative testing supports a change. MQTT publishing and Scrypted custom motion routing were **not** tested against a real broker in this project; code is optional and experimental.

## Reproduce safely

See [the standalone native PIR experiment](native-pir-experiment.md) for the command and its constraints and [optional MQTT proof of concept](native-pir-mqtt.md) for code that has **only passed simulated-broker tests**. Never publish captured ADT responses, stream-query tokens, full RTSP URLs, PCAPs, or MQTT credentials. In particular, no part of this project is an alarm/intrusion-detection guarantee.

## References

- [RFC 2326: RTSP 1.0 and interleaved RTP over TCP](https://datatracker.ietf.org/doc/html/rfc2326#section-10.12)
- [Older Sercomm camera API research](https://github.com/edent/Sercomm-API) — possible protocol clues, not validation of ADT firmware semantics
- [OC845 installation manual (manufacturer filing)](https://fccid.io/P27OC845/User-Manual/Users-Manual-4489631.pdf)
