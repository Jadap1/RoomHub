#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

#include "roomhub/endpoint_config.hpp"

namespace roomhub::transport {

struct StartResult {
    bool connected = false;
    bool registered = false;
};

enum class VoiceResponseState {
    pending,
    ready,
    failed,
};

struct VoiceResponse {
    std::string speech_url;
    std::string mime_type;
};

StartResult start(const roomhub::config::EndpointConfig &config);
bool start_voice_audio();
bool send_voice_audio(const std::int16_t *samples, std::size_t byte_count);
bool end_voice_audio();
bool cancel_voice_audio();
VoiceResponseState voice_response_state();
VoiceResponse take_voice_response();

}  // namespace roomhub::transport
