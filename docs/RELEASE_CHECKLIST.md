# RoomHub release checklist

Complete this checklist before declaring RoomHub 1.0 stable.

## Automated checks

- Server unit and integration tests pass with deprecations treated as errors.
- Server application, tests, and Home Assistant integration compile.
- Release consistency, JSON, translations, and repository secret checks pass.
- ESP-IDF 5.4.4 builds the endpoint with adequate application and bootloader
  partition headroom.
- GitHub server tests and release quality gates pass on the release commit.
- Signed endpoint release artifacts pass their recorded SHA-256 checksums.

## Single-endpoint regression

- Endpoint reconnects after add-on restart, Home Assistant restart, and power
  cycle without losing its identity, area, or preferences.
- Dashboard controls, Assist, Piper playback, notifications, camera snapshot,
  screen/volume/microphone controls, battery reporting, and intercom work.
- A signed OTA installs, reconnects, confirms health, and preserves settings.
- A failed or unhealthy OTA rolls back to the last healthy application.

## Multi-endpoint acceptance

Complete [multi-device acceptance](MULTI_DEVICE_ACCEPTANCE.md) with two physical
Tab5 devices. This is the only hardware acceptance item that cannot be closed
until the additional devices are available.

## Release publication

- Add-on, Home Assistant integration, endpoint firmware, onboarding guide, and
  [supported features](SUPPORTED_FEATURES.md) identify their exact versions.
- The public browser installer references the promoted hardware-tested endpoint
  release, not a draft or same-version replacement build.
- Installation, pairing, update, rollback, and USB recovery are tested from the
  published documentation.
- Known limitations and post-1.0 enhancements are recorded explicitly.
- The add-on stage changes from `experimental` only when all required 1.0
  acceptance items are complete.
