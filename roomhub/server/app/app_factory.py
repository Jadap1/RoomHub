import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from .config import PROJECT_NAME, VERSION
from .core import database
from .core.area_registry import area_registry
from .core.command_registry import register_commands
from .core.command_router import command_router
from .core.connection_manager import manager
from .core.device_registry import device_registry
from .core.entity_registry import entity_registry
from .core.entity_registry_init import register_entities
from .core.event_subscriptions import register_event_subscriptions
from .core.floor_registry import floor_registry
from .core.registry import registry
from .handlers.dispatcher import dispatch
from .integrations.registry import homeassistant
from .services.voice_audio_service import VoiceAudioConnection
from .services.audio_command_service import (
    AudioPlayRequest,
    audio_command_service,
)
from .services.endpoint_assignment_service import endpoint_assignment_service
from .services.endpoint_pairing_service import endpoint_pairing_service
from .services.endpoint_dashboard_preferences_service import (
    endpoint_dashboard_preferences_service,
)
from .services.firmware_service import firmware_service
from .services.firmware_auth import configured_firmware_token, firmware_token_valid
from .services.firmware_audit import firmware_audit
from .services.firmware_deployment_service import firmware_deployment_service
from .services.notification_service import NotificationRequest, notification_service
from .services.endpoint_control_service import (
    EndpointControlRequest,
    endpoint_control_service,
)
from .services.intercom_service import intercom_service
from .services.camera_snapshot_service import (
    CameraSnapshotTimeout,
    CameraSnapshotUnavailable,
    camera_snapshot_service,
)


class EndpointManagementUpdate(BaseModel):
    area_id: str
    excluded_entity_ids: list[str] = Field(default_factory=list)
    entity_order: list[str] = Field(default_factory=list)
    pinned_entity_ids: list[str] = Field(default_factory=list)


class EndpointPairingRequest(BaseModel):
    device_name: str = Field(min_length=1, max_length=64)
    area_id: str


