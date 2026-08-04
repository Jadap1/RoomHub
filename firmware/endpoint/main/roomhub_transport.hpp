#pragma once

#include "roomhub/endpoint_config.hpp"

namespace roomhub::transport {

struct StartResult {
    bool connected = false;
    bool registered = false;
};

StartResult start(const roomhub::config::EndpointConfig &config);

}  // namespace roomhub::transport
