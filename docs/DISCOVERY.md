# Investigation notes: how we uncovered local RTSP on ADT Command cameras

This is the **research and troubleshooting record**, not the quickest installation guide. If you just want your own cameras working, start with the [step-by-step how-to](GETTING_STARTED.md) and [Scrypted guide](nvr-scrypted.md).

**Tested:** November 15, 2026 · ADT Control for iOS · two OC845 cameras and one RC845 · Fedora 45 · Scrypted v0.147.0 on Home Assistant OS.

## The question

Could still-enrolled ADT Command / Alarm.com cameras provide a usable local feed to an independent RTSP client without resetting or replacing their firmware? And, if so, could that work with a common NVR installation such as Scrypted on HAOS?

We showed that the camera's **local media path** is accessible after an authorized account session supplies the camera credentials. This does **not** establish that its credentials are permanent, its control plane is cloud-independent, or its stream survives the loss of an ADT subscription.

## Starting point and outside research

An earlier report by **dppeak** in [Omar-L/adc-video-bridge issue #35 (August 2026)](https://github.com/Omar-L/adc-video-bridge/issues/35) documented local camera RTSP URLs returned by the Alarm.com mobile API with action `UberLoginNew`, as well as nonstandard HTTPS-tunneled high ports. We used that observation as a lead and tested our own ADT Control installation. The original report deserves credit for the prior local RTSP discovery.

## Experiment 1 — Inspect the authenticated app's response

We used **mitmweb** as a temporary HTTPS interception proxy for an iPhone already signed into **our own** ADT Control account. The mobile app made requests to:

```text
https://adt-ios-mobile.alarm.com/MobileServlet/SubmitRequest.aspx
```

In our capture, an `UberSeamlessLoginNew` response included the camera information. The earlier `UberLoginNew` action was **not** the only way to retrieve it, which matters for users of ADT Control iOS. Response contents can vary by request/session.

We also encountered mitmweb filter syntax differences between versions, so filtering visually by host and request action was more reliable than assuming a particular search expression.

The useful response was **gzip-compressed XML**, with a top-level `<slnr>` element. Some mitmweb views displayed garbled binary. Copying that displayed text into an editor corrupted its bytes; saving the response body as a binary file and decompressing it when necessary worked.

Under the XML structure, camera `<cli>` records contained `lre`, `l`, and `p` as **attributes**, not child elements. The `lre` value carried a camera-specific RTSP URL such as the following invented pattern:

```text
rtsp://<user>:<password>@<camera-lan-ip>:<high-port>/img/media.sav?stream=<camera-specific-value>
```

The three recorded high ports fell in the **41925–41927** range; they were different per camera. The paths, users, passwords, and query data are not published. The wizard parses locally and defaults to no sensitive output.

**Security note:** A captured login response may also include broader account data, tokens and cookies. No raw capture belongs in issues, logs or Git history. We are not providing an authentication bypass; authorized access to one's own app session is required.

## Experiment 2 — Understand the high-port transport

The captured `lre` URL was not ordinary plain RTSP, despite beginning with `rtsp://`:

| Attempt | Observation |
| --- | --- |
| Plain `rtsp://` to the captured camera-specific high port | Failed with an invalid-data response |
| Change the scheme to `rtsps://` | Did not work: RTSP directly over TLS differs from RTSP tunneled over HTTPS |
| FFmpeg `-rtsp_transport https` with a certificate-verification override | Reached a camera certificate-verification failure in our FFmpeg build |
| Local `socat` TLS bridge, then FFmpeg `-rtsp_transport http` | **Succeeded**: FFprobe detected video/audio stream metadata |

We bound `socat` to **127.0.0.1** and connected its outgoing side to the private camera IP/high port with TLS `verify=0`, limited to that specific local camera endpoint. We preserved the original login credentials, path, and query, and changed only the client-facing relay address. This workaround is still available as the [TLS fallback](TLS_FALLBACK.md).

## Experiment 3 — Decode actual video

A successful FFprobe probe reported **H.264 at 1920×1080** plus **G.711 μ-law audio** from the driveway OC845. Initially, Fedora's packaged `ffmpeg-free` had only the `libopenh264` decoder available and FFplay repeatedly emitted `DecodeFrame failed`. Replacing that build with full FFmpeg from RPM Fusion, after inspecting the DNF transaction, allowed visible playback.

Using the TLS relay, **all three cameras produced live pictures in FFplay**:

| Camera | Model | Verified at this stage |
| --- | --- | --- |
| Driveway | OC845 | Live video, H.264 1080p metadata, G.711 μ-law audio stream identified |
| Basement | RC845 | Live video through TLS relay |
| Lake | OC845 | Live video through TLS relay |

The audio *track* was identified; successful audio playback in HomeKit/Scrypted is a separate question.

## Experiment 4 — The simpler port-554 discovery

When considering Scrypted on **Home Assistant OS**, we realized that having to run `socat` and a separate restreamer would make the system unnecessarily complex. Previously, port **554** on the driveway camera had returned `401 Unauthorized` when we didn't yet possess its credentials. We retested the camera **with the credentials from the authenticated XML** and the same camera-specific path/query.

That one change worked. FFprobe using **ordinary RTSP/TCP directly to port 554** returned the H.264 and G.711 tracks. We then used the Scrypted **RTSP Camera** plugin's separate URL, username and password fields. A **live driveway-camera picture displayed in Scrypted v0.147.0 on HAOS**. No `socat`, MediaMTX or other restreamer was required.

The basement RC845 and lake OC845 were subsequently **configured in Scrypted**. We do **not** yet have separately documented proof of their long-duration stability, audio, or direct preview behavior. This distinction is intentional: connecting a device in a plugin is not identical to validating every media feature.

### Why the two ports differ

- **Port 554** — standard RTSP/TCP, authenticated with the same recovered camera credentials; confirmed for the driveway and used for its direct Scrypted preview. Typically plaintext on the LAN.
- **Captured high port** — a **different HTTPS-based RTSP tunnel** exposed by the camera and represented by `lre`. It is not interchangeable with `rtsp://...:554` and requires compatible HTTPS tunneling or the documented relay.

The raw high-port `lre` URL is **not** a drop-in URL for the Scrypted RTSP Camera plugin. The wizard's Scrypted mode intentionally constructs a port-554 URL (preserving the original camera-specific path and query).

## What is established, and what remains unknown

**Verified:** An authorized ADT Control response can provide credentials; the tested cameras can deliver usable local video via the documented relay; and a driveway OC845 can serve and display live video directly through standard RTSP/TCP to Scrypted on HAOS.

**Unverified:** Functioning without internet, after ADT service cancellation, after reboot or credential rotation, on additional camera firmware/models, with long-term Scrypted stability, with HomeKit Secure Video, with motion events, or with audio in the NVR. We do **not** suggest disconnecting a monitored alarm system or canceling a subscription to test this prematurely.

## Sources and technical references

- **Prior research by dppeak:** [Omar-L/adc-video-bridge issue #35](https://github.com/Omar-L/adc-video-bridge/issues/35)
- [mitmproxy: certificates](https://docs.mitmproxy.org/stable/concepts-certificates/)
- [mitmproxy: getting started](https://docs.mitmproxy.org/stable/overview/getting-started/)
- [FFmpeg RTSP protocol documentation](https://ffmpeg.org/ffmpeg-protocols.html)
- [Apple Lockdown Mode](https://support.apple.com/en-us/105120)

The [how-to](GETTING_STARTED.md) is the maintained procedure. This page records *why* we chose it, what failed along the way, and the limits of our evidence.
