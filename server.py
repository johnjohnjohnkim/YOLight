from socket import *
import json

import control

UDP_IP = "239.255.255.250" # Govee multicast group address
SEND_PORT = 4001    # Devices listen here for commands
LISTEN_PORT = 4002  # Devices reply here

devices = [] # Populated by discover_devices()


def discover_devices():
    """Broadcast a scan request and collect every Govee device that replies."""
    print("Scanning for Govee devices...")

    sendSocket = socket(AF_INET, SOCK_DGRAM)
    listenSocket = socket(AF_INET, SOCK_DGRAM)
    listenSocket.bind(("", LISTEN_PORT))
    listenSocket.settimeout(240) # Stop scanning after 4 minutes of silence

    scan_msg = json.dumps({
        "msg": {
            "cmd": "scan",
            "data": {"account_topic": "reserve"}
        }
    }).encode()

    sendSocket.sendto(scan_msg, (UDP_IP, SEND_PORT))

    devices.clear()
    while True:
        try:
            data, addr = listenSocket.recvfrom(1024)
            response = json.loads(data.decode())
            devices.append(response["msg"]["data"])
        except timeout: # No more replies coming in
            print(f"Done scanning. Found {len(devices)} device(s).")
            for device in devices:
                print(f"  - {device.get('sku', 'unknown model')} at {device['ip']}")
            break

    sendSocket.close()
    listenSocket.close()
    return devices


def turn_lights_on():
    print(f"Turning lights on ({len(devices)} device(s))")
    for device in devices:
        control.send_turn_command(device["ip"], True)


def turn_lights_off():
    print(f"Turning lights off ({len(devices)} device(s))")
    for device in devices:
        control.send_turn_command(device["ip"], False)

if __name__ == "__main__":
    discover_devices()