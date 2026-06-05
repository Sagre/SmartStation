import json
import os
import threading
import time
from collections import deque

import paho.mqtt.client as mqtt
import rclpy
import yaml
from rclpy.node import Node
from std_msgs.msg import String

try:
    from station_orchestrator.logging_config import get_logger
except ImportError:
    import logging
    import sys

    def get_logger(name: str):
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

DEFAULT_CONFIG = {
    'mqtt_broker_ip': '127.0.0.1',
    'mqtt_broker_port': 1883,
    'topic_filters': ['sensor/#', 'device/+/battery_soc', 'control/#', 'log/#'],
    'allow_all_topics': False,
    'publisher_limit': 200,
}


class MQTTROS2Bridge(Node):
    def __init__(self, config_path=None):
        self.logger = get_logger('smartstation.mqtt_bridge')

        super().__init__('mqtt_ros2_bridge')
        self.logger.info('Starting mqtt_ros2_bridge')
        self.config = DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    cfg = yaml.safe_load(f) or {}
                    self.config.update(cfg)
            except Exception as e:
                self.logger.warning(f'Failed to load config: {e}')

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_log = self._on_mqtt_log

        self._registered_publishers = {}
        self._pub_order = deque()
        self._publisher_limit = int(self.config.get('publisher_limit', 200))

        self._recent_from_mqtt = deque()
        self._recent_lock = threading.Lock()
        self._recent_ttl = 5.0

        self.mqtt_broker_ip = self.config['mqtt_broker_ip']
        self.mqtt_broker_port = int(self.config['mqtt_broker_port'])
        self.logger.info(f'Connecting to MQTT broker {self.mqtt_broker_ip}:{self.mqtt_broker_port}')
        self.mqtt_thread = threading.Thread(target=self._mqtt_loop, daemon=True)
        self.mqtt_thread.start()

        self._subscribe_control_topics()

    def _mqtt_loop(self):
        try:
            self.mqtt_client.connect(self.mqtt_broker_ip, self.mqtt_broker_port, 60)
            self.mqtt_client.loop_forever()
        except Exception as e:
            self.logger.error(f'MQTT connection error: {e}')

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.logger.info('MQTT connected successfully')
            if self.config.get('allow_all_topics'):
                client.subscribe('#')
                self.logger.info('Subscribed to all topics (#)')
            else:
                for topic_filter in self.config.get('topic_filters', []):
                    client.subscribe(topic_filter)
                    self.logger.info(f'Subscribed to topic filter: {topic_filter}')
        else:
            self.logger.error(f'MQTT connection failed with rc={rc}')

    def _on_mqtt_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.logger.warning(f'MQTT disconnected unexpectedly with rc={rc}')
        else:
            self.logger.info('MQTT disconnected')

    def _on_mqtt_log(self, client, userdata, level, buf):
        if level == mqtt.LogLevel.MQTT_LOG_ERR:
            self.logger.error(f'MQTT: {buf}')
        elif level == mqtt.LogLevel.MQTT_LOG_WARNING:
            self.logger.warning(f'MQTT: {buf}')
        elif level == mqtt.LogLevel.MQTT_LOG_DEBUG:
            self.logger.debug(f'MQTT: {buf}')
        elif level == mqtt.LogLevel.MQTT_LOG_INFO:
            self.logger.info(f'MQTT: {buf}')

    def _on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = msg.payload.decode('utf-8')
        except Exception:
            payload = str(msg.payload)

        self.logger.info(f'MQTT message received on {topic}: {payload}')

        try:
            json.loads(payload)
        except Exception:
            self.logger.warning(f'Non-JSON MQTT payload on {topic}: {payload}')

        pub = self._get_or_create_publisher(topic)
        if pub:
            message = String()
            message.data = payload
            pub.publish(message)
            self.logger.debug(f'Published to ROS2 topic {topic}')
        else:
            self.logger.warning(f'Failed to create publisher for topic {topic}')

        now = time.time()
        with self._recent_lock:
            self._recent_from_mqtt.append((topic, payload, now))
            while self._recent_from_mqtt and now - self._recent_from_mqtt[0][2] > self._recent_ttl:
                self._recent_from_mqtt.popleft()

    def _get_or_create_publisher(self, topic):
        if topic in self._registered_publishers:
            return self._registered_publishers[topic]
        if len(self._registered_publishers) >= self._publisher_limit:
            old = self._pub_order.popleft()
            self.logger.warning(f'Publisher limit reached, removing publisher for {old}')
            self._registered_publishers.pop(old, None)
        pub = self.create_publisher(String, topic, 10)
        self._registered_publishers[topic] = pub
        self._pub_order.append(topic)
        self.logger.info(f'Created ROS publisher for topic {topic}')
        return pub

    def create_ros_subscription(self, topic):
        def _cb(msg, t=topic):
            payload = msg.data
            with self._recent_lock:
                now = time.time()
                for tpc, pl, ts in list(self._recent_from_mqtt):
                    if now - ts > self._recent_ttl:
                        continue
                    if tpc == t and pl == payload:
                        return

            try:
                self.mqtt_client.publish(t, payload)
                self.logger.info(f'Forwarded to MQTT {t}: {payload}')
            except Exception as e:
                self.logger.error(f'Failed to publish to MQTT {t}: {e}')

        self.create_subscription(String, topic, _cb, 10)
        self.logger.info(f'Created ROS subscription for {topic} to forward to MQTT')

    def _subscribe_control_topics(self):
        devices = self.config.get('devices', {})
        if not isinstance(devices, dict):
            self.logger.warning('No devices configured for ROS control topic subscriptions')
            return
        for device_id in devices:
            if isinstance(device_id, str) and device_id:
                self.create_ros_subscription(f'control/{device_id}')


def main(argv=None):
    rclpy.init(args=argv)
    cwd = os.getcwd()
    cfg = os.path.join(cwd, 'config', 'station_params.yaml')
    node = MQTTROS2Bridge(config_path=cfg)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.logger.info('Shutting down mqtt_ros2_bridge')
        node.destroy_node()
        rclpy.shutdown()
