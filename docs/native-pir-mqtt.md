# Optional, unverified native PIR → MQTT pilot (two OC845 cameras)

This optional **proof of concept has passed mocked-MQTT offline tests only; it has not been connected to a real broker in this project**. It does **not** change Scrypted, OpenCV, or HomeKit Secure Video. It can publish separately observed Sercomm OC845 PIR pulses to a locally reachable MQTT broker so Home Assistant can display them. **You do not need MQTT to use local RTSP, Scrypted, HKSV, or the standalone PIR monitor.** Do not expose a broker or make network/security changes solely to run an optional experiment. Do not use this as your sole security/motion reporting path.

## Why keep OpenCV in parallel?

The ADT OC845 Quick Installation Guide, section 7.1, states its PIR sensor has a **16 ft / 5 m detection range**, although the camera records a much wider outdoor scene. Distant activity such as cars on the street or a person far out in the grass may trigger image-based motion detection while remaining outside the reliable PIR area. The two methods are complementary. Reference: https://fccid.io/P27OC845/User-Manual/Users-Manual-4489631.pdf (printed page 18).

Our tested camera firmware `V1.0.01R53`: two OC845 units reported `0x03` PIR pulses via RTSP `padding=yes`. The indoor RC845 provides 32-byte RTP padding whose metadata declares 28 bytes plus 3 filler zeros; it **does not** include command `0x03` and the 13-byte `0x01` status remained zero during deliberate motion. The updated decoder accepts the trailing filler but returns PIR **unavailable**, not a false OFF result.

## Requirements

- Python 3.11+; existing repo files plus this update.
- Local Mosquitto MQTT broker accepting MQTT v3.1.1 over TCP port 1883, with username/password if configured.
- Optional `paho-mqtt` 2.x library in a virtual environment (core RTSP program remains standard-library only without MQTT).
- Home Assistant's MQTT integration with discovery enabled (normally enabled by default); **the broker add-on alone is not enough** to create entities.
- Existing captured ADT response file, outside Git. Keep it private.

## Install on Fedora Framework

```bash
cd ~/Downloads/adt-local-rtsp
python3 -m venv .venv
.venv/bin/python -m pip install 'paho-mqtt>=2.1,<3'
.venv/bin/python -m unittest discover -s tests -v
```

`.venv` is excluded by `.gitignore` already. No third-party library is loaded if you omit `--mqtt-config`.

## Create protected MQTT settings outside the repository

```bash
mkdir -p ~/.config/adt-local-rtsp
umask 077
touch ~/.config/adt-local-rtsp/mqtt.toml
chmod 600 ~/.config/adt-local-rtsp/mqtt.toml
nano ~/.config/adt-local-rtsp/mqtt.toml
```

Enter (replace the broker IP, username and password locally; **do not paste secrets into chat or the repository**):

```toml
[mqtt]
host = "192.168.1.100"  # PLACEHOLDER: replace with your own LAN-reachable broker IP
port = 1883
username = "YOUR_MQTT_USERNAME"
password = "YOUR_MQTT_PASSWORD"
```

If your broker accepts anonymous local clients, omit *both* `username` and `password`. The program refuses world-readable configurations and non-private IPv4 broker destinations. MQTT over port 1883 is **unencrypted**; only use on a trusted LAN, and do not expose the broker port publicly. Test that the host IP is the one reachable from your Framework laptop, not a HA add-on container IP.

## Test one camera at a time, without changing Scrypted

Driveway (15 minutes, with optional shorter `--duration 180` for your first test):

```bash
cd ~/Downloads/adt-local-rtsp
.venv/bin/python adc_motion_monitor.py \
  --capture ~/adt-private/login-response.bin \
  --camera CAMERA_LAN_IP --duration 900 --hold 5 --retries 1 \
  --mqtt-config ~/.config/adt-local-rtsp/mqtt.toml --name driveway
```

Lake (separate terminal/process, with unique name):

