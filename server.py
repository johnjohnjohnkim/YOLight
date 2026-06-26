from socket import *
import json

MCAST_GRP = "239.255.255.250"
SEND_PORT = 4001     # devices listen here for scan requests
LISTEN_PORT = 4002   # devices reply to the multicast group on this port
CONTROL_PORT = 4003  # send control commands to a device's IP here

# The local IP of the interface on the SAME network as your Govee device.
# Set this explicitly on Windows so multicast doesn't leave via a VPN/WSL/Hyper-V
# adapter. Find it with `ipconfig` (the IPv4 address of your Wi-Fi/Ethernet).
LOCAL_IP = "192.168.2.65"  # e.g. "192.168.1.50"

# --- Listen socket: must JOIN the multicast group to hear device replies ---
listenSocket = socket(AF_INET, SOCK_DGRAM)
listenSocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
listenSocket.bind(("", LISTEN_PORT))
mreq = inet_aton(MCAST_GRP) + inet_aton(LOCAL_IP)
listenSocket.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP, mreq)
listenSocket.settimeout(10)

# --- Send socket: pin the outgoing interface for multicast ---
sendSocket = socket(AF_INET, SOCK_DGRAM)
sendSocket.setsockopt(IPPROTO_IP, IP_MULTICAST_IF, inet_aton(LOCAL_IP))
sendSocket.setsockopt(IPPROTO_IP, IP_MULTICAST_TTL, 2)

scan_msg = json.dumps({
    "msg": {
        "cmd": "scan",
        "data": {"account_topic": "reserve"}
    }
}).encode()

sendSocket.sendto(scan_msg, (MCAST_GRP, SEND_PORT))

devices = []

while True:
    try:
        data, addr = listenSocket.recvfrom(1024)
        response = json.loads(data.decode())
        print(f"Got reply from {addr}: {response}")
        devices.append(response["msg"]["data"])
    except timeout:
        print(f"Done scanning. Found {len(devices)} device(s).")
        break

# print(devices)
# Testing just for the one device connected

#command to turn off light (0 - off, 1 - on)
command = json.dumps({
    "msg":{
        "cmd" : "turn",
        "data":{
            "value" : 0
        }
    }
})

clientSocket = socket(AF_INET, SOCK_DGRAM)
clientSocket.sendto(command.encode(), (devices[0]["ip"], CONTROL_PORT))