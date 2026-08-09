#pragma once

#include <cstdint>

namespace roomhub::recovery {

class Backoff {
public:
    Backoff(std::uint32_t initial_ms, std::uint32_t maximum_ms);
    std::uint32_t next_delay_ms();
    void reset();
    std::uint32_t current_delay_ms() const;

private:
    std::uint32_t initial_ms_;
    std::uint32_t maximum_ms_;
    std::uint32_t current_ms_;
};

}  // namespace roomhub::recovery
