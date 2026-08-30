# Govee light control. Primary channel is Govee's cloud HTTP API
# (openapi.api.govee.com); if a cloud request fails to connect, falls back
# to direct LAN control via the Govee LAN API (multicast discovery +
# control.py). tracker.py is the main consumer of this module.

from concurrent.futures import ThreadPoolExecutor
from socket import *
import json
import uuid

import requests

import control
from config import env

# --- LAN (backup) ---

UDP_IP = "239.255.255.250" # Govee multicast group address
SEND_PORT = 4001    # Devices listen here for commands
LISTEN_PORT = 4002  # Devices reply to the multicast group on this port

# Local IP of the interface on the SAME network as the Govee devices. Set
# explicitly so multicast doesn't leave via a VPN/WSL/Hyper-V adapter on Windows.
LOCAL_IP = env.IP_ADDR

devices = [] # LAN devices, populated by discover_devices()


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


# --- Cloud HTTP API (primary) ---

GOVEE_BASE_URL = "https://openapi.api.govee.com"
GOVEE_HEADERS = {
    "Content-Type": "application/json",
    "Govee-API-Key": env.GOVEE_API,
}

cloud_devices = [] # Cloud devices, populated by fetch_cloud_devices()


def fetch_cloud_devices():
    """Fetch the account's devices from Govee's cloud API."""
    response = requests.get(f"{GOVEE_BASE_URL}/router/api/v1/user/devices", headers=GOVEE_HEADERS)
    response.raise_for_status()
    cloud_devices.clear()
    cloud_devices.extend(response.json()["data"])
    return cloud_devices


def _cloud_turn(device, on: bool):
    body = {
        "requestId": str(uuid.uuid4()),
        "payload": {
            "sku": device["sku"],
            "device": device["device"],
            "capability": {
                "type": "devices.capabilities.on_off",
                "instance": "powerSwitch",
                "value": 1 if on else 0,
            },
        },
    }
    response = requests.post(f"{GOVEE_BASE_URL}/router/api/v1/device/control", headers=GOVEE_HEADERS, json=body)
    response.raise_for_status()
    


# --- Combined control: cloud first, LAN as backup ---

def _turn_lights(on: bool):
    try:
        if not cloud_devices:
            fetch_cloud_devices()
        with ThreadPoolExecutor(max_workers=len(cloud_devices)) as pool:
            list(pool.map(lambda device: _cloud_turn(device, on), cloud_devices))
        print(f"Turned lights {'on' if on else 'off'} via cloud API ({len(cloud_devices)} device(s))")
    except requests.exceptions.RequestException:
        print("Cloud API unreachable, falling back to LAN control")
        if not devices:
            discover_devices()
        with ThreadPoolExecutor(max_workers=len(devices)) as pool:
            list(pool.map(lambda device: control.send_turn_command(device["ip"], on), devices))
        print(f"Turned lights {'on' if on else 'off'} via LAN ({len(devices)} device(s))")

# def _activation(colour: str):
    

def turn_lights_on():
    _turn_lights(True)


def turn_lights_off():
    _turn_lights(False)

def activation_on():
    _activation("Orange")


if __name__ == "__main__":
    discover_devices()
