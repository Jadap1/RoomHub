#pragma once

#include <cstddef>
#include <string>

namespace roomhub::ota {

using StatusCallback = void (*)(
    const std::string &request_id,
    const std::string &version,
    const char *status,
    unsigned int progress,
    const char *reason
);

bool start(
    const std::string &request_id,
    const std::string &url,
    const std::string &version,
    std::size_t expected_size,
    const std::string &expected_sha256,
    StatusCallback status_callback
);
bool in_progress();
bool network_busy();
void confirm_running_image();

}  // namespace roomhub::ota
