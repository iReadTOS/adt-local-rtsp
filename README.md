# ADT Command / Alarm.com cameras: verified local RTSP access without resetting them

**A reproducible discovery and playback guide — tested November 15, 2026**  
**Scope:** ADT Control on iOS; one indoor **RC845** and two outdoor **OC845** cameras; Fedora Linux used for capture, relay, and testing.

> **TL;DR:** Yes: on our tested OC845 and RC845 cameras, the credentials recovered from an authenticated ADT Control iOS login response work with **ordinary RTSP over TCP on port 554**. The driveway OC845 displayed live video in **Scrypted v0.147.0 running as a Home Assistant OS add-on**, with no external restreamer. The other two cameras have also been added to Scrypted. The original `lre` URL uses a *different* camera-specific high port with an HTTPS-based RTSP tunnel; we retain that method below as a fallback. **Local video does not establish that the cameras work after an ADT cancellation or loss of internet.**

This write-up documents a working procedure, including the problems encountered along the way. It is intended for people inspecting **cameras and accounts they own or are authorized to manage**. It does not exploit the camera, bypass account authentication, brute-force a password, or require resetting the device. Different ADT products, firmware versions, or account configurations may behave differently.

## Quick start — direct RTSP and Scrypted (recommended)

1. On your **own** ADT Control iOS account, capture the authenticated `UberSeamlessLoginNew` response with mitmproxy and save its raw XML/gzip body outside the repository. See [§4–§5](#4-capture-the-adt-control-mobile-response). **Never publish the capture.**
2. Start the **interactive, standard-library-only configuration wizard**:

   ```bash
   python3 adc_setup_wizard.py
   ```

   Optionally provide a file explicitly:

   ```bash
   python3 adc_setup_wizard.py --capture ~/adt-private/login-response.bin
   ```

3. Choose the capture file, camera numbers or IP(s), the LAN IP override if needed, and direct RTSP port **554** (default). Pick **Scrypted** to obtain a URL without embedded login credentials, plus the username and password in separate fields. The wizard makes you explicitly type `REVEAL` and can store secrets in a *new, permissions-restricted file* outside Git.
4. In the **RTSP Camera** plugin in Scrypted, add a camera and enter the separate **RTSP Stream URL**, **Username**, and **Password**. Use the actual stream query returned from the authenticated capture; do **not** assume `/img/media.sav?stream=2` applies to all cameras. Test live video. For a complete worked example, see [Scrypted / NVR guide](docs/nvr-scrypted.md).
5. For NVRs that require embedded credentials (e.g. some Blue Iris configurations), choose **Blue Iris / generic NVR** in the wizard to export the complete `rtsp://username:password@CAMERA_LAN_IP:554/...` URL. **Blue Iris itself has not yet been tested** on this system.

**Choose a mode:** Safe summary (no passwords or stream tokens); Scrypted (separate fields); NVR (complete authenticated direct RTSP URL); or original high-port URL (advanced HTTPS-tunnel diagnostics). The original safe `adc_local_test.py` is preserved. See [Compatibility](COMPATIBILITY.md) for test scope.

**Security:** Direct RTSP on port 554 is typically **unencrypted**. Keep cameras on a trusted LAN and **never port-forward RTSP**. The URL's query may itself contain a secret even when credentials are entered separately. If port 554 does not work on your model, the [older local TLS relay method](#7-bridge-the-cameras-tls-tunnel-locally-with-socat) remains documented below.

## Advanced export of full camera URLs

**Prefer the interactive [`adc_setup_wizard.py`](adc_setup_wizard.py)**. It supports file selection, camera selection by index/IP, optional LAN IP overrides, port choice, optional FFprobe connectivity checks, Scrypted-friendly separate credential fields, and complete authenticated standard-RTSP URLs for NVR clients. It requires an explicit reveal confirmation, prints nothing sensitive by default, and can write a new mode-`0600` private file (no overwrite) outside Git.

The older [`adc_url_export.py`](adc_url_export.py) is retained for command-line power users who want the **original HTTPS-tunneled high-port** URL and the local `socat` bridge URL. Its output also includes the simpler direct-port-554 and Scrypted formats. The original high-port URL is **not** interchangeable with the working plain RTSP/TCP port-554 URL.

```bash
mkdir -p -m 700 ~/adt-private
python3 adc_url_export.py ~/adt-private/login-response.bin \
  --index 1 --save-to ~/adt-private/camera-1-urls.txt \
  --i-understand-the-risk
```

Do not submit any capture, credentials, stream tokens, or exported URLs to GitHub issues, forums, support tickets, or screenshots. Credentials and possibly stream tokens grant access to live camera feeds.

## Compatibility at a glance

| Model | Test result | Verified media | Notes |
| --- | --- | --- | --- |
| OC845 (driveway) | **Live in Scrypted + FFplay** | H.264 1080p + G.711 μ-law audio | Direct RTSP/TCP **554**; TLS relay also tested |
| RC845 (basement) | **Live in FFplay; added to Scrypted** | Live picture (exact codecs not recorded in the publication) | TLS relay verified; port-554 Scrypted config added |
| OC845 (lake) | **Live in FFplay; added to Scrypted** | Live picture (exact codecs not recorded in the publication) | TLS relay verified; port-554 Scrypted config added |

These are three camera instances from **one installation**, not a claim that every firmware/ADT variant is compatible. Submit additional verified reports using the template in [COMPATIBILITY.md](COMPATIBILITY.md). Testing without an active ADT subscription remains outstanding.

## 1. What we actually proved

On November 15, 2026, the following worked on three ADT-enrolled cameras:

| Camera | Reported model | Result |
| --- | --- | --- |
| Driveway | OC845 | Authenticated local feed played; H.264 **1920×1080**, plus **G.711 μ-law audio** detected |
| Basement | RC845 | Authenticated local feed displayed in FFplay |
| Lake | OC845 | Authenticated local feed displayed in FFplay |

The original verified fallback path was **camera (private LAN IP) → encrypted TLS connection → local `socat` relay → FFplay on the same LAN**. We subsequently confirmed a **direct authenticated RTSP/TCP stream on port 554** for the driveway camera and displayed it in Scrypted running in HAOS without a relay. No ADT or Alarm.com cloud video relay was used for these playback sessions. The **initial credentials came from an authenticated ADT Control API response**, and the cameras may still contact the cloud for other purposes. We have **not** yet tested whether the cameras continue serving these streams with the internet disconnected, after a reboot, after credential rotation, or after an ADT subscription is canceled.

This work builds on the earlier discovery by **dppeak in August 2026**, documented in [Omar-L/adc-video-bridge issue #35](https://github.com/Omar-L/adc-video-bridge/issues/35). That report describes the Alarm.com mobile API returning local RTSP credentials with an `UberLoginNew` response. Our test adds a particularly useful detail for ADT Control iOS: **`UberSeamlessLoginNew` also returned the camera records**, within an `<slnr>` XML document. It also demonstrates **audio on this OC845**, whereas the cameras in the earlier report had no audio stream.

## 2. Requirements and security precautions

You need:

- An ADT Control / Alarm.com account authorized to view the cameras, with the iOS app already working.
- A computer on the same LAN as the cameras; our commands use **Fedora 45**. The general method can be adapted to other operating systems.
- `mitmproxy` / `mitmweb` to inspect **your own authenticated app traffic**.
- **Optional:** `ffprobe` for direct RTSP connectivity testing and `ffplay` for local playback. `socat` is needed only for the legacy high-port TLS-tunnel fallback, not for Scrypted direct RTSP on port 554.
- The ability to adjust the iPhone's Wi-Fi proxy and temporarily trust a locally generated root certificate.

**Sensitive information warning:** The captured response may contain account tokens, camera login credentials, camera addresses, and account/device metadata. **Never publish a raw capture, decrypted response, full `lre` URL, screenshots containing secrets, mitmproxy CA private keys, or any captured cookies.** The companion Python helper prints only camera metadata, not credentials. It does pass the authenticated URL to a local FFmpeg process as an argument, which other local users/process-monitoring tools may be able to inspect. Use a trusted computer and clean up afterward.

**Lockdown Mode:** Apple's Lockdown Mode blocks installation of new configuration profiles. If you use it, a spare test phone is preferable. Otherwise, you may need to temporarily turn it off and restart to install the mitmproxy certificate; restore it promptly when capture is finished. Do not browse unrelated sensitive websites while HTTPS interception is enabled.

## 3. Install the tools on Fedora

```bash
sudo dnf install uv
uv tool install mitmproxy

# Optional local testing tools:
command -v ffprobe
command -v ffplay
# Only if you need the fallback HTTPS tunnel:
sudo dnf install socat
```

If `ffprobe` or `ffplay` is absent, install a suitable FFmpeg package. **Do not swap multimedia packages blindly**; there is a Fedora decoder note in §9. In our case, the default Fedora `ffmpeg-free` build identified the streams but its `libopenh264` decoder could not display the H.264 picture. Switching to the RPM Fusion full FFmpeg package resolved playback.

Find your computer's LAN IP (for example, using `ip -4 addr`); we'll call it `COMPUTER_LAN_IP`. The phone and computer must be able to communicate over the local network.

## 4. Capture the ADT Control mobile response

On the Fedora computer, start mitmweb:

```bash
~/.local/bin/mitmweb \
  --listen-host COMPUTER_LAN_IP \
  --listen-port 8080 \
  --set web_host=127.0.0.1 \
  --set web_port=8081
```

Replace `COMPUTER_LAN_IP` with your real LAN address. Open the interface **on the Fedora computer** at `http://127.0.0.1:8081`. Port 8081 stays local; port 8080 accepts traffic from the iPhone. If Fedora's firewall blocks the connection, you can **temporarily** open port 8080 in your active zone:

```bash
sudo firewall-cmd --add-port=8080/tcp
```

Do **not** forward either port on your internet router.

On the iPhone, open **Settings → Wi-Fi → (i) next to the current network → Configure Proxy → Manual**. Set server to `COMPUTER_LAN_IP`, port `8080`, authentication off. In Safari, explicitly open **`http://mitm.it`** (not HTTPS) and follow the iOS certificate-installation steps. Install the downloaded profile under **Settings → General → VPN & Device Management**, and then enable trust under **Settings → General → About → Certificate Trust Settings**.

In our setup, the default onboarding page did not appear consistently. An alternative that worked was restarting mitmweb with `--set onboarding_host=example.com` and opening **`http://example.com`** explicitly. If Safari automatically upgrades the page to HTTPS, manually replace `https://` with `http://`.

Verify that Safari can open an ordinary HTTPS site through the proxy **and that the requests appear in mitmweb**. Then open ADT Control and view a camera. Our iOS app worked through the proxy without additional app patching.

Look for HTTP POSTs to the endpoint:

```text
https://adt-ios-mobile.alarm.com/MobileServlet/SubmitRequest.aspx
```

Select larger responses, open the **Request** details, and look for the form field `Action`. In our capture the useful action was:

```text
UberSeamlessLoginNew
```

A seamless login may occur when restoring an existing session; we did not need to forcibly log out first. The earlier Alarm.com research observed `UberLoginNew`, which is also worth looking for on other app variants. Different responses for the same action can contain different amounts of camera metadata.

## 5. Save the response body without mangling it

The response in our capture was XML compressed with gzip. It had these **response** headers:

```text
Content-Type: text/html
Content-Encoding: gzip
```

Mitmweb showed `Raw [decoded gzip]`, yet the displayed text was still binary-looking. Pasting it into a text editor introduced `�` replacement characters and **destroyed some of the byte values**. Export the original bytes; do not copy/paste the garbled text.

For our installed mitmweb version, the following URL downloaded the selected flow's response body. The `FLOW_ID` is visible in the mitmweb address bar when you select the flow:

```text
http://127.0.0.1:8081/flows/FLOW_ID/response/content.data
```

Replace `FLOW_ID` with the selected flow's identifier. This endpoint worked in our setup; it is a mitmweb implementation detail and could change in another release. Save the downloaded body as `login-response.bin` in a **private** directory:

```bash
mkdir -p -m 700 ~/adt-private
mv ~/Downloads/YOUR_DOWNLOADED_FILENAME ~/adt-private/login-response.bin
chmod 600 ~/adt-private/login-response.bin
file ~/adt-private/login-response.bin
```

If `file` says `gzip compressed data`, that's expected. If it says XML/ASCII text, the client may have already decoded gzip. The companion helper handles **either** form. Do not upload the raw file to forums, GitHub issues, or public bug reports.

## 6. Discover the local camera endpoints safely

Download the companion `adc_local_test.py` script from this guide's files and put it alongside this README. It uses the Python standard library, does not contact ADT, and prints neither usernames nor passwords.

```bash
python3 adc_local_test.py ~/adt-private/login-response.bin list
```

In our capture, there were **three `<cli>` camera records containing `lre` attributes**. The important distinction is that `lre`, `l`, `p`, `UnitId`, and `SupportsWebRTC` are **XML attributes on camera records**, *not child elements*. Searching for `<lre>` finds nothing even when the credentials are present.

The records were nested in a top-level `<slnr>` document, under a `<cli>` section with a `<gdr>` branch. The actual camera records have an `lre` URL and separate `l` and `p` credential attributes. Their private IPs and high ports differed. The paths in our capture followed this form (this is deliberately **not a real credential**):

```text
rtsp://<user>:<password>@<camera-lan-ip>:<camera-high-port>/img/media.sav?stream=<stream-id>
```

The captured **HTTPS tunnel** high ports were in the `41925–41927` range, specific to the three cameras. For **standard RTSP/TCP**, we subsequently found that **port 554** accepted these same credentials (directly verified for the driveway). Do not confuse the two transports: the captured *high port* is not a normal RTSP/TCP port. The wizard defaults to direct RTSP port 554; the safe tester still lists the high ports for fallback work.

## 7. Bridge the camera's TLS tunnel locally with socat

**This is an optional fallback; try direct authenticated RTSP/TCP on port 554 first using the interactive wizard and Scrypted guide.**

This was the key transport discovery during our initial experiments. Running ordinary RTSP directly against the captured high port failed with an “invalid data” error. Replacing `rtsp://` with `rtsps://` also failed. FFmpeg's native `-rtsp_transport https` path reached a **self-signed/expired-camera-certificate verification** error in our build, even with `-tls_verify 0` supplied. We therefore used `socat` to terminate TLS locally.

In **Terminal 1**, start a relay for the first camera. Replace `CAMERA_LAN_IP` and `CAMERA_TLS_PORT` using the safe `list` output from §6:

```bash
socat -d -d \
  TCP4-LISTEN:8554,bind=127.0.0.1,reuseaddr,fork \
  OPENSSL:CAMERA_LAN_IP:CAMERA_TLS_PORT,verify=0
```

This means: **FFmpeg → local `127.0.0.1:8554` → `socat` → camera's TLS endpoint**. The relay passes the camera's authentication challenge and stream bytes; it does not need to know the username or password. `verify=0` is limited to this TLS connection, not a system-wide certificate setting. The loopback bind prevents other LAN clients from connecting to this relay directly.

**Important:** It is not a generic plain-RTSP server. The RTSP client must use HTTP tunneling on the local side, as in the next step. This is relevant only when using the fallback TLS relay; our Scrypted installation connects to standard port 554 directly.

## 8. Probe the camera, then play its live video

Leave the `socat` terminal open. In **Terminal 2**, probe camera `1` from the numbered list:

```bash
python3 adc_local_test.py ~/adt-private/login-response.bin probe \
  --index 1 --relay-port 8554
```

The helper rebuilds the authenticated URL locally, replacing only its host/port with `127.0.0.1:8554`. It calls FFprobe with the critical option `-rtsp_transport http`, preserving the original credentials, path, and stream query.

Success shows stream metadata. For the tested driveway camera, we observed:

```text
H.264 video — 1920 x 1080
PCM mu-law (G.711) audio
```

Metadata recognition by itself **does not prove video decoding**. Play the live picture too:

```bash
python3 adc_local_test.py ~/adt-private/login-response.bin play \
  --index 1 --relay-port 8554
```

Press **Q** in the FFplay window to close it. If live video appears, the camera is supplying real local media—not just an SDP description.

Repeat for the other cameras using additional terminals/relay ports:

```bash
# Terminal for camera 2 — replace placeholders
socat -d -d TCP4-LISTEN:8555,bind=127.0.0.1,reuseaddr,fork \
  OPENSSL:SECOND_CAMERA_IP:SECOND_CAMERA_TLS_PORT,verify=0

# Terminal for camera 3 — replace placeholders
socat -d -d TCP4-LISTEN:8556,bind=127.0.0.1,reuseaddr,fork \
  OPENSSL:THIRD_CAMERA_IP:THIRD_CAMERA_TLS_PORT,verify=0
```

Then run `probe` and `play` for camera indices `2` and `3`, with `--relay-port 8555` and `8556` respectively. **Use the order printed by the script; it need not be the same order as ours.** All three streams displayed successfully in our tests.

## 9. Fedora 45 H.264 playback fix

We initially got successful FFprobe metadata but a blank/failed FFplay stream with repeated:

```text
[libopenh264] DecodeFrame failed
```

Checking the codecs showed only Fedora's restricted `libopenh264` H.264 decoder:

```bash
rpm -q ffmpeg-free ffmpeg
ffmpeg -hide_banner -decoders | grep -Ei 'h264|openh264'
```

Our working solution was using **RPM Fusion's full FFmpeg build**, which includes the native H.264 decoder. If RPM Fusion Free is not enabled, it can be enabled on Fedora with:

```bash
sudo dnf install \
  https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
```

**Preview the transaction first** (do not blindly remove packages):

```bash
sudo dnf swap ffmpeg-free ffmpeg --allowerasing --assumeno
```

Only if the package transaction looks safe:

```bash
sudo dnf swap ffmpeg-free ffmpeg --allowerasing
ffmpeg -hide_banner -decoders | grep -Ei 'h264|openh264'
```

If DNF proposes uninstalling major desktop components or unrelated applications, stop and resolve dependencies before proceeding. After the switch, FFplay displayed our driveway video correctly.

## 10. Troubleshooting lessons

| Symptom | What we learned |
| --- | --- |
| mitmproxy onboarding page doesn't appear | Use an **explicit `http://` URL**; Safari may upgrade to HTTPS. Verify traffic appears in mitmweb first. |
| App reports network error | Test basic HTTP and HTTPS interception, proxy reachability, certificate trust, and possible app-specific pinning; do not assume the camera is at fault. |
| View-filter syntax errors | Filter visually by hostname/path or use the simpler plain-text filter. The filter/search inputs aren't interchangeable in every version. |
| Response looks like garbled binary | Save **original bytes**, rather than copying them as text; gzip decompress as needed. |
| `<lre>` search reports zero | Look for the **attribute** `lre` on a camera `<cli>` element, not an `<lre>` element. |
| `rtsp://` high port reports invalid data | The high port expects an **HTTPS RTSP tunnel**, not ordinary plaintext RTSP. |
| `rtsps://` fails | RTSP directly inside TLS is different from RTSP tunneled over HTTPS. |
| `-rtsp_transport https` says certificate failed | Use a **per-camera `socat` TLS relay** locally; do not change system-wide certificate trust. |
| FFprobe identifies H.264 but playback fails | Check the available H.264 decoder. Fedora `libopenh264` failed in this test; native `h264` worked. |
| FFprobe succeeds, but no picture | SDP/codec identification isn't proof that video frames can decode. Try FFplay and inspect decoding errors. |

## 11. Restore the phone's security configuration and clean up

After capturing the one useful response, you no longer need mitmproxy for local video testing. On the iPhone, **turn off the manual Wi-Fi proxy**, remove the mitmproxy-installed certificate/profile, disable its root-certificate trust by removing it, and **re-enable Lockdown Mode** if you turned it off. On Fedora, stop mitmweb, close any temporary firewall hole, and secure or remove the raw capture once you've finished testing:

```bash
sudo firewall-cmd --remove-port=8080/tcp  # only if you opened it earlier
```

Do not distribute `~/.mitmproxy/mitmproxy-ca.pem` (it contains the private CA key), the full decrypted response, or screenshots displaying account tokens. The example in this guide intentionally contains **no live credentials**.

## 12. What this does *not* prove yet

**We have proved local media transport, not total independence from ADT.** Open questions include whether the local credentials are stable, whether the cameras reconnect after an internet outage or reboot without cloud help, how on-demand streams behave over time, and whether any streams persist after subscription cancellation. **Do not cancel service based on this guide alone.** Test offline operation carefully, without disabling your security system's monitoring or emergency functionality.

**Scrypted direct RTSP is now confirmed** for a live driveway OC845 in Scrypted v0.147.0 on HAOS, and the basement/lake have been configured there. No extra restreaming service was required. **HomeKit, long-term stability, motion detection, Blue Iris, and subscription-independent operation remain unverified.** See the [Scrypted guide](docs/nvr-scrypted.md) for exact settings and limitations.

## References and credit

- **Original local RTSP discovery:** dppeak, *Cameras publish a local RTSP endpoint on the LAN, reachable without the cloud*, Aug 8, 2026 — <https://github.com/Omar-L/adc-video-bridge/issues/35>. This guide independently verifies the technique on OC845/RC845 ADT Control cameras and documents the seamless-login XML, audio, TLS bridge, and Fedora playback details.
- **mitmproxy certificate installation:** <https://docs.mitmproxy.org/stable/concepts-certificates/>
- **mitmproxy getting started:** <https://docs.mitmproxy.org/stable/overview/getting-started/>
- **FFmpeg RTSP transport options:** <https://ffmpeg.org/ffmpeg-protocols.html>
- **Apple Lockdown Mode restrictions:** <https://support.apple.com/en-us/105120>
- **Fedora/RPM Fusion multimedia package background:** <https://computingforgeeks.com/how-to-install-ffmpeg-on-fedora/>

*Please share findings, models tested, and errors, but redact any live RTSP URLs, passwords, API tokens, and account identifiers. Contributions from other firmware/app versions would be especially helpful.*
