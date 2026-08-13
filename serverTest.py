import requests
from fastapi import status, HTTPException, APIRouter
import json

from config import env

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

GOVEE_DEVICES_URL = "https://openapi.api.govee.com/router/api/v1/user/devices"

@router.get("/devices", status_code=status.HTTP_200_OK)
def get_devices():
    response = requests.get(
        GOVEE_DEVICES_URL,
        headers={
            "Content-Type": "application/json",
            "Govee-API-Key": env.GOVEE_API,
        },
    )

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=response.status_code, detail=response.text)

    devices = response.json()
    return devices


deviceList = get_devices()
print(type(deviceList["data"]))