# SmartStation System Requirements

This document captures the system-level requirements inferred from the current SmartStation implementation. The requirements are expressed at the feature level and do not prescribe the existing software module structure.

## 1. Station Orchestration

1.1 The system shall start and manage a set of interconnected runtime services required for SmartStation operation. The services shall support running as background services so that operation can continue after the terminal that started the system exits.

1.2 Before starting each service, the system shall detect whether that exact service instance is already running under the same SmartStation deployment and stop only those processes before continuing.

1.4 The system shall load station configuration from `config/station_params.yaml`.

1.5 The system shall support configuration of:
- MQTT broker IP address (`mqtt_broker_ip`)
- MQTT broker port (`mqtt_broker_port`)
- Web interface port (`web_port`)
- Registered devices and their display names (`devices`)

1.6 The system shall validate station configuration against a defined schema before service startup, including required fields, permitted types, and valid device definitions.

1.7 If configuration validation fails, the system shall refuse to start and provide a human-readable error message indicating the invalid field(s).

1.8 The system shall start a local MQTT broker process when configured, using a local broker implementation such as `mosquitto`.

1.9 The system shall start managed services in a defined order: configuration validation, MQTT broker, MQTT-to-ROS2 bridge, logger service, and web GUI service.

1.9 The system shall retry transient startup failures for broker and bridge services with a configurable retry count and backoff delay before failing startup.

1.10 If a managed service fails repeatedly after configured retries, the system shall fail startup and report a fatal error.

1.11 The system shall provide a health-check mechanism that verifies each managed service is alive and reporting healthy status.

1.12 The system shall monitor child service processes and, if any service exits unexpectedly, shut down the remaining services cleanly.

1.13 The system shall log all logging of all services/modules to a logging file.

## 2. MQTT-to-ROS2 Bridge

2.1 The system shall connect to an MQTT broker using configurable broker address and port.

2.2 The system shall subscribe to MQTT topics using a configurable set of topic filters rather than an unbounded wildcard subscription by default.

2.3 The system shall support subscribing to all topics (`#`) only when explicitly enabled in configuration and when the expected topic volume is manageable.

2.4 The system shall forward received MQTT messages to corresponding ROS2 topics with the same topic name.

2.5 The system shall publish forwarded messages as text payloads using a common message format (ROS2 `String`).

2.6 The system shall dynamically create ROS2 publishers for MQTT topics as they are discovered, subject to a configurable publisher limit.

2.7 The system shall tolerate non-JSON MQTT payloads by forwarding the raw string payload and logging invalid JSON payloads.

2.8 The system shall subscribe for each detected device to a ROS2 topic with the pattern `control/<device_id>`.

2.9 The system shall translate and forward each message detected on one of the control topics as MQTT message with the same topic.

2.10 The system shall support forwarding battery state-of-charge updates published by devices on MQTT topics with the pattern `device/<device_id>/battery_soc` to corresponding ROS2 topics with the same path.

2.11 The system shall avoid creating routing loops for topics matching the control pattern by preventing the same message from being forwarded back to its origin side.

## 3. Log Collection and Storage

3.1 The system shall discover and subscribe to ROS2 topics whose path begins with `log/`.

3.2 The system shall interpret log topic names using the pattern `log/<device_id>/<log_level>` where:
- `<device_id>` identifies the originating device
- `<log_level>` identifies the severity level (e.g., INFO, WARNING, ERROR)

3.3 The system shall parse log message payloads as JSON when possible and extract a `message` field; otherwise it shall store the raw text payload.

3.4 The system shall persist log entries to a local SQLite database.

3.5 The system shall capture and store the following fields for each log entry:
- timestamp (use a message-provided timestamp if available, otherwise use system receipt time)
- device identifier
- log level
- message text
- original topic

3.6 The system shall support the following log retrieval capabilities:
- retrieve logs filtered by device
- retrieve logs filtered by log level
- retrieve logs in date ranges
- retrieve paginated log results sorted by timestamp descending by default
- retrieve recent logs using a configurable “last N entries” or “last T time” query
- retrieve error and warning logs over a time window
- retrieve summaries (counts per level, per device)

3.7 The system shall automatically remove log entries older than a configurable retention period (default 30 days).

3.8 The system shall support exporting logs to CSV.

3.9 The system shall support clearing logs entirely and clearing logs for a specific device.

## 4. Web-Based User Interface

4.1 The system shall provide a web interface accessible on the configured web port.

4.2 The system shall render a home page that displays the latest values for configured sensors.

4.3 The system shall support a web socket endpoint that delivers live sensor updates to connected clients.

4.4 The system shall generate sensor configuration from registered devices and the sensor types defined in station configuration.

4.5 The system shall support the following sensor and device state types by default:
- Soil moisture
- Temperature
- Pressure
- Humidity
- Battery state of charge

4.6 The system shall define sensor topics using the pattern `sensor/<device_id>/sensor_<sensor_id>` and subscribe to those topics for live updates.

4.7 The system shall update and display the last known value for each sensor in the web UI.

4.8 The system shall provide a log browsing page that displays recent log entries from the log database.

4.9 The system shall serve static resources and rendered templates required by the web UI.

4.10 The system shall operate the web server concurrently with ROS2 subscriptions for sensor data.

4.11 The system shall show the timestamp for each sensor value when the last update was received.

4.12 The system shall provide a control browsing page that displays configured devices and allows selecting a device-level action such as Reboot or Soil Moisture re-configuration.

4.13 The system shall expose a web socket payload format that includes at minimum: device identifier, sensor identifier, value, and timestamp.

4.14 The system shall publish a message to ROS2 topics of the pattern `control/<device_id>` with the selected action encoded as a simple string payload.

4.15 The system shall display battery state of charge for each configured device on the device control page.

## 5. Device and Sensor Configuration

5.1 The system shall allow devices to be registered by an identifier and display name in station configuration.

5.2 The system shall use registered devices to derive sensor subscription configuration.

5.3 The system shall support multiple devices, each with an associated set of supported sensor types and device state metrics derived from registered device configuration.

5.4 The system shall treat the configured registered devices as the authoritative device set and require a service restart before changes to device registration are applied unless runtime device reload is explicitly supported.

## 6. Error Handling and Diagnostics

6.1 The system shall record and report errors when required binaries or services are unavailable.

6.2 The system shall log failures to connect to the MQTT broker, failures to create ROS2 publishers or subscriptions, and failures to load configuration.

6.3 The system shall distinguish transient connection failures from fatal startup errors and retry transient failures where appropriate.

6.4 The system shall handle service shutdown gracefully, terminating child processes when necessary.

## 7. Operational Assumptions

7.1 The system shall be deployed in an environment where the ROS2 runtime and tooling are installed and configured.

7.2 The system assumes the `mosquitto` executable is available in the PATH when a local MQTT broker is used.

7.3 The system assumes a station configuration file exists at a known path, which may be the default `config/station_params.yaml` or a path supplied at startup.

7.4 The system assumes a local SQLite database can be created in a writable directory, with the default location under `~/.smartstation/`.

7.5 The system shall allow overriding the default configuration file location and the SQLite data directory via startup arguments or environment variables.

## 8. Operational Security

8.1 The system shall bind the web interface explicitly to the localhost interface (`127.0.0.1` or `::1`) when operating in localhost-only mode.

8.2 The system shall assume the web interface is only exposed to localhost.

8.3 The system shall not require web authentication or HTTPS when the system is confined to localhost-only access.

8.4 The system shall still log failures to connect to MQTT or ROS2 services and report unexpected bridge connection issues.
