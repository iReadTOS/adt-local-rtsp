# Direct RTSP in Scrypted (Home Assistant OS)

**Tested November 15, 2026:** A live OC845 driveway video feed displayed through Scrypted **v0.147.0**, using the RTSP Camera plugin inside a Home Assistant OS add-on. The RC845 basement and second OC845 (lake) were subsequently added to Scrypted by the same user. Full audio, HomeKit, motion events, long-term operation, and independent live previews of both remaining cameras have **not** been documented yet.

**No restreamer, `socat`, MediaMTX, or FFmpeg command was required for the direct port-554 Scrypted feed.** The original captured `lre` URL used an *unusual, HTTPS-tunneled high port*, but the **same credentials** were accepted by **standard RTSP/TCP on port 554**. Only the driveway camera's direct port-554 FFprobe result and Scrypted preview are documented so far. Different firmware may behave differently.

## Export Scrypted camera settings

1. Capture your own ADT Control iOS `UberSeamlessLoginNew` login response by following the [README capture steps](../README.md#4-capture-the-adt-control-mobile-response). Keep the body (`.bin` gzip or XML) privately on your computer. **Never post it.**
2. Run the no-dependencies, interactive wizard:

   ```bash
   python3 adc_setup_wizard.py
   ```

   Or choose a file explicitly:

   ```bash
   python3 adc_setup_wizard.py --capture ~/adt-private/login-response.bin
   ```

3. Choose the camera by number, IP, comma-separated numbers, or `all`. The standard RTSP port defaults to **554**. Choose **Scrypted**, type `REVEAL` after reading the warning, and pick terminal display or a new private export file (0600).
4. The wizard produces these *categories* of settings. The example below uses **invented credentials** and a documentation-network IP; your real output will differ:

   ```text
   RTSP Stream URL: rtsp://192.0.2.8:554/img/media.sav?stream=example
   Username: exampleuser
   Password: EXAMPLE_ONLY_DO_NOT_USE
   ```

   Do not change or discard the camera-specific query parameters. The URL **without username/password** can still contain a sensitive stream token in its query.

## Configure Scrypted RTSP Camera plugin

1. Open the Scrypted Management Console from Home Assistant.
2. Install/open the **RTSP Camera** plugin.
3. Add a camera (e.g. `ADT Driveway`). In its settings, fill out the **Username**, **Password**, and **RTSP Stream URL** fields from the *same camera's* wizard output. Keep **No Audio** unchecked initially.
4. Save and open **Stream: Default** to verify a live picture. If preview fails, first check the IP, port 554, camera-specific path/query, and credentials. A metadata-only FFprobe success is *not* proof of playable frames.
5. Repeat for each camera. If the camera names seem wrong, compare the **IP addresses** in the URL with the intended device. We initially named a driveway-addressed stream `LAKE CAMERA` by mistake.

**Do not embed `user:pass@` in the RTSP Stream URL in Scrypted when its separate credential fields are available.** The RTSP plugin has had code paths that log raw stream URLs. Check logs before sharing any screenshots or bug reports.

## For Blue Iris and other NVRs

Choose the wizard's **Blue Iris / generic NVR** mode. It prints (or privately saves) the **complete authenticated standard RTSP URL** using the port 554 endpoint. Use the camera-specific path and query, not a guessed generic path. **We have not tested Blue Iris itself**; compatible authentication and port-554 behavior on other installations remain to be confirmed.

## Security, limitations and fallback

Direct port 554 usually carries **unencrypted** RTSP, including authentication exchanges and video. Restrict LAN access, do not forward port 554, and use a trusted network. Any saved `.bin` response or exported text file contains reusable access information; keep these outside the Git repository with restrictive permissions.

The *high port* in the original `lre` requires RTSP-over-HTTPS tunneling and is **not** a substitute for port 554. If standard RTSP on port 554 fails on another camera/firmware, see the [fallback `socat` TLS relay walkthrough](../README.md#7-bridge-the-cameras-tls-tunnel-locally-with-socat). We **do not** require MediaMTX for our confirmed Scrypted setup.

We have **not** established that any camera will function without internet or after an ADT subscription ends. Avoid disrupting a monitored security system while testing.
