import rclpy
from rclpy.node import Node
from std_msgs.msg import String

import paho.mqtt.client as mqtt
import yaml
import os
import threading
import time
from collections import defaultdict, deque

DEFAULT_CONFIG = {
    'mqtt_broker_ip': '127.0.0.1',
    'mqtt_broker_port': 1883,
    'topic_filters': ['sensor/#', 'device/+/battery_soc', 'control/#', 'log/#'],
    'allow_all_topics': False,
    'publisher_limit': 200,
}


class MQTTROS2Bridge(Node):
    def __init__(self, config_path=None):
        super().__init__('mqtt_ros2_bridge')
        self.get_logger().info('Starting mqtt_ros2_bridge')
        self.config = DEFAULT_CONFIG.copy()
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    cfg = yaml.safe_load(f) or {}
                    self.config.update(cfg)
            except Exception as e:
                self.get_logger().warn(f'Failed to load config: {e}')

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        self._publishers = {}  # topic -> rclpy publisher
        self._pub_order = deque()  # track recently created publishers to enforce limit
        self._publisher_limit = int(self.config.get('publisher_limit', 200))

        # Use a cache to avoid routing loops: map of (topic,payload)->timestamp when forwarded from mqtt
        self._recent_from_mqtt = deque()
        self._recent_lock = threading.Lock()
        self._recent_ttl = 5.0

        # Start MQTT in a background thread
        broker = self.config['mqtt_broker_ip']
        port = int(self.config['mqtt_broker_port'])
        self.get_logger().info(f'Connecting to MQTT {broker}:{port}')
        self.mqtt_client.connect_async(broker, port)
        self.mqtt_thread = threading.Thread(target=self.mqtt_client.loop_forever, daemon=True)
        self.mqtt_thread.start()

        # Subscribe to ROS2 control topics
        # Note: we will dynamically create per-topic subscriptions when appropriate
        # Provide a generic subscription for demonstration (won't capture nested topics).
        # Users can extend create_ros_subscription to add specific topic subscriptions.

        # Dynamically subscribe to topic filters once connected
        self._subscribe_filters()

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        self.get_logger().info(f'MQTT connected rc={rc}')
        # subscribe to configured filters
        if self.config.get('allow_all_topics'):
            client.subscribe('#')
        else:
            for f in self.config.get('topic_filters', []):
                client.subscribe(f)

    def _on_mqtt_message(self, client, userdata, msg):
        topic = msg.topic
        try:
            payload = msg.payload.decode('utf-8')
        except Exception:
            payload = str(msg.payload)

        # Log invalid JSON attempts (best-effort)
        try:
            import json
            json.loads(payload)
            is_json = True
        except Exception:
            is_json = False
            self.get_logger().info(f'Non-JSON MQTT payload on {topic}')

        # Publish to ROS2 topic with same name
        pub = self._get_or_create_publisher(topic)
        if pub:
            m = String()
            m.data = payload
            pub.publish(m)

        # record for loop-avoidance
        now = time.time()
        with self._recent_lock:
            self._recent_from_mqtt.append((topic, payload, now))
            # prune old
            while self._recent_from_mqtt and now - self._recent_from_mqtt[0][2] > self._recent_ttl:
                self._recent_from_mqtt.popleft()

    def _get_or_create_publisher(self, topic):
        if topic in self._publishers:
            return self._publishers[topic]

        if len(self._publishers) >= self._publisher_limit:
            # remove oldest
            old = self._pub_order.popleft()
            self.get_logger().warn(f'Publisher limit reached, removing publisher for {old}')
            self._publishers.pop(old, None)

        ros_topic = topic
        pub = self.create_publisher(String, ros_topic, 10)
        self._publishers[topic] = pub
        self._pub_order.append(topic)
        self.get_logger().info(f'Created ROS publisher for topic {topic}')
        return pub

    def create_ros_subscription(self, topic):
        # create a subscription for a specific ROS2 topic so we can forward to MQTT
        def _cb(msg, t=topic):
            payload = msg.data
            # check recent_from_mqtt to avoid loops
            with self._recent_lock:
                now = time.time()
                for tpc, pl, ts in list(self._recent_from_mqtt):
                    if now - ts > self._recent_ttl:
                        continue
                    if tpc == t and pl == payload:
                        # originated from mqtt recently; skip forwarding
                        return

            # forward to MQTT
            try:
                self.mqtt_client.publish(t, payload)
            except Exception as e:
                self.get_logger().error(f'Failed to publish to MQTT {t}: {e}')

        # create subscription
        self.create_subscription(String, topic, _cb, 10)
        self.get_logger().info(f'Created ROS subscription for {topic} to forward to MQTT')

    def _subscribe_filters(self):
        # Placeholder. Subscriptions are primarily handled via MQTT side; ROS->MQTT subscriptions
        # can be created via `create_ros_subscription` when device/control topics are known.
        return


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
        node.get_logger().info('Shutting down mqtt_ros2_bridge')
        node.destroy_node()
        rclpy.shutdown()
