import json
from typing import Any


async def authenticate(
    websocket: Any,
    access_token: str
) -> None:

    initial_message = json.loads(
        await websocket.recv()
    )

    if (
        initial_message.get("type")
        != "auth_required"
    ):

        raise RuntimeError(
            "Home Assistant did not request "
            "authentication"
        )


    await websocket.send(
        json.dumps(
            {
                "type": "auth",
                "access_token": access_token
            }
        )
    )


    auth_response = json.loads(
        await websocket.recv()
    )

    response_type = auth_response.get(
        "type"
    )

    if response_type == "auth_invalid":

        raise RuntimeError(
            "Home Assistant authentication "
            "failed: "
            f"{auth_response.get('message')}"
        )


    if response_type != "auth_ok":

        raise RuntimeError(
            "Unexpected Home Assistant "
            "authentication response: "
            f"{auth_response}"
        )
