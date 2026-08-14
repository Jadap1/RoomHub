#!/usr/bin/env python3
"""Encrypt and upload the endpoint signing key as a GitHub Actions secret."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from nacl.public import PublicKey, SealedBox


def github_credential() -> str:
    result = subprocess.run(
        ["git", "credential", "fill"],
        input=b"protocol=https\nhost=github.com\n\n",
        check=True,
        capture_output=True,
    )
    values = {}
    for line in result.stdout.decode().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    token = values.get("password")
    if not token:
        raise RuntimeError("Git Credential Manager has no GitHub credential")
    return token


def request(token: str, method: str, url: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode()
    call = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RoomHub-release-setup",
        },
    )
    try:
        with urllib.request.urlopen(call, timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {error.code}: {detail}") from error
    return json.loads(body) if body else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="owner/name")
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument(
        "--name", default="ENDPOINT_SIGNING_KEY_B64", help="Actions secret name"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    key_path = args.key.resolve()
    if not key_path.is_file():
        raise FileNotFoundError(key_path)
    token = github_credential()
    endpoint = f"https://api.github.com/repos/{args.repository}/actions/secrets"
    public_key = request(token, "GET", f"{endpoint}/public-key")
    plaintext = base64.b64encode(key_path.read_bytes())
    encrypted = SealedBox(
        PublicKey(base64.b64decode(public_key["key"]))
    ).encrypt(plaintext)
    request(
        token,
        "PUT",
        f"{endpoint}/{args.name}",
        {
            "encrypted_value": base64.b64encode(encrypted).decode(),
            "key_id": public_key["key_id"],
        },
    )
    configured = request(token, "GET", endpoint)
    if args.name not in {
        item.get("name") for item in configured.get("secrets", [])
    }:
        raise RuntimeError("GitHub did not report the configured secret")
    print(f"Configured encrypted Actions secret {args.name} in {args.repository}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
