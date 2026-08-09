#pragma once

#include <string>

namespace roomhub::firmware {
bool is_upgrade(const std::string &running, const std::string &candidate);
}  // namespace roomhub::firmware
