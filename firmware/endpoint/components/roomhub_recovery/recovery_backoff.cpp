#include "roomhub/recovery_backoff.hpp"

#include <algorithm>

namespace roomhub::recovery {

Backoff::Backoff(std::uint32_t initial_ms, std::uint32_t maximum_ms)
    : initial_ms_(std::max<std::uint32_t>(1, initial_ms)),
      maximum_ms_(std::max(initial_ms_, maximum_ms)),
      current_ms_(initial_ms_)
{
}

std::uint32_t Backoff::next_delay_ms()
{
    const std::uint32_t result = current_ms_;
    current_ms_ = current_ms_ >= maximum_ms_ / 2
        ? maximum_ms_ : current_ms_ * 2;
    return result;
}

void Backoff::reset()
{
    current_ms_ = initial_ms_;
}

std::uint32_t Backoff::current_delay_ms() const
{
    return current_ms_;
}

}  // namespace roomhub::recovery
