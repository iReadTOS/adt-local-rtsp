# How-to: obtain local RTSP settings for your ADT cameras

**Purpose:** Start with cameras visible in your own ADT Control iOS account, capture your own login response, extract the local RTSP configuration, and connect to Scrypted or another NVR. **Direct RTSP/TCP on port 554 is the first method to try.** You do not need a TLS relay or MediaMTX for our verified Scrypted installation.

> These are instructions for cameras/accounts you **own or are authorized to administer**. The captured response contains **passwords, tokens and possibly account data**. Never upload it, paste it into a chat, or commit it to GitHub. No step requires resetting or unenrolling cameras. Whether operation continues after ADT cancellation or without internet is untested.

**Jump to:** [Prerequisites](#before-you-start) · [Capture the response](#step-1--capture-your-own-adt-control-login-response) · [Export settings](#step-3--run-the-wizard) · [Connect to Scrypted](#step-4--connect-to-scrypted-or-another-nvr) · [Cleanup](#step-5--remove-temporary-interception-settings) · [Troubleshooting](#common-problems)

## Before you start

You need:

- An **ADT Control iOS** app session signed into an account allowed to view the cameras. Other Alarm.com apps may use different requests; the same steps have **not** been verified on all apps.
- An iPhone and a computer on the same reachable LAN as one another. Our actual walkthrough used **Fedora 45**.
- `mitmproxy` / `mitmweb` on that computer to capture **your own** app session.
- Python 3.11+ for the wizard (standard library only). Optional `ffprobe` for a connectivity test.
- The [repository files](../README.md#scripts) on your computer. You can clone the public repository (skip this if you already have a checkout):

  ```bash
  cd ~/Downloads
  git clone https://github.com/iReadTOS/adt-local-rtsp.git
  ```

**Security preparation:** Only proxy traffic from a device you control. Avoid unrelated websites while interception is active. If your iPhone uses Lockdown Mode, a separate test phone is preferable; otherwise restoring Lockdown Mode afterward is essential. Do **not** expose the mitmproxy console or proxy to the internet.

## Step 1 — Capture your own ADT Control login response

### 1A. Start mitmweb on Fedora

```bash
sudo dnf install uv
uv tool install mitmproxy
ip -4 addr
```

Find the computer's LAN IPv4 address and substitute it everywhere below for `COMPUTER_LAN_IP` (the text is a placeholder, not a literal hostname).

```bash
~/.local/bin/mitmweb \
  --listen-host COMPUTER_LAN_IP \
  --listen-port 8080 \
  --set web_host=127.0.0.1 \
  --set web_port=8081
```

Open **`http://127.0.0.1:8081` on the Fedora computer** to view the intercepted traffic. If Fedora's firewall blocks the iPhone, temporarily allow the proxy port in the current active zone:

```bash
sudo firewall-cmd --add-port=8080/tcp
```

Do not router-port-forward 8080 or 8081. The web interface stays on loopback (`127.0.0.1`).

### 1B. Route your iPhone through the proxy

On the iPhone, go to **Settings → Wi-Fi → (i) for the current network → Configure Proxy → Manual**. Set:

- **Server:** `COMPUTER_LAN_IP` (the computer's actual LAN address)
- **Port:** `8080`
- **Authentication:** Off

Open Safari and navigate explicitly to **`http://mitm.it`** (*http*, not *https*). Follow mitmproxy's iOS certificate instructions. Install the profile under **Settings → General → VPN & Device Management** and enable certificate trust under **Settings → General → About → Certificate Trust Settings**.

In our capture, the default onboarding page was inconsistent. An alternative was restarting mitmweb with `--set onboarding_host=example.com` and manually loading `http://example.com`. This is version-specific troubleshooting, not the normal path. If Safari silently upgrades the URL to HTTPS, type `http://` explicitly.

If Lockdown Mode prevents profile installation, prefer another test device. If you temporarily turn it off, **restore it after Step 5**.

### 1C. Find the response

Verify a normal HTTPS page loads through the proxy **and appears in mitmweb**. Then open **ADT Control** and view a camera. Look for POST requests to:

```text
https://adt-ios-mobile.alarm.com/MobileServlet/SubmitRequest.aspx
```

Inspect their **Request** form data. The action that contained our camera records was:

```text
Action = UberSeamlessLoginNew
```

The earlier community research reported `UberLoginNew` for another app/session; investigate either action if present. **Not every response contains the same camera metadata**, even with a matching action. You may need to inspect several relevant responses from an authorized session. Do not publish intercepted requests/responses.

## Step 2 — Save the response body as bytes (not copied text)

Our useful response was gzip-compressed XML, with headers including `Content-Encoding: gzip`, and was sometimes displayed as binary-looking text. **Do not paste those characters into an editor.** Replacement symbols (`�`) corrupt the file.

In the version of mitmweb used in our experiment, the selected flow's ID appeared in the web address. We downloaded its **response body** using:

```text
http://127.0.0.1:8081/flows/FLOW_ID/response/content.data
```

Replace `FLOW_ID` with the actual ID from your own capture. **This is an observed mitmweb implementation detail**, not a stable promise for future versions. Save the downloaded file privately; substitute its real filename below:

```bash
mkdir -p -m 700 ~/adt-private
mv ~/Downloads/YOUR_DOWNLOADED_FILENAME ~/adt-private/login-response.bin
chmod 600 ~/adt-private/login-response.bin
file ~/adt-private/login-response.bin
```

A `gzip compressed data` response is expected; already-decoded XML also works. The wizard recognizes both formats. The capture may contain data for *more than one camera and other account/device metadata*; keep the entire file private and out of the Git repository.

## Step 3 — Run the wizard

Navigate to your local repository checkout and launch it:

```bash
cd ~/Downloads/adt-local-rtsp
python3 adc_setup_wizard.py
```

Or point straight to your saved response:

```bash
python3 adc_setup_wizard.py --capture ~/adt-private/login-response.bin
```

The wizard prompts for:

1. **File:** choose a detected XML/gzip capture or type a different path. **It does not intercept the app or download credentials for you.**
2. **Camera(s):** select `all`, an index (`1`), a comma-separated list (`1,3`), or an exact camera IP.
3. **Camera address:** retain the captured LAN IP unless you know it changed; optional overrides accept private IPv4 addresses.
4. **Standard RTSP port:** start with **554**. The original `lre` high port uses a *different* HTTPS tunnel and **must not** be pasted here as a standard RTSP port.
5. **Output:** Safe summary (default), Scrypted (URL plus separate username/password), NVR (complete authenticated RTSP URL), or original high-port URL (advanced diagnostics).

Start with **Safe summary** to confirm the correct cameras were detected. If you choose a sensitive mode, read the warning and type `REVEAL`. You can optionally test the direct port with `ffprobe` before revealing the configuration. Then choose to display the settings in your **local terminal** or save them to a **new private `0600` file** outside Git. The wizard will not overwrite a file. A stored password or URL may grant access to live video; protect and eventually remove the export.

The Scrypted format resembles the following **invented example**:

```text
RTSP Stream URL: rtsp://192.0.2.8:554/img/media.sav?stream=example
Username: exampleuser
Password: EXAMPLE_ONLY_DO_NOT_USE
```

**Do not remove or invent query parameters.** Even without `user:password@`, the camera-specific RTSP URL's query may be sensitive.

## Step 4 — Connect to Scrypted or another NVR

### Scrypted on Home Assistant OS

1. Open your **Scrypted Management Console** from Home Assistant OS.
2. Open/install the **RTSP Camera** plugin, then add a camera.
3. Copy the same camera's **RTSP Stream URL**, **Username** and **Password** into their *separate* settings. Leave **No Audio** unchecked initially.
4. Save and test the live preview. Name the device using the camera/IP you actually selected.
5. Repeat for additional cameras. The same account capture can contain several different camera entries with **different credentials and stream queries**.

We verified a live Scrypted preview for one **OC845** camera under **Scrypted v0.147.0 on HAOS**; the RC845 and other OC845 were subsequently added. Scrypted/OpenCV subsequently triggered real HomeKit Secure Video clips viewed in Apple Home; per-camera audio, recording behavior and long-term stability remain incompletely characterized. See [the Scrypted / NVR guide](nvr-scrypted.md) for detailed notes.

### Blue Iris or another NVR

Choose the wizard's **Blue Iris / generic NVR** mode if the application expects a full URL with credentials. Use the reported *direct port-554* URL and configure **RTSP over TCP** if your NVR offers that choice. **Blue Iris was not tested** in our installation, so its individual settings cannot be guaranteed. The full URL must remain private.

### Verify locally with FFprobe (optional)

The wizard offers to run FFprobe against the selected camera using standard RTSP/TCP on port 554. This checks authentication and stream metadata, but **metadata alone does not guarantee playable video**; check the actual NVR/FFplay picture too. FFprobe receives credentials in a process argument, which can be visible to other local processes on the computer.

## Step 5 — Remove temporary interception settings

Once the capture is saved and you can configure cameras, **you no longer need mitmproxy** for ordinary local streaming. On the iPhone, disable the manual Wi-Fi proxy, remove the mitmproxy certificate/profile and its trust, and re-enable Lockdown Mode if you had disabled it. Stop mitmweb on Fedora. If you opened a temporary firewall hole, remove it:

```bash
sudo firewall-cmd --remove-port=8080/tcp
```

Keep or securely delete the private response file as appropriate for your needs. Never publish `~/.mitmproxy/mitmproxy-ca.pem` (it contains the private CA key), account login responses, or credential-bearing URLs.

## Common problems

| Symptom | What to check |
| --- | --- |
| `bash: from: command not found` | You pasted a Python snippet directly into Bash. Run a complete `python3` script or `python3 - <<'PY'` ... `PY` block. The wizard is simply `python3 adc_setup_wizard.py`. |
| iPhone cannot load `mitm.it` | Check both devices' LAN reachability, the manual proxy host/port, temporary firewall rules, and an **explicit `http://` URL**. |
| ADT Control app reports an error | Confirm proxy connectivity and the certificate trust settings; app builds may behave differently. |
| Downloaded response appears garbled | Export **raw response bytes**, not text copied from the viewer; the script supports gzip and plain XML. |
| Wizard reports no `lre` cameras | Try another relevant authenticated login response. The camera data is in **XML attributes**, not `<lre>` elements. |
| Direct RTSP/TCP `:554` won't connect or authenticate | Verify the actual IP, credentials and exact path/query, then test with FFprobe. Some models or firmware may not expose this port. |
| Direct RTSP fails but a captured high port exists | That high port may use **RTSP-over-HTTPS**. Follow the [optional TLS relay fallback](TLS_FALLBACK.md), not a blind RTSP port substitution. |
| FFprobe returns codecs but no visible picture | Check FFmpeg's decoder support, and distinguish SDP discovery from playable frames. See [Fedora playback troubleshooting](TLS_FALLBACK.md#fedora-45-h264-decoder-issue). |

## Further reading

- [Investigation and technical findings](DISCOVERY.md) — the discovery process and failed experiments, **not required for setup**
- [Optional TLS tunnel fallback](TLS_FALLBACK.md) — separate procedure when the simpler RTSP connection fails
- [Compatibility](../COMPATIBILITY.md) — tested models and community reporting
- [Security](../SECURITY.md) — protecting camera credentials and capture files
