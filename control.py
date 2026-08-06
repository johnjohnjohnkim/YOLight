# Low-level Govee LAN API client. Unlike server.py (which handles device
# discovery over multicast), this module sends unicast UDP commands directly
# to a single device's known IP address, e.g. turning it on/off.

from socket import socket, AF_INET, SOCK_DGRAM
import json

CONTROL_PORT = 4003 # Devices listen here for direct on/off/color commands


def send_turn_command(ip, on: bool):
    """Send a Govee LAN API 'turn' command to a single device."""
    msg = json.dumps({
        "msg": {
            "cmd": "turn",
            "data": {"value": 1 if on else 0}
        }
    }).encode()

    sock = socket(AF_INET, SOCK_DGRAM)
    sock.sendto(msg, (ip, CONTROL_PORT))
    sock.close()