```bash
.venv/bin/python adc_motion_monitor.py \
  --capture ~/adt-private/login-response.bin \
  --camera OTHER_CAMERA_LAN_IP --duration 900 --hold 5 --retries 1 \
  --mqtt-config ~/.config/adt-local-rtsp/mqtt.toml --name lake
```

Don't run two processes **with the same `--name`** simultaneously: they would report to the same MQTT topics. Leave the basement RC845 on OpenCV; this release doesn't provide useful PIR values for it.

## Topics and Home Assistant

Each `--name` publishes retained MQTT v3.1.1 QoS 1 messages:

| Topic | Values | Purpose |
|---|---|---|
| `adt_local_rtsp/pir/driveway/state` | `ON` / `OFF` | 5-second-held motion |
| `adt_local_rtsp/pir/driveway/availability` | `online` / `offline` | Online **only after valid PIR metadata is observed** |
| `homeassistant/binary_sensor/adt_local_rtsp_driveway/config` | JSON | HA MQTT discovery |

The `lake` camera follows the same topic convention. HA entity IDs are assigned by Home Assistant (usually `binary_sensor.adt_driveway_pir_motion` and `binary_sensor.adt_lake_pir_motion`, but verify in the UI). The device name will be `ADT Driveway PIR` / `ADT Lake PIR`.

The publisher sets motion `OFF` and availability `offline` on startup, clean exit, RTSP disconnect, and after 20 seconds of previously observed PIR metadata starvation. MQTT's retained Last Will also marks availability offline if the MQTT connection drops unexpectedly. A reconnect requires a fresh valid PIR sample before returning online. Published motion values are **not** a safety or alarm guarantee.

The monitor still retrieves the full RTSP stream **over the network**, although it does not decode or store video. Running two monitor instances will add video-stream network traffic to both cameras, even if it reduces future video-analysis CPU work.

## Verification checklist

1. Run driveway pilot, trigger motion within 5–10 feet of the camera, and check that the command prints `MOTION ON` / `MOTION OFF`.
2. In Home Assistant, navigate to **Settings → Devices & services → MQTT** and look for the new discovered device. Confirm `Motion` changes to `on` and back to `off`.
3. Verify that stopping the pilot makes the HA entity **unavailable** (not falsely clear).
4. Compare MQTT transitions against Scrypted OpenCV and HKSV recordings, especially distant grass/road movement, in different light and weather. Keep OpenCV enabled throughout.
5. Only after several days of comparisons, decide whether to augment Scrypted's camera motion events with the native PIR topic. Simply creating a Home Assistant sensor does **not** make HKSV respond to it.

## Troubleshooting

- `No module named paho`: use `.venv/bin/python`, not system `python3`.
- Config `chmod 600` warning: put it outside the repo and restrict it to your user.
- MQTT timeout/refusal: confirm broker LAN address, port, account credentials, and HA Mosquitto listener settings. Do not paste passwords or broker logs with secrets.
- Home Assistant doesn't show device: confirm the **MQTT integration** is configured and discovery enabled. The MQTT add-on alone isn't sufficient.
- Sensor stays unavailable: check the monitor has actually logged PIR raw state changes. The RC845's metadata lacks a PIR record, so this is expected for RC845.
- Avoid converting MQTT signals into Scrypted HKSV triggers until the Scrypted MQTT and Custom Motion Sensor integration is separately verified for your installed Scrypted version.

Security: the original ADT response file includes reusable camera credentials; never commit, share, or print it. MQTT settings include another reusable password and should remain private. Do not set this up as a critical security or intrusion-alarm system.

**Example address warning:** all `CAMERA_LAN_IP` / `OTHER_CAMERA_LAN_IP` values are placeholders. Likewise, `192.168.1.100` is only an example broker address and may not exist on your network. The broker must already accept incoming LAN connections; Home Assistant's internal add-on hostname/socket alone will not be reachable from a separate laptop. Do **not** expose MQTT to the public internet. No MQTT connectivity was verified on our test installation.
