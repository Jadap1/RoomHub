#pragma once

#include <string>

namespace roomhub::board {

bool start_tab5_camera_capture(
    const std::string &roomhub_url,
    const std::string &upload_path,
    const std::string &upload_token,
    const std::string &request_id
);

}
