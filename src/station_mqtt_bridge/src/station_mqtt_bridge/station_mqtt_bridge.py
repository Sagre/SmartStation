#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String  # Or other message type as needed
import paho.mqtt.client as mqtt
import json
import threading
import time
from typing import Dict, Any

class MQTTtoROS2Bridge(Node):
    def __init__(self):
        super().__init__('station_mqtt_bridge')

        # ROS2 parameters for MQTT broker configuration
        self.declare_parameter('mqtt_broker_ip', '192.168.2.197')
        self.declare_parameter('mqtt_broker_port', 1883)

        self.mqtt_broker_ip = self.get_parameter('mqtt_broker_ip').value
        self.mqtt_broker_port = self.get_parameter('mqtt_broker_port').value
        self.mqtt_topic_subscriptions = {}
        self.qos = 0  # Quality of Service. 0, 1 or 2

        # Initialize MQTT client
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message

        # Start MQTT client in a separate thread
        self.mqtt_thread = threading.Thread(target=self.mqtt_loop, daemon=True)
        self.mqtt_thread.start()

        self.get_logger().info(
            f'MQTT to ROS2 Bridge started connecting to {self.mqtt_broker_ip}:{self.mqtt_broker_port}'
        )

    def mqtt_loop(self):
        try:
            self.mqtt_client.connect(self.mqtt_broker_ip, self.mqtt_broker_port, 60)
            self.mqtt_client.loop_forever()
        except Exception as e:
            self.get_logger().error(f"MQTT connection error: {e}")

    def on_connect(self, client, userdata, flags, rc):
        """Called when the MQTT client successfully connects."""
        if rc == 0:
            self.get_logger().info("Connected to MQTT broker")
            self.mqtt_client.subscribe("#", self.qos) # Subscribe to ALL topics (wildcard)
        else:
            self.get_logger().error(f"Failed to connect to MQTT broker, return code {rc}")

    def on_message(self, client, userdata, msg):
        """Called when an MQTT message is received."""
        topic = msg.topic
        payload_str = msg.payload.decode('utf-8')

        try:
            # Attempt to parse as JSON first
            payload_json: Dict[str, Any] = json.loads(payload_str)
            self.get_logger().info(f"Received MQTT message on topic '{topic}': {payload_json}")
            self.publish_to_ros2(topic, payload_str) #publish json string as it is
        except json.JSONDecodeError:
            # If not JSON, publish the raw string as is.
            self.get_logger().warn(f"Invalid JSON received on topic '{topic}': {payload_str}")
            self.publish_to_ros2(topic, payload_str) #publish it
        except Exception as e:
            self.get_logger().error(f"Error processing MQTT message on topic '{topic}': {e}")

    def publish_to_ros2(self, topic: str, message: str):
        """Publishes the received message to a ROS2 topic, creating publisher if necessary."""
        if topic not in self.mqtt_topic_subscriptions:
            try:
                self.get_logger().info(f"Creating ROS2 publisher for topic: '{topic}'")
                publisher = self.create_publisher(String, topic, 10)
                self.mqtt_topic_subscriptions[topic] = publisher
                self.get_logger().info(f"Created ROS2 publisher for topic: '{topic}'")
            except Exception as e:
                self.get_logger().error(f"Failed to create ROS2 publisher for topic '{topic}': {e}")
                return # Stop processing, since we can not create the publisher.

        try:
            msg = String()
            msg.data = message  # Publish the entire JSON/String as is
            self.mqtt_topic_subscriptions[topic].publish(msg)
            self.get_logger().debug(f"Published to ROS2 topic '{topic}': {message}")
        except Exception as e:
            self.get_logger().error(f"Failed to publish to ROS2 topic '{topic}': {e}")

    def destroy_node(self):
        """Destroys the node, and also stops the MQTT client."""
        self.get_logger().info("Shutting down MQTT to ROS2 bridge...")
        self.mqtt_client.disconnect()
        super().destroy_node()

def main(args=None):
    rclpy.init(args=args)
    station_mqtt_bridge = MQTTtoROS2Bridge()
    try:
        rclpy.spin(station_mqtt_bridge) # spin until interrupted
    except KeyboardInterrupt:
        pass
    finally:
        station_mqtt_bridge.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()