from __future__ import annotations

import hashlib
import hmac
import secrets
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ..core.database import get_connection


PAIRING_LIFETIME = timedelta(minutes=10)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def device_proof(token: str, nonce: str, endpoint_id: str) -> str:
    """Produce the proof used by tests and compatible provisioning clients."""
    key = bytes.fromhex(_hash(token))
    message = f"{nonce}:{endpoint_id}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _matches_proof(
    token_hash: str, proof: str | None, nonce: str, endpoint_id: str
) -> bool:
    if not proof or len(proof) != 64:
        return False
    expected = hmac.new(
        bytes.fromhex(token_hash),
        f"{nonce}:{endpoint_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, proof)


@dataclass(frozen=True)
class PairingResult:
    accepted: bool
    reason: str
    device_name: str | None = None
    area_id: str | None = None
    legacy: bool = False


class EndpointPairingService:
    def create(self, device_name: str, area_id: str) -> dict:
        name = device_name.strip()
        if not name or len(name) > 64:
            raise ValueError("device_name must contain 1 to 64 characters")
        token = secrets.token_urlsafe(24)
        expires = datetime.now(UTC) + PAIRING_LIFETIME
        with closing(get_connection()) as connection, connection:
            connection.execute(
                "DELETE FROM endpoint_pairing_codes WHERE expires_at <= ?",
                (datetime.now(UTC).isoformat(),),
            )
            connection.execute(
                """
                INSERT INTO endpoint_pairing_codes
                    (token_hash, device_name, area_id, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (_hash(token), name, area_id, expires.isoformat()),
            )
        return {
            "pairing_token": token,
            "device_name": name,
            "area_id": area_id,
            "expires_at": expires.isoformat(),
        }

    def authenticate(
        self, endpoint_id: str, proof: str | None, nonce: str
    ) -> PairingResult:
        if not endpoint_id or len(endpoint_id) > 64:
            return PairingResult(False, "invalid_endpoint_id")
        with closing(get_connection()) as connection, connection:
            credential = connection.execute(
                "SELECT token_hash FROM endpoint_credentials WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
            if credential is not None:
                if _matches_proof(credential[0], proof, nonce, endpoint_id):
                    profile = connection.execute(
                        "SELECT device_name FROM endpoint_profiles WHERE endpoint_id = ?",
                        (endpoint_id,),
                    ).fetchone()
                    assignment = connection.execute(
                        "SELECT area_id FROM endpoint_assignments WHERE endpoint_id = ?",
                        (endpoint_id,),
                    ).fetchone()
                    return PairingResult(
                        True,
                        "authenticated",
                        profile[0] if profile else None,
                        assignment[0] if assignment else None,
                    )
                return PairingResult(False, "invalid_device_token")

            if proof:
                pending_codes = connection.execute(
                    """
                    SELECT token_hash, device_name, area_id, expires_at
                    FROM endpoint_pairing_codes
                    """,
                ).fetchall()
                pending = next((
                    item for item in pending_codes
                    if datetime.fromisoformat(item[3]) > datetime.now(UTC)
                    and _matches_proof(item[0], proof, nonce, endpoint_id)
                ), None)
                if pending is not None:
                    connection.execute(
                        "INSERT INTO endpoint_credentials VALUES (?, ?, ?)",
                        (endpoint_id, pending[0], datetime.now(UTC).isoformat()),
                    )
                    connection.execute(
                        "INSERT INTO endpoint_profiles VALUES (?, ?)",
                        (endpoint_id, pending[1]),
                    )
                    connection.execute(
                        """
                        INSERT INTO endpoint_assignments VALUES (?, ?)
                        ON CONFLICT(endpoint_id) DO UPDATE SET area_id=excluded.area_id
                        """,
                        (endpoint_id, pending[2]),
                    )
                    connection.execute(
                        "DELETE FROM endpoint_pairing_codes WHERE token_hash = ?",
                        (pending[0],),
                    )
                    return PairingResult(True, "paired", pending[1], pending[2])

            # Existing assigned endpoints are grandfathered until reprovisioned.
            legacy = connection.execute(
                "SELECT area_id FROM endpoint_assignments WHERE endpoint_id = ?",
                (endpoint_id,),
            ).fetchone()
            if legacy is not None:
                return PairingResult(
                    True, "legacy_assignment", area_id=legacy[0], legacy=True
                )
        return PairingResult(False, "pairing_required")


endpoint_pairing_service = EndpointPairingService()
