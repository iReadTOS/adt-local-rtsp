"""Opt-in MQTT v3.1.1 publishing for native Sercomm PIR research.

Requires paho-mqtt>=2.0 only when MQTT is enabled. The broker is local,
credentials come from a protected TOML file, and no camera data is uploaded.
"""

import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import time
import tomllib


class MQTTFailure(Exception):
    """Safe MQTT errors that never include secrets."""


def read_mqtt_config(path):
    """Read protected TOML (host, port, username, password)."""
    path = Path(path).expanduser()
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise MQTTFailure("MQTT config must be a regular file readable only by its owner (chmod 600)")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise MQTTFailure("MQTT config must belong to the current user")
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    config = document.get("mqtt")
    if not isinstance(config, dict):
        raise MQTTFailure("MQTT config missing [mqtt] section")
    from adc_motion_monitor import private_camera_host
    host = config.get("host", "")
    port = config.get("port", 1883)
    username = config.get("username", "")
    password = config.get("password", "")
    if not isinstance(host, str) or not private_camera_host(host):
        raise MQTTFailure("MQTT host must be a private RFC1918 IPv4 address")
    if type(port) is not int or not 1 <= port <= 65535:
        raise MQTTFailure("MQTT port must be between 1 and 65535")
    if not all(isinstance(v, str) for v in (username, password)):
        raise MQTTFailure("MQTT username and password must be strings")
    if bool(username) != bool(password):
        raise MQTTFailure("Provide both MQTT username and password, or neither")
    return {"host": host, "port": port, "username": username, "password": password}


def validate_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", name):
        raise MQTTFailure("--name must be 1-32 lowercase letters/numbers, starting with a letter")
    return name


def discovery_payload(name, model):
    """A stable Home Assistant MQTT binary_sensor per user-selected camera name."""
    validate_name(name)
    prefix = f"adt_local_rtsp/pir/{name}"
    return {
        "name": "Motion",
        "unique_id": f"adt_local_rtsp_{name}_motion",
        "device_class": "motion",
        "state_topic": f"{prefix}/state",
        "availability_topic": f"{prefix}/availability",
        "payload_on": "ON",
        "payload_off": "OFF",
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": {
            "identifiers": [f"adt_local_rtsp_{name}"],
            "name": f"ADT {name.replace('_', ' ').replace('-', ' ').title()} PIR",
            "manufacturer": "Sercomm / ADT",
            "model": str(model)[:80],
        },
    }


class PIRPublisher:
    """MQTT publisher with retained state, discovery, and LWT availability.

    A valid PIR metadata sample is required before advertising online. On a
    broken RTSP feed or no PIR samples for a while, the sensor goes offline.
    """

    def __init__(self, path, name, model, client_factory=None):
        self.config = read_mqtt_config(path)
        self.name = validate_name(name)
        self.discovery = discovery_payload(name, model)
        self.topic = f"adt_local_rtsp/pir/{name}"
        self.client_factory = client_factory
        self.client = None
        self._connected = threading.Event()
        self._online = False
        self._last_state = None
        self._lock = threading.RLock()

    def _new_client(self):
        if self.client_factory is not None:
            return self.client_factory()
        try:
            from paho.mqtt import client as mqtt
        except ImportError as exc:
            raise MQTTFailure("MQTT publishing requires paho-mqtt>=2.0 (install in a virtual environment)") from exc
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"adt-pir-{self.name}-{secrets.token_hex(4)}",
            protocol=mqtt.MQTTv311,
        )

    def _publish(self, topic, value, *, retain=True):
        if not self._connected.is_set():
            raise MQTTFailure("MQTT broker connection unavailable")
        try:
            info = self.client.publish(topic, value, qos=1, retain=retain)
            if info.rc != 0:
                raise MQTTFailure("MQTT publish was not accepted by the client")
            return info
        except (OSError, ValueError) as exc:
            raise MQTTFailure("MQTT publish failed") from exc

    def _on_connect(self, _client, _userdata, _flags, reason_code, _properties):
        with self._lock:
            if reason_code != 0:
                self._connected.clear()
                return
            self._online = False
            self._last_state = None
            self._connected.set()
            # No PIR data yet: don't advertise a falsely healthy sensor.
            self._publish(f"{self.topic}/state", "OFF")
            self._publish(f"{self.topic}/availability", "offline")
            self._publish(
                f"homeassistant/binary_sensor/adt_local_rtsp_{self.name}/config",
                json.dumps(self.discovery, separators=(",", ":")),
            )

    def _on_disconnect(self, _client, _userdata, _flags, _reason_code, _properties):
        with self._lock:
            self._connected.clear()
            self._online = False
            self._last_state = None

    def start(self, timeout=8):
        self.client = self._new_client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        if self.config["username"]:
            self.client.username_pw_set(self.config["username"], self.config["password"])
        self.client.will_set(f"{self.topic}/availability", "offline", qos=1, retain=True)
        try:
            self.client.connect(self.config["host"], self.config["port"], keepalive=30)
            self.client.loop_start()
        except (OSError, ValueError) as exc:
            raise MQTTFailure(f"Could not connect to local MQTT broker ({type(exc).__name__})") from exc
        if not self._connected.wait(timeout):
            self.close()
            raise MQTTFailure("MQTT broker refused the connection or timed out")

    def sample(self, active):
        """Mark a validated PIR sample and report motion only on state change."""
        with self._lock:
            if not self._connected.is_set():
                return False
            state = "ON" if active else "OFF"
            if self._last_state != state:
                self._publish(f"{self.topic}/state", state)
                self._last_state = state
            if not self._online:
                self._publish(f"{self.topic}/availability", "online")
                self._online = True
            return True

    def unavailable(self):
        """Called on RTSP loss or metadata starvation; fail safely."""
        with self._lock:
            info = None
            if self._connected.is_set():
                self._publish(f"{self.topic}/state", "OFF")
                info = self._publish(f"{self.topic}/availability", "offline")
            self._last_state = None
            self._online = False
            return info

    def close(self):
        if self.client is None:
            return
        try:
            info = self.unavailable()
            if info is not None:
                # Flush the retained offline state before a clean MQTT
                # DISCONNECT (a clean shutdown does not fire the LWT).
                info.wait_for_publish(timeout=3)
                if not info.is_published():
                    raise MQTTFailure("MQTT offline state was not acknowledged")
        finally:
            try:
                self.client.disconnect()
            finally:
                self.client.loop_stop()
                self.client = None
                self._connected.clear()
