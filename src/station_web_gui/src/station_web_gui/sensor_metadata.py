from enum import IntEnum
from typing import Dict, List
from dataclasses import dataclass


class SensorType(IntEnum):
    SOIL = 1
    TEMP = 2
    PRESS = 3
    HUM = 4


@dataclass
class SensorMetadata:
    enum_id: int
    sensor_type: SensorType
    unit: str
    base_name: str


class SensorMetadataRegistry:
    SENSOR_METADATA: Dict[SensorType, SensorMetadata] = {
        SensorType.SOIL: SensorMetadata(1, SensorType.SOIL, "%", "Soil"),
        SensorType.TEMP: SensorMetadata(2, SensorType.TEMP, "C°", "Temperature"),
        SensorType.PRESS: SensorMetadata(3, SensorType.PRESS, "kPa", "Pressure"),
        SensorType.HUM: SensorMetadata(4, SensorType.HUM, "%", "Humidity"),
    }

    @classmethod
    def get_all_sensor_types(cls) -> List[SensorType]:
        return list(cls.SENSOR_METADATA.keys())

    @classmethod
    def generate_sensor_config(cls, device_id: str, device_display_name: str) -> List[Dict]:
        configs = []
        for sensor_type in cls.get_all_sensor_types():
            metadata = cls.SENSOR_METADATA[sensor_type]
            configs.append({
                "id": f"{device_id}_{metadata.base_name.lower()}",
                "topic": f"sensor/{device_id}/sensor_{metadata.enum_id}",
                "device_id": device_id,
                "device_name": device_display_name,
                "label": metadata.base_name,
                "unit": metadata.unit,
            })
        return configs
