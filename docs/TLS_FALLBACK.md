# Optional fallback: RTSP over HTTPS via a local TLS relay

**Only use this if direct authenticated RTSP/TCP on port 554 does not work.** Our Scrypted/HAOS driveway camera works on **554 without any relay**. If you are just setting up Scrypted, use the [normal how-to](GETTING_STARTED.md) and [Scrypted guide](nvr-scrypted.md) instead.

The `lre` attribute in the authenticated ADT response describes a **camera-specific high port** that, on our cameras, expected **RTSP tunneled over HTTPS**. This is different from ordinary plaintext RTSP on port 554 and from `rtsps://` (RTSP directly wrapped in TLS).

We successfully used this fallback to display **all three cameras in FFplay** on Fedora. It is a **local test workflow**, not a recommendation to run a restreamer on HAOS.

## Prerequisites

- A saved, private authenticated ADT response as described in [steps 1–2 of the how-to](GETTING_STARTED.md#step-1--capture-your-own-adt-control-login-response).
- Python 3, this repository's `adc_local_test.py`, FFprobe/FFplay, and `socat` on the **same computer**.
- Camera and computer on the same reachable LAN.

On Fedora:

```bash
sudo dnf install socat
command -v ffprobe
command -v ffplay
```

If FFprobe/FFplay are missing, install a suitable FFmpeg build. Review dependency changes first, particularly if switching multimedia packages (see below).

## Step 1 — List cameras without exposing credentials

```bash
python3 adc_local_test.py ~/adt-private/login-response.bin list
```

Use the **camera's captured LAN IP and high port** from the output. The original tested high ports varied across cameras; your values may differ. This safe listing does not show the `lre` username/password.

## Step 2 — Start the loopback-only TLS relay

In **Terminal 1** (replace placeholders with your camera's address/port):

```bash
socat -d -d \
  TCP4-LISTEN:8554,bind=127.0.0.1,reuseaddr,fork \
  OPENSSL:CAMERA_LAN_IP:CAMERA_TLS_PORT,verify=0
```

Traffic flow: **FFmpeg on this computer → local 127.0.0.1:8554 → `socat` → encrypted TLS to camera's private IP/high port**. The loopback listener prevents access from other LAN devices. `verify=0` disables verification only for this outgoing camera TLS connection; it is not a global trust change. Use it only for devices you administer on a trusted LAN.

`socat` doesn't need the RTSP username/password itself. The Python helper preserves those credentials in the client URL, which may temporarily be visible to other local processes as FFmpeg arguments.

## Step 3 — Probe, then play

In **Terminal 2**, while `socat` is running:

```bash
python3 adc_local_test.py ~/adt-private/login-response.bin probe \
  --index 1 --relay-port 8554
```

The helper builds a local `rtsp://...@127.0.0.1:8554/...` URL and calls FFprobe using **`-rtsp_transport http`**. The HTTP transport flag is essential; the relay is **not a plain-RTSP server**. Camera index `1` is only an example: use the index shown by the list command.

Once FFprobe reports tracks, test **actual frames**:

```bash
python3 adc_local_test.py ~/adt-private/login-response.bin play \
  --index 1 --relay-port 8554
```

Press **Q** in the FFplay window to exit. Successful SDP/FFprobe metadata alone does not establish playable video.

For other cameras, repeat using their **own captured high ports**, choosing different local relay ports and matching index/relay-port arguments (e.g., `8555` and camera `2`). Don't reuse the first camera's credentials or query string.

## Fedora 45 H.264 decoder issue

We initially identified tracks with FFprobe but FFplay printed repeated `libopenh264 DecodeFrame failed` errors. Our Fedora `ffmpeg-free` build did not have the native H.264 decoder available. Check your installed decoders:

```bash
rpm -q ffmpeg-free ffmpeg
ffmpeg -hide_banner -decoders | grep -Ei 'h264|openh264'
```

Our solution was the **full FFmpeg package from RPM Fusion**, enabling RPM Fusion Free if it was not already enabled:

```bash
sudo dnf install \
  https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
```

Preview the proposed replacement **before accepting it**:

```bash
sudo dnf swap ffmpeg-free ffmpeg --allowerasing --assumeno
```

Only proceed if it does **not** remove unrelated important applications:

```bash
sudo dnf swap ffmpeg-free ffmpeg --allowerasing
ffmpeg -hide_banner -decoders | grep -Ei 'h264|openh264'
```

This was a Fedora-specific playback problem, not evidence that the camera was cloud-only.

## Why we needed this fallback initially

| Attempt | Result in our environment |
| --- | --- |
| Standard `rtsp://` against the captured **high port** | Invalid data |
| Changing scheme to `rtsps://` | Failed |
| FFmpeg's `-rtsp_transport https` with certificate override | Camera certificate verification failed |
| `socat` local TLS relay plus FFmpeg `-rtsp_transport http` | **Worked**; all three streams played after the decoder fix |

The easier standard **port 554** access was discovered *later*, after reusing the newly recovered credentials. See [the research narrative](DISCOVERY.md) for the actual sequence.

## Limits and security

The HTTPS-tunneled high port is not a drop-in replacement for standard RTSP. Do not expose the relay to the internet, publish authenticated URLs, or leave the proxy/certificate from the capture stage enabled. This fallback doesn't establish operation after an ADT subscription ends or during a WAN outage.
