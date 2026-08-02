from collections.abc import Callable
from typing import Any

from ..integrations.homeassistant.assist_pipeline import (
    HomeAssistantAssistError,
    HomeAssistantSpeechToTextSession,
)
from ..integrations.homeassistant.tts_pipeline import (
    HomeAssistantTextToSpeechClient,
)
from .voice_intent_service import voice_intent_service


SessionFactory = Callable[..., HomeAssistantSpeechToTextSession]
TextToSpeechFactory = Callable[[], HomeAssistantTextToSpeechClient]


def _message(message_type: str, **payload: Any) -> dict[str, Any]:
    return {
        "version": "1.0",
        "type": message_type,
        "payload": payload,
    }


class VoiceAudioConnection:
    def __init__(
        self,
        session_factory: SessionFactory = HomeAssistantSpeechToTextSession,
        intent_service=voice_intent_service,
        text_to_speech_factory: TextToSpeechFactory = (
            HomeAssistantTextToSpeechClient
        ),
    ) -> None:
        self._session_factory = session_factory
        self._intent_service = intent_service
        self._text_to_speech_factory = text_to_speech_factory
        self._session: HomeAssistantSpeechToTextSession | None = None

    async def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._session is not None:
            return _message(
                "voice.audio.rejected",
                status="rejected",
                reason="session_already_active",
            )

        sample_rate = payload.get("sample_rate")
        channels = payload.get("channels")
        audio_format = payload.get("format")
        if (
            sample_rate != 16000
            or channels != 1
            or audio_format != "pcm_s16le"
        ):
            return _message(
                "voice.audio.rejected",
                status="rejected",
                reason="unsupported_audio_format",
                message=(
                    "Audio must be 16 kHz, mono, signed 16-bit "
                    "little-endian PCM."
                ),
            )

        session = self._session_factory(sample_rate=sample_rate)
        try:
            await session.start()
        except Exception:
            await session.abort()
            return _message(
                "voice.audio.failed",
                status="failed",
                reason="transcription_unavailable",
            )

        self._session = session
        return _message(
            "voice.audio.ready",
            status="ready",
            sample_rate=sample_rate,
            channels=channels,
            format=audio_format,
        )

    async def send_audio(
        self,
        audio: bytes,
    ) -> dict[str, Any] | None:
        if self._session is None:
            return _message(
                "voice.audio.rejected",
                status="rejected",
                reason="no_active_session",
            )
        try:
            await self._session.send_audio(audio)
        except (ValueError, RuntimeError) as error:
            return _message(
                "voice.audio.rejected",
                status="rejected",
                reason="invalid_audio_frame",
                message=str(error),
            )
        except Exception:
            await self.close()
            return _message(
                "voice.audio.failed",
                status="failed",
                reason="transcription_failed",
            )
        return None

    async def finish(
        self,
        endpoint_id: str,
    ) -> dict[str, Any]:
        session = self._session
        self._session = None
        if session is None:
            return _message(
                "voice.audio.rejected",
                status="rejected",
                reason="no_active_session",
            )

        try:
            transcript = await session.finish()
        except HomeAssistantAssistError:
            return _message(
                "voice.audio.failed",
                status="failed",
                reason="transcription_failed",
            )
        except Exception:
            await session.abort()
            return _message(
                "voice.audio.failed",
                status="failed",
                reason="transcription_failed",
            )

        response = await self._intent_service.handle_transcript(
            transcript,
            endpoint_id=endpoint_id,
        )
        response = dict(response)
        response["payload"] = {
            **response.get("payload", {}),
            "transcript": transcript,
        }
        speech_text = self._speech_text(response)
        try:
            speech = await self._text_to_speech_factory().synthesize(
                speech_text
            )
        except Exception:
            response["payload"]["speech_status"] = "unavailable"
        else:
            response["payload"]["speech"] = {
                "url": speech.url,
                "mime_type": speech.mime_type,
            }
        return response

    async def cancel(self) -> dict[str, Any]:
        had_session = self._session is not None
        await self.close()
        return _message(
            "voice.audio.cancelled",
            status="cancelled",
            had_active_session=had_session,
        )

    async def close(self) -> None:
        session = self._session
        self._session = None
        if session is not None:
            await session.abort()

    @staticmethod
    def _speech_text(response: dict[str, Any]) -> str:
        response_type = response.get("type")
        payload = response.get("payload") or {}
        if response_type == "voice.intent.accepted":
            return "Done."
        if response_type == "voice.intent.rejected":
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
            return "Sorry, I did not understand that command."
        return "Sorry, I could not complete that command."
