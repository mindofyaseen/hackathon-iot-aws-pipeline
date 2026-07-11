import boto3
import json
import time
import random
import argparse
from datetime import datetime, timezone

IOT_ENDPOINT = "a189zpdu3uyewq-ats.iot.us-east-1.amazonaws.com"
REGION = "us-east-1"
MQTT_TOPIC_PREFIX = "iot/sensors"
PUBLISH_INTERVAL = 5

DEVICES = [
    {"device_id": "device_001", "base_lat": 33.7215, "base_long": 73.0433},
    {"device_id": "device_002", "base_lat": 33.6844, "base_long": 73.0479},
    {"device_id": "device_003", "base_lat": 33.7294, "base_long": 73.0931},
    {"device_id": "device_004", "base_lat": 33.6007, "base_long": 73.0679},
    {"device_id": "device_005", "base_lat": 33.7680, "base_long": 72.8411},
]


def build_payload(device: dict) -> dict:
    return {
        "device_id": device["device_id"],
        "lat": round(device["base_lat"] + random.uniform(-0.005, 0.005), 6),
        "long": round(device["base_long"] + random.uniform(-0.005, 0.005), 6),
        "temperature": round(random.uniform(18.0, 42.0), 2),
        "aqi": round(random.uniform(20.0, 300.0), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run(iterations: int = 0):
    client = boto3.client(
        "iot-data",
        region_name=REGION,
        endpoint_url=f"https://{IOT_ENDPOINT}",
    )

    print(f"Starting IoT simulator -- {len(DEVICES)} devices, interval {PUBLISH_INTERVAL}s")
    print(f"Endpoint: {IOT_ENDPOINT}")
    print("Press Ctrl+C to stop.\n")

    count = 0
    while True:
        for device in DEVICES:
            payload = build_payload(device)
            topic = f"{MQTT_TOPIC_PREFIX}/{device['device_id']}"
            client.publish(
                topic=topic,
                qos=1,
                payload=json.dumps(payload),
            )
            print(f"[{payload['timestamp']}] {device['device_id']} -> {topic} | aqi={payload['aqi']} temp={payload['temperature']}")

        count += 1
        if iterations and count >= iterations:
            print(f"\nDone. Published {count} rounds x {len(DEVICES)} devices = {count * len(DEVICES)} messages.")
            break

        time.sleep(PUBLISH_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="IoT sensor simulator")
    parser.add_argument("--iterations", type=int, default=0, help="Number of rounds (0 = infinite)")
    args = parser.parse_args()
    run(iterations=args.iterations)
