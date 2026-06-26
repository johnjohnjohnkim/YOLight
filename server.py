from socket import *
import json

PORT = 4002

serverSocket = socket(AF_INET, SOCK_DGRAM)
serverSocket.bind(('', PORT))


print("Server is ready to receive.")

while True:
    message, clientAddr = serverSocket.recvfrom(2048)
    modMessage = message.decode.upper()