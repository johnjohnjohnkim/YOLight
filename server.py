from socket import *
import json

import control
from config import env

UDP_IP = "239.255.255.250" # Govee multicast group address
SEND_PORT = 4001    # Devices listen here for commands
LISTEN_PORT = 4002  # Devices reply to the multicast group on this port

# Local IP of the interface on the SAME network as the Govee devices. Set
# explicitly so multicast doesn't leave via a VPN/WSL/Hyper-V adapter on Windows.
LOCAL_IP = env.IP_ADDR

devices = [] # Populated by discover_devices()


def discover_devices():
    """Broadcast a scan request and collect every Govee device that replies."""
    print("Scanning for Govee devices...")

    # Listen socket must JOIN the multicast group to hear device replies.
    listenSocket = socket(AF_INET, SOCK_DGRAM)
    listenSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    listenSocket.bind(("", LISTEN_PORT))
    mreq = inet_aton(UDP_IP) + inet_aton(LOCAL_IP)
    listenSocket.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
    listenSocket.settimeout(3) # Stop scanning after a few seconds of silence

    # Send socket: pin the outgoing interface for multicast.
    sendSocket = socket(AF_INET, SOCK_DGRAM)
    sendSocket.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, inet_aton(LOCAL_IP))
    sendSocket.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 2)

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
            device = response["msg"]["data"]
            devices.append(device)
            print(f"  + Found {device.get('sku', 'unknown model')} at {device['ip']}")
        except timeout: # No more replies coming in
            print(f"Done scanning. Found {len(devices)} device(s).")
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