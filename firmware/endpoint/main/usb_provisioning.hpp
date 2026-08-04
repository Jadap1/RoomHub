#pragma once

namespace roomhub::provisioning {

// Blocks until a valid configuration is stored, then restarts the endpoint.
// This is called only when NVS is available and no valid configuration exists.
[[noreturn]] void run_usb_provisioning();

}  // namespace roomhub::provisioning
