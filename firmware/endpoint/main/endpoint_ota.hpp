#pragma once

#include <cstddef>
#include <string>

namespace roomhub::ota {

bool start(
    const std::string &url,
    const std::string &version,
    std::size_t expected_size,
    const std::string &expected_sha256
);
bool in_progress();
void confirm_running_image();

}  // namespace roomhub::ota
