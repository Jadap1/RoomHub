#include "roomhub/version_policy.hpp"

#include <array>
#include <charconv>
#include <string>

namespace roomhub::firmware {
namespace {
bool parse(const std::string &value, std::array<unsigned int, 3> &parts)
{
    std::size_t start = 0;
    for (std::size_t index = 0; index < parts.size(); ++index) {
        const std::size_t end = value.find('.', start);
        if ((index < 2 && end == std::string::npos)
            || (index == 2 && end != std::string::npos)) return false;
        const std::size_t stop = end == std::string::npos ? value.size() : end;
        if (stop == start) return false;
        const char *first = value.data() + start;
        const char *last = value.data() + stop;
        const auto result = std::from_chars(first, last, parts[index]);
        if (result.ec != std::errc{} || result.ptr != last) return false;
        start = stop + 1;
    }
    return true;
}
}  // namespace

bool is_upgrade(const std::string &running, const std::string &candidate)
{
    std::array<unsigned int, 3> current{};
    std::array<unsigned int, 3> proposed{};
    return parse(running, current) && parse(candidate, proposed) && proposed > current;
}
}  // namespace roomhub::firmware
