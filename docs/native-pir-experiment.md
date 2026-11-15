# Experimental native PIR monitoring over RTSP

This **research prototype** connects directly to a Sercomm/ADT camera using standard RTSP/TCP on port 554, requests `padding=yes`, and parses the camera's proprietary PIR information from the RTP padding. It is **not** a production security sensor, Home Assistant integration, or Scrypted plugin. The video frames are discarded, not decoded or recorded.

## Evidence and current limits

Our **driveway OC845, firmware V1.0.01R53**, showed that `padding=no` returned zero padded RTP packets, while `padding=yes` produced 32-byte padding blocks in approximately one-third of observed packets. The 31 data bytes inside the padding matched the Sercomm structure and contained command `0x03`, length `0x01`, with values `0x00` and `0x01`. The user observed `0x01` pulses while walking in front of the camera. A completely isolated stationary comparison under the same lighting/conditions and prolonged false-positive testing remain worthwhile.

Both outdoor OC845 and indoor RC845 cameras report `pir_sensor=on` and identical `V1.0.01R53` firmware via the authenticated HTTPS `/util/query.cgi?extension=yes` endpoint. **Live Python RTSP/PIR decoding has now been verified on the driveway and lake OC845 models.** The RC845 provides metadata without a PIR command; see the hardware verification section below.

## Run the standalone prototype

You need the existing `adc_setup_wizard.py` in the same repository directory and your **private** captured ADT Control response file (XML or gzip). The capture contains reusable credentials; never commit, screenshot, or share it.

```bash
cd ~/Downloads/adt-local-rtsp
python3 -m unittest discover -s tests -v

python3 adc_motion_monitor.py \
  --capture ~/adt-private/login-response.bin \
  --camera CAMERA_LAN_IP \
  --duration 90 \
  --hold 5
```

The example IP and capture path reflect our test installation—use the actual LAN address and capture path for your own authorized camera. No root or TShark required. Python standard library only.

The monitor prints RTSP connection status, raw PIR status transitions, and `MOTION ON` / `MOTION OFF`. `0x01` and `0x11` are **tentatively treated as trigger pulses**; a five-second hold prevents single-packet pulses from immediately clearing the motion state. That hold interval is a heuristic, not a camera capability. Repeated pulses within the hold interval extend it. It attempts to reconnect if the stream breaks and exits after the requested duration. `Ctrl+C` stops it.

**Compare against the existing Scrypted OpenCV events while testing**, but don't disable OpenCV or alter HKSV settings until native events have been shown to work reliably. Correlate state changes with intentional motion, periods of no motion, and changing illumination. Continue to use Scrypted's working recording path for security-sensitive needs.

## Security and supported scope

- Monitor uses a *separate* standard RTSP/TCP connection on the local network. Your existing Scrypted camera configuration isn't changed.
- Camera credentials and stream query tokens are loaded from a file in process memory, not passed to a subprocess or printed. RTSP authentication itself may involve Basic or Digest; plain RTSP/TCP is **not encrypted**, so only use this on a trusted private network.
- The script validates RFC1918 IPv4 camera addresses and limits redirect/control URLs to the same local camera. It makes no cloud calls and changes no camera settings.
- Data is read from interleaved RTP on the RTSP socket. No video or packet captures are written to disk. The camera metadata frame parser has offline tests using the two observed 31-byte samples and synthetic RTP packets.
- RTSP camera implementations differ. A successful `ffprobe` session doesn't prove this standalone RTSP client will negotiate with the same firmware; if the client returns a sanitized `RTSP DESCRIBE/SETUP/PLAY` status error, report only that error and **not** the camera's authenticated URL, full SDP, or capture file.

## Next milestones

The direct client has now produced credible PIR events on both OC845 cameras, and the RC845 does not include the `0x03` PIR command in its observed metadata. The next milestone is the optional [native PIR MQTT pilot](native-pir-mqtt.md) and multi-day comparison with Scrypted OpenCV under changing conditions. Integrating the binary sensor with Scrypted HKSV requires a separately validated bridge; adding an MQTT sensor to Home Assistant does not automatically make it a Scrypted camera motion event.

Reference: [RTSP 1.0 interleaved RTP specification](https://datatracker.ietf.org/doc/html/rfc2326#section-10.12) and [older Sercomm camera API research](https://github.com/edent/Sercomm-API).

## RTSP authentication compatibility (experimental update)

The initial Python RTSP client failed with `RTSP DESCRIBE returned status 401` on a camera whose feed plays with FFmpeg. That **does not establish that the camera credentials are wrong**: the original client's Digest header had a different format from FFmpeg, and it skipped FFmpeg's initial `OPTIONS` request.

This experimental update sends `OPTIONS` before `DESCRIBE` and formats Digest authorization like FFmpeg for common embedded-camera compatibility (quoted `qop`, no `algorithm` field unless advertised). These adjustments passed mocked-server tests **and worked on both outdoor OC845s in live sessions**.

Retry normally first:

```bash
python3 adc_motion_monitor.py \
  --capture ~/adt-private/login-response.bin \
  --camera CAMERA_LAN_IP --duration 90 --hold 5 --retries 0
```

If you still get `401` and the camera advertises Basic authentication, an **explicit opt-in diagnostic** is available:

```bash
python3 adc_motion_monitor.py \
  --capture ~/adt-private/login-response.bin \
  --camera CAMERA_LAN_IP --duration 30 --hold 5 \
  --retries 0 --auth basic
```

**Security:** Basic RTSP authentication transmits reusable credentials in a trivially reversible form over the unencrypted local network. Do not use `--auth basic` on an untrusted LAN. Basic mode is **never an automatic fallback** when Digest fails. Do not repeatedly try incorrect credentials. Do not share RTSP packet dumps, debug trace logs, private capture files, stream URLs, or process command lines.

The standard tests are offline and do not guarantee compatibility with every camera firmware. Even after receiving live PIR samples, leave the working Scrypted/OpenCV/HKSV configuration unchanged until native detection has been compared against video-based motion in actual weather, day and night, and over varying distances.


## Actual hardware verification (2026-11-15)

The auth compatibility fix succeeded on real V1.0.01R53 hardware. Two OC845 cameras successfully produced native PIR trigger events using the standalone Python RTSP client: driveway 1,337 samples / 8 trigger pulses / 3 held motion events over 90 seconds, and lake 882 samples / 28 pulses / 4 held events over 60 seconds. Those counts represent observed experiments only; they do not establish detection accuracy across weather, seasons, or far-field distances.

The basement RC845 connected successfully but yielded no PIR values. TShark verified 71 padded RTP packets, all 32-byte padding, when `padding=yes` was requested. Our client saw 177 padded packets in 12 seconds. Its metadata declared 28 meaningful bytes followed by 3 zero filler bytes, and contained no `0x03` PIR command. During intentional motion, 595 valid samples of the 13-byte command `0x01` field remained all zero. The updated decoder accepts the declared-length difference while treating PIR as **unavailable**.

An **opt-in MQTT pilot** is now available; see [native-pir-mqtt.md](native-pir-mqtt.md). HomeKit remains driven by OpenCV during the pilot. The official OC845 manual specifies only 16 feet / 5 meters as PIR detection range; do not assume native PIR will catch distant cars or people in the grass.

**Public examples:** `CAMERA_LAN_IP` is a placeholder to replace with your own camera's RFC1918 address; the `~/adt-private/login-response.bin` path likewise represents a private file you captured for an account you administer. The published examples do **not** contain our camera IPs or captured response. This monitor is not required for local RTSP or Scrypted.
