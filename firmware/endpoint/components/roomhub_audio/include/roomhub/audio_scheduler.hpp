#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
namespace roomhub::audio {
enum class Priority : std::uint8_t { notification=100, media=150, voice_assistant=200, intercom=230, emergency=255 };
struct Item { std::uint32_t token=0; Priority priority=Priority::notification; };
enum class SubmitAction { rejected, queued, start, interrupt };
struct SubmitResult { SubmitAction action=SubmitAction::rejected; std::uint32_t interrupted_token=0; };
class Scheduler {
public:
    static constexpr std::size_t capacity=8;
    SubmitResult submit(Item item);
    bool cancel(std::uint32_t token);
    bool complete(std::uint32_t token);
    bool has_active() const;
    Item active() const;
    std::size_t queued() const;
private:
    void start_next();
    Item active_{}; bool has_active_=false;
    std::array<Item, capacity> queue_{}; std::size_t queued_=0;
};
}  // namespace roomhub::audio
