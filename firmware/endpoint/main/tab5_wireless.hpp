#pragma once

#include <cstdint>

namespace roomhub::board {

struct Tab5WirelessScanResult {
    bool radio_ready = false;
    std::uint16_t network_count = 0;
};

bool power_on_tab5_wireless();
Tab5WirelessScanResult scan_tab5_wifi();

}  // namespace roomhub::board
