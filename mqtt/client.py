import json
import threading
from typing import Dict, Any, Callable, List, Optional
try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False

class StationMQTTClient:
    """
    MQTT client for Polar Station telemetry broadcasting.
    Supports native Mosquitto broker (localhost:1883) with transparent
    in-memory pub-sub fallback so external MQTT brokers are strictly optional.
    
    Topics:
    - station/solar
    - station/wind
    - station/battery
    - station/load
    - station/weather
    - station/ai
    - station/status
    - station/alerts
    """
    def __init__(self, host: str = "localhost", port: int = 1883):
        self.host = host
        self.port = port
        self.is_connected = False
        self.local_subscriptions: Dict[str, List[Callable[[str, Dict[str, Any]], None]]] = {}
        self.client = None
        self._lock = threading.Lock()
        
        if PAHO_AVAILABLE:
            try:
                self.client = mqtt.Client(client_id="aurora_polar_station")
                self.client.on_connect = self._on_connect
                self.client.on_disconnect = self._on_disconnect
                # Non-blocking attempt with low timeout
                self.client.connect_async(self.host, self.port, keepalive=30)
                self.client.loop_start()
            except Exception as e:
                print(f"[MQTT] No Mosquitto broker reachable at {self.host}:{self.port} ({e}). Operating in Local In-Memory Fallback mode.")
                self.client = None

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            print(f"[MQTT] Connected to Mosquitto Broker on {self.host}:{self.port}")
        else:
            self.is_connected = False

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False

    def subscribe(self, topic: str, callback: Callable[[str, Dict[str, Any]], None]):
        with self._lock:
            if topic not in self.local_subscriptions:
                self.local_subscriptions[topic] = []
            self.local_subscriptions[topic].append(callback)
            if self.is_connected and self.client:
                self.client.subscribe(topic)

    def publish(self, topic: str, payload: Dict[str, Any]):
        """Publishes to MQTT broker and triggers local in-memory listeners."""
        json_data = json.dumps(payload)
        
        # 1. Publish to physical broker if active
        if self.is_connected and self.client:
            try:
                self.client.publish(topic, json_data)
            except Exception:
                pass
                
        # 2. Local in-memory pub-sub dispatcher
        with self._lock:
            for sub_topic, callbacks in self.local_subscriptions.items():
                if sub_topic == "#" or sub_topic == topic or (sub_topic.endswith("/#") and topic.startswith(sub_topic[:-2])):
                    for cb in callbacks:
                        try:
                            cb(topic, payload)
                        except Exception:
                            pass

    def publish_telemetry(self, telemetry: Dict[str, Any]):
        """Broadcasts granular station updates across specialized MQTT topics."""
        self.publish("station/solar", {
            "power_kw": telemetry.get("solar_power_kw"),
            "irradiance": telemetry.get("solar_irradiance_w_m2")
        })
        self.publish("station/wind", {
            "power_kw": telemetry.get("wind_power_kw"),
            "speed_m_s": telemetry.get("wind_speed_m_s")
        })
        self.publish("station/battery", {
            "soc": telemetry.get("battery_soc_pct"),
            "power_kw": telemetry.get("battery_power_kw"),
            "temp_c": telemetry.get("battery_temperature_c")
        })
        self.publish("station/load", {
            "total_kw": telemetry.get("total_station_load_kw"),
            "critical_kw": telemetry.get("critical_load_kw"),
            "flexible_kw": telemetry.get("flexible_load_kw")
        })
        self.publish("station/weather", {
            "temp_c": telemetry.get("temperature_c"),
            "condition": telemetry.get("weather_condition")
        })
        self.publish("station/ai", {
            "action": telemetry.get("ai_action_name"),
            "reason": telemetry.get("ai_action_reason"),
            "reward": telemetry.get("ai_reward")
        })
        self.publish("station/status", telemetry)

    def close(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
