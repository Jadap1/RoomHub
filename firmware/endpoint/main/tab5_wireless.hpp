#pragma once

#include <cstdint>
#include <string>

namespace roomhub::board {

struct Tab5WirelessScanResult {
    bool radio_ready = false;
    std::uint16_t network_count = 0;
};

struct Tab5WirelessConnectionResult {
    bool radio_ready = false;
    bool connected = false;
};

bool power_on_tab5_wireless();
Tab5WirelessScanResult scan_tab5_wifi();
Tab5WirelessConnectionResult connect_tab5_wifi(
    const std::string &ssid,
    const std::string &password
);

}  // namespace roomhub::board