def create_app(
    database_path: str | Path | None = None,
    homeassistant_connector=None
) -> FastAPI:

    connector = (
        homeassistant_connector
        if homeassistant_connector is not None
        else homeassistant
    )

    if database_path is not None:
        database.DATABASE = Path(database_path)

    database.initialise_database()
    entity_registry.load()
    floor_registry.load()
    area_registry.load()
    device_registry.load()
    register_entities()
    register_commands()
    register_event_subscriptions(connector)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.homeassistant_task = asyncio.create_task(
            connector.start()
        )
        try:
            yield
        finally:
            await connector.stop()
            task = getattr(
                app.state,
                "homeassistant_task",
                None
            )
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(
        title=PROJECT_NAME,
        version=VERSION,
        lifespan=lifespan
    )

    @app.get("/entities")
    async def entities():
        return entity_registry.get_all()

    @app.get("/floors")
    async def floors():
        return floor_registry.get_all()

    @app.get("/areas")
    async def areas():
        return area_registry.get_all()

    @app.get("/devices")
    async def devices():
        return device_registry.get_all()

    @app.get("/floors/{floor_id}")
    async def floor(floor_id: str):
        item = floor_registry.get(floor_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.get("/areas/{area_id}")
    async def area(area_id: str):
        item = area_registry.get(area_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.get("/devices/{device_id}")
    async def device(device_id: str):
        item = device_registry.get(device_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "service": PROJECT_NAME,
            "version": VERSION,
            "entities": len(entity_registry.entities),
            "homeassistant": {
                "connected": connector.connected
            }
        }

    @app.get("/endpoints")
    async def endpoints():
        return registry.get_all()

    @app.put("/api/endpoints/{endpoint_id}/controls")
    async def control_endpoint(endpoint_id: str, request: EndpointControlRequest):
        result = await endpoint_control_service.apply(endpoint_id, request)
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail="endpoint not found")
        if result["status"] == "unavailable":
            raise HTTPException(status_code=409, detail="endpoint unavailable")
        return result

    @app.get("/api/endpoints/{endpoint_id}/camera/snapshot")
    async def camera_snapshot(endpoint_id: str):
        try:
            image = await camera_snapshot_service.capture(endpoint_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="endpoint not found") from error
        except CameraSnapshotUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except CameraSnapshotTimeout as error:
            raise HTTPException(status_code=504, detail=str(error)) from error
        return Response(
            content=image,
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.put("/api/endpoints/{endpoint_id}/camera/upload/{request_id}")
    async def camera_upload(
        endpoint_id: str,
        request_id: str,
        request: Request,
        x_roomhub_camera_token: str | None = Header(default=None),
    ):
        image = await request.body()
        try:
            camera_snapshot_service.upload(
                endpoint_id, request_id, x_roomhub_camera_token, image
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="capture request not found") from error
        except PermissionError as error:
            raise HTTPException(status_code=401, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"status": "accepted", "request_id": request_id}

    @app.get("/", response_class=HTMLResponse)
    @app.get("//", response_class=HTMLResponse)
    @app.get("/manage/", response_class=HTMLResponse)
    async def management_page():
        return (Path(__file__).parent / "static" / "manage.html").read_text(
            encoding="utf-8"
        )

    @app.get("/api/config")
    @app.get("/manage/api/config")
    async def management_config():
        endpoints = []
        for endpoint_id, endpoint in registry.endpoints.items():
            endpoints.append({
                **endpoint.model_dump(mode="json"),
                "entities": (
                    endpoint_dashboard_preferences_service.eligible_entities(
                        endpoint_id
                    )
                ),
                "firmware_deployment": firmware_deployment_service.get(endpoint_id),
            })
        endpoints.sort(key=lambda item: item["device_name"].casefold())
        return {
            "endpoints": endpoints,
            "areas": sorted(
                [area.model_dump() for area in area_registry.areas.values()],
                key=lambda item: item["name"].casefold(),
            ),
        }

    @app.post("/api/pairing")
    @app.post("/manage/api/pairing")
    async def create_endpoint_pairing(
        pairing_request: EndpointPairingRequest,
        request: Request,
        x_roomhub_admin_token: str | None = Header(default=None),
    ):
        if configured_firmware_token() is None:
            raise HTTPException(status_code=503, detail="admin token not configured")
        if not firmware_token_valid(x_roomhub_admin_token):
            firmware_audit.record("pairing_denied", client=str(request.client))
            raise HTTPException(status_code=401, detail="invalid admin token")
        if area_registry.get(pairing_request.area_id) is None:
            raise HTTPException(status_code=400, detail="invalid area")
        try:
            result = endpoint_pairing_service.create(
                pairing_request.device_name, pairing_request.area_id
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        firmware_audit.record(
            "pairing_created",
            device_name=pairing_request.device_name,
            area_id=pairing_request.area_id,
        )
        return result

    @app.put("/api/endpoints/{endpoint_id}")
    @app.put("/manage/api/endpoints/{endpoint_id}")
    async def update_endpoint_management(
        endpoint_id: str,
        update: EndpointManagementUpdate,
    ):
        assignment = await endpoint_assignment_service.assign(
            endpoint_id, update.area_id
        )
        if assignment["status"] != "assigned":
            raise HTTPException(status_code=400, detail=assignment)
        preferences = (
            await endpoint_dashboard_preferences_service.replace_exclusions(
                endpoint_id,
                set(update.excluded_entity_ids),
                update.entity_order or None,
                set(update.pinned_entity_ids),
            )
        )
        if preferences["status"] != "saved":
            raise HTTPException(status_code=400, detail=preferences)
        endpoint = registry.get(endpoint_id)
        return {
            "status": "saved",
            "endpoint": endpoint.model_dump(mode="json"),
            "entities": (
                endpoint_dashboard_preferences_service.eligible_entities(
                    endpoint_id
                )
            ),
        }

    @app.put("/endpoints/{endpoint_id}/area/{area_id}")
    async def assign_endpoint_area(endpoint_id: str, area_id: str):
        return await endpoint_assignment_service.assign(endpoint_id, area_id)

    @app.put("/firmware/endpoint")
    async def publish_endpoint_firmware(
        request: Request,
        x_firmware_version: str = Header(),
        x_roomhub_admin_token: str | None = Header(default=None),
    ):
        if configured_firmware_token() is None:
            raise HTTPException(status_code=503, detail="firmware admin token not configured")
        if not firmware_token_valid(x_roomhub_admin_token):
            firmware_audit.record("publish_denied", client=str(request.client))
            raise HTTPException(status_code=401, detail="invalid firmware admin token")
        image = await request.body()
        try:
            manifest = await asyncio.to_thread(
                firmware_service.publish,
                x_firmware_version,
                image,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        firmware_audit.record(
            "published",
            version=manifest.version,
            size=manifest.size,
            sha256=manifest.sha256,
        )
        return manifest

    @app.get("/firmware/endpoint/manifest")
    async def endpoint_firmware_manifest():
        manifest = firmware_service.manifest()
        if manifest is None:
            raise HTTPException(status_code=404, detail="firmware not published")
        return manifest

    @app.get("/firmware/endpoint/image")
    async def endpoint_firmware_image():
        manifest = firmware_service.manifest()
        if manifest is None:
            raise HTTPException(status_code=404, detail="firmware not published")
        return FileResponse(
            firmware_service.image_path,
            media_type="application/octet-stream",
            filename=f"roomhub-endpoint-{manifest.version}.bin",
        )

    @app.post("/firmware/endpoint/deploy/{endpoint_id}")
    async def deploy_endpoint_firmware(
        endpoint_id: str,
        request: Request,
        x_roomhub_admin_token: str | None = Header(default=None),
    ):
        if configured_firmware_token() is None:
            raise HTTPException(status_code=503, detail="firmware admin token not configured")
        if not firmware_token_valid(x_roomhub_admin_token):
            firmware_audit.record(
                "deploy_denied",
                endpoint_id=endpoint_id,
                client=str(request.client),
            )
            raise HTTPException(status_code=401, detail="invalid firmware admin token")
        endpoint = registry.get(endpoint_id)
        manifest = firmware_service.manifest()
        if endpoint is None or not endpoint.connected:
            raise HTTPException(status_code=409, detail="endpoint not connected")
        if manifest is None:
            raise HTTPException(status_code=404, detail="firmware not published")
        try:
            deployment = await firmware_deployment_service.deploy(endpoint_id, manifest)
        except ConnectionError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {"status": "sent", "target": endpoint_id, "firmware": manifest, "deployment": deployment}

    @app.get("/firmware/endpoint/deploy/{endpoint_id}")
    async def endpoint_firmware_deployment(endpoint_id: str):
        return firmware_deployment_service.get(endpoint_id) or {"status": "none"}

    @app.post("/notifications")
    @app.post("/api/notifications")
    @app.post("/manage/api/notifications")
    async def create_notification(request: NotificationRequest):
        return await notification_service.notify(request)

    @app.get("/notifications/{delivery_id}")
    async def notification_delivery(delivery_id: str):
        delivery = notification_service.get(delivery_id)
        return delivery if delivery is not None else {"error": "not found"}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        registration_nonce = secrets.token_urlsafe(24)
        await websocket.send_json({
            "version": "1.0",
            "type": "endpoint.challenge",
            "payload": {"nonce": registration_nonce},
        })
        endpoint_id = None
        audio = VoiceAudioConnection()
        try:
            while True:
                event = await websocket.receive()
                if event["type"] == "websocket.disconnect":
                    break

                binary = event.get("bytes")
                if binary is not None:
                    response = (
                        await intercom_service.send_audio(endpoint_id, binary)
                        if endpoint_id is not None
                        and intercom_service.is_transmitting(endpoint_id)
                        else await audio.send_audio(binary)
                    )
                    if response is not None:
                        await websocket.send_json(response)
                    continue

                data = event.get("text")
                if data is None:
                    continue
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({
                        "version": "1.0",
                        "type": "error",
                        "payload": {"message": "Invalid JSON"},
                    })
                    continue

                message_type = message.get("type")
                if message_type == "endpoint.register":
                    payload = message.get("payload") or {}
                    candidate_id = payload.get("device_id")
                    pairing = endpoint_pairing_service.authenticate(
                        candidate_id,
                        payload.get("device_proof"),
                        registration_nonce,
                    )
                    if not pairing.accepted:
                        await websocket.send_json({
                            "version": "1.0",
                            "type": "endpoint.registration_rejected",
                            "payload": {"reason": pairing.reason},
                        })
                        continue
                    if pairing.device_name:
                        payload["device_name"] = pairing.device_name
                    if pairing.area_id:
                        payload["area_id"] = pairing.area_id
                    endpoint_id = candidate_id
                    await manager.connect(
                        endpoint_id,
                        websocket
                    )
                    response = await dispatch(message)
                    firmware_deployment_service.mark_running(
                        endpoint_id,
                        message.get("payload", {}).get("firmware_version"),
                    )
                elif (
                    isinstance(message_type, str)
                    and message_type.startswith("intercom.")
                ):
                    if endpoint_id is None:
                        response = {
                            "version": "1.0",
                            "type": "intercom.rejected",
                            "payload": {"reason": "endpoint_not_registered"},
                        }
                    elif message.get("source") not in (None, endpoint_id):
                        response = {
                            "version": "1.0",
                            "type": "intercom.rejected",
                            "payload": {"reason": "source_mismatch"},
                        }
                    elif message_type == "intercom.start":
                        response = await intercom_service.start(
                            endpoint_id, message.get("payload") or {}
                        )
                    elif message_type == "intercom.status":
                        response = await intercom_service.target_status(
                            endpoint_id, message.get("payload") or {}
                        )
                    elif message_type in {"intercom.end", "intercom.cancel"}:
                        response = await intercom_service.stop(
                            endpoint_id,
                            "cancelled"
                            if message_type == "intercom.cancel"
                            else "completed",
                        )
                    else:
                        response = {
                            "version": "1.0",
                            "type": "intercom.rejected",
                            "payload": {"reason": "unknown_intercom_message"},
                        }
                elif (
                    isinstance(message_type, str)
                    and message_type.startswith("voice.audio.")
                ):
                    if endpoint_id is None:
                        response = {
                            "version": "1.0",
                            "type": "voice.audio.rejected",
                            "payload": {
                                "status": "rejected",
                                "reason": "endpoint_not_registered",
                            },
                        }
                    elif message.get("source") not in (None, endpoint_id):
                        response = {
                            "version": "1.0",
                            "type": "voice.audio.rejected",
                            "payload": {
                                "status": "rejected",
                                "reason": "source_mismatch",
                            },
                        }
                    elif message_type == "voice.audio.start":
                        response = await audio.start(
                            message.get("payload") or {}
                        )
                    elif message_type == "voice.audio.end":
                        response = await audio.finish(endpoint_id)
                    elif message_type == "voice.audio.cancel":
                        response = await audio.cancel()
                    else:
                        response = {
                            "version": "1.0",
                            "type": "voice.audio.rejected",
                            "payload": {
                                "status": "rejected",
                                "reason": "unknown_audio_message",
                            },
                        }
                else:
                    response = await dispatch(message)
                await websocket.send_json(response)
                if message_type == "endpoint.register" and endpoint_id is not None:
                    await intercom_service.broadcast_targets(endpoint_id)
                    await firmware_deployment_service.retry_after_registration(
                        endpoint_id,
                        message.get("payload", {}).get("firmware_version"),
                        firmware_service.manifest(),
                    )
        except WebSocketDisconnect:
            pass
        finally:
            await audio.close()
            if endpoint_id:
                await intercom_service.close_endpoint(endpoint_id)
                if manager.disconnect(endpoint_id, websocket):
                    endpoint = registry.get(endpoint_id)
                    if endpoint:
                        endpoint.connected = False
                    await intercom_service.broadcast_targets()

    @app.post("/test/display/{endpoint_id}")
    async def test_display(endpoint_id: str):
        await manager.send(
            endpoint_id,
            {
                "version": "1.0",
                "type": "display.show",
                "source": "roomhub-core",
                "target": endpoint_id,
                "payload": {"screen": "home"}
            }
        )
        return {
            "status": "sent",
            "target": endpoint_id
        }

    @app.post("/audio/{endpoint_id}/play")
    async def play_audio(endpoint_id: str, request: AudioPlayRequest):
        return await audio_command_service.play(endpoint_id, request)

    @app.post("/audio/{endpoint_id}/stop/{request_id}")
    async def stop_audio(endpoint_id: str, request_id: str):
        return await audio_command_service.stop(endpoint_id, request_id)

    @app.post("/test/light/{endpoint_id}")
    async def test_light(endpoint_id: str):
        message = {
            "version": "1.0",
            "type": "light.toggle",
            "source": "roomhub-core",
            "target": endpoint_id,
            "payload": {"entity_id": "test_light"}
        }
        return await command_router.execute(message)

    @app.get("/state/{endpoint_id}")
    async def endpoint_state(endpoint_id: str):
        endpoint = registry.get(endpoint_id)
        if not endpoint:
            return None
        return endpoint.state

    @app.get("/entities/{entity_id}")
    async def entity(entity_id: str):
        item = entity_registry.get(entity_id)
        if not item:
            return {"error": "not found"}
        return item.model_dump()

    @app.post("/test/command/light")
    async def test_light_command():
        message = {
            "version": "1.0",
            "type": "light.toggle",
            "source": "test",
            "target": "roomhub-core",
            "payload": {
                "entity_id": "light.kitchen_main"
            }
        }
        return await command_router.execute(message)

    return app
