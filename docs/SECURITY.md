# RoomHub security and release credentials

RoomHub configuration and release credentials must never be committed to the
repository or included in firmware artifacts.

The browser installer self-hosts the integrity-verified `esp-web-tools` 10.4.0
bundle under `installer/vendor/esp-web-tools`. Do not replace it with a mutable
CDN URL. Dependency updates must be downloaded from the npm registry, checked
against the registry's SHA-512 integrity metadata, reviewed, and committed with
the upstream license before the installer is redeployed.

## Local secrets

The following values are local secrets:

- Home Assistant long-lived access tokens;
- RoomHub firmware administration tokens;
- Wi-Fi credentials used while provisioning an endpoint;
- firmware-signing private keys;
- future endpoint pairing secrets.

`roomhub/server/config/homeassistant.json` is for local development only. Copy
`homeassistant.example.json`, populate the local copy, and leave it untracked.
The Home Assistant add-on obtains its API credential from the Supervisor and
does not require this development file.

Provisioning tools must prompt for Wi-Fi passwords without echoing them. Do not
accept passwords on a command line because command histories and process lists
can expose them.

The endpoint pairing credential is transferred only over the local USB
provisioning connection. RoomHub stores its SHA-256 digest. WebSocket
registration uses a fresh nonce and HMAC-SHA256 proof, so the credential is not
placed in network messages. Plain HTTP/WebSocket traffic can still be observed
or relayed by an attacker with access to the local network; use a trusted device
network or an HTTPS/WSS reverse proxy where that threat is relevant.

## Firmware signing

Release OTA and factory images are signed by the project release key. Store the
RSA private key outside the repository, back it up offline, and expose it to CI
only through the protected `ENDPOINT_SIGNING_KEY_B64` release secret. Restrict
tag creation and release-environment access to maintainers. Public releases contain
signed binaries, checksums, manifests, and public verification material; they
never contain the private key.

Maintainers can configure the encrypted GitHub Actions secret without placing
the key on a command line:

```text
python -m pip install -r tools/requirements-release.txt
python tools/set_github_signing_secret.py --repository Jadap1/RoomHub --key D:/secure/roomhub-endpoint.pem
```

The helper obtains the existing Git Credential Manager login, fetches GitHub's
repository public key, encrypts the base64-encoded signing key locally with a
sealed box, and uploads only ciphertext.

## Credential incident procedure

If a credential is committed:

1. Revoke or rotate it at its issuing service immediately.
2. Replace tracked secret files with documented examples and correct ignore
   coverage.
3. Inspect all branches, tags, and open pull requests for the credential.
4. Rewrite published Git history only as a coordinated maintenance operation.
5. Force-push rewritten references, invalidate cached artifacts, and tell every
   contributor to replace or carefully clean existing clones.
6. Verify the revoked credential no longer authenticates.

Removing a secret from the current revision does not remove it from Git history
and does not remove the need to revoke it.

## Before sharing the repository

- Run `python tools/check_repository_secrets.py`.
- Confirm local configuration and signing keys are untracked.
- Search every reachable Git revision, not only the working tree.
- Confirm previously exposed credentials have been revoked.
- Build public artifacts from a clean checkout and inspect their contents.
