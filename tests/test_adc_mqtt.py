"""Offline MQTT tests: fake broker client; never connects to a real broker."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from adc_mqtt import MQTTFailure, PIRPublisher, discovery_payload, read_mqtt_config


class FakeInfo:
    rc = 0
    def wait_for_publish(self, timeout=None):
        self.timeout = timeout
    def is_published(self):
        return True


class FakeClient:
    def __init__(self):
        self.records = []
        self.connected = False
        self.on_connect = None
        self.on_disconnect = None
        self.will = None
    def username_pw_set(self, username, password):
        self.auth = (username, password)
    def will_set(self, topic, payload, qos, retain):
        self.will = (topic, payload, qos, retain)
    def connect(self, host, port, keepalive):
        self.connected = True
        self.records.append(("connect", host, port))
    def loop_start(self):
        self.on_connect(self, None, None, 0, None)
    def publish(self, topic, payload, qos, retain):
        self.records.append((topic, payload, qos, retain))
        return FakeInfo()
    def disconnect(self):
        self.connected = False
    def loop_stop(self):
        pass


class MQTTTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "mqtt.toml"
        self.path.write_text('''[mqtt]
host = "192.168.1.11"
port = 1883
username = "mqttuser"
password = "not-a-real-password"
''')
        self.path.chmod(0o600)

    def test_config_permissions_and_no_secret_in_errors(self):
        self.assertEqual(read_mqtt_config(self.path)["port"], 1883)
        self.path.chmod(0o644)
        with self.assertRaisesRegex(MQTTFailure, "chmod 600"):
            read_mqtt_config(self.path)
        self.path.chmod(0o600)
        self.path.write_text('''[mqtt]
host = "8.8.8.8"
username = "mqttuser"
password = "not-a-real-password"
''')
        with self.assertRaises(MQTTFailure) as caught:
            read_mqtt_config(self.path)
        self.assertNotIn("not-a-real-password", str(caught.exception))

    def test_name_validation_and_discovery_topics(self):
        payload = discovery_payload("driveway", "OC845")
        self.assertEqual(payload["device_class"], "motion")
        self.assertEqual(payload["state_topic"], "adt_local_rtsp/pir/driveway/state")
        self.assertEqual(payload["availability_topic"], "adt_local_rtsp/pir/driveway/availability")
        with self.assertRaises(MQTTFailure):
            discovery_payload("../evil", "OC845")

    def test_connect_lwt_discovery_online_motion_and_shutdown(self):
        fake = FakeClient()
        publisher = PIRPublisher(self.path, "driveway", "OC845", client_factory=lambda: fake)
        publisher.start()
        self.assertEqual(fake.auth, ("mqttuser", "not-a-real-password"))
        self.assertEqual(fake.will, ("adt_local_rtsp/pir/driveway/availability", "offline", 1, True))
        self.assertIn(("adt_local_rtsp/pir/driveway/availability", "offline", 1, True), fake.records)
        self.assertIn(("adt_local_rtsp/pir/driveway/state", "OFF", 1, True), fake.records)
        discover = next(v for t, v, *_ in fake.records if t.endswith("/config"))
        self.assertEqual(json.loads(discover)["unique_id"], "adt_local_rtsp_driveway_motion")
        self.assertNotIn("not-a-real-password", discover)
        self.assertTrue(publisher.sample(False))
        self.assertTrue(publisher.sample(True))
        self.assertTrue(publisher.sample(True))
        publisher.unavailable()
        self.assertTrue(publisher.sample(False))
        publisher.close()
        states = [v for t, v, *_ in fake.records if t == "adt_local_rtsp/pir/driveway/state"]
        self.assertEqual(states, ["OFF", "OFF", "ON", "OFF", "OFF", "OFF"])
        avail = [v for t, v, *_ in fake.records if t == "adt_local_rtsp/pir/driveway/availability"]
        self.assertEqual(avail, ["offline", "online", "offline", "online", "offline"])
        self.assertFalse(fake.connected)

    def test_reconnect_requires_new_valid_sample(self):
        fake = FakeClient()
        pub = PIRPublisher(self.path, "lake", "OC845", client_factory=lambda: fake)
        pub.start()
        pub.sample(True)
        fake.on_disconnect(fake, None, None, 0, None)
        self.assertFalse(pub.sample(True))
        fake.on_connect(fake, None, None, 0, None)
        self.assertFalse(pub._online)
        pub.sample(True)
        self.assertTrue(pub._online)
        pub.close()


if __name__ == "__main__":
    unittest.main()
