#include "tab5_camera.hpp"

#include <array>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <vector>

#include "bsp/m5stack_tab5.h"
#include "driver/jpeg_encode.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_video_init.h"
#include "esp_video_device.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "linux/videodev2.h"

namespace roomhub::board {
namespace {

constexpr char kTag[] = "tab5_camera";
constexpr std::size_t kBufferCount = 2;
std::atomic_bool capture_active{false};

struct CaptureRequest {
    std::string roomhub_url;
    std::string upload_path;
    std::string upload_token;
    std::string request_id;
};

std::string upload_url(const CaptureRequest &request)
{
    std::string base = request.roomhub_url;
    while (!base.empty() && base.back() == '/') base.pop_back();
    return base + (request.upload_path.empty() || request.upload_path.front() != '/' ? "/" : "")
        + request.upload_path;
}

bool encode_jpeg(
    const std::uint8_t *raw,
    std::size_t raw_size,
    unsigned width,
    unsigned height,
    std::vector<std::uint8_t> &image
)
{
    jpeg_encoder_handle_t encoder = nullptr;
    jpeg_encode_engine_cfg_t engine_config = {
        .intr_priority = 0,
        .timeout_ms = 250,
    };
    if (jpeg_new_encoder_engine(&engine_config, &encoder) != ESP_OK) return false;

    jpeg_encode_memory_alloc_cfg_t memory_config = {
        .buffer_direction = JPEG_ENC_ALLOC_OUTPUT_BUFFER,
    };
    std::size_t output_capacity = 0;
    auto *output = static_cast<std::uint8_t *>(
        jpeg_alloc_encoder_mem(raw_size, &memory_config, &output_capacity)
    );
    if (output == nullptr) {
        jpeg_del_encoder_engine(encoder);
        return false;
    }

    jpeg_encode_cfg_t config = {
        .height = height,
        .width = width,
        .src_type = JPEG_ENCODE_IN_FORMAT_RGB565,
        .sub_sample = JPEG_DOWN_SAMPLING_YUV422,
        .image_quality = 70,
    };
    std::uint32_t encoded_size = 0;
    const esp_err_t result = jpeg_encoder_process(
        encoder, &config, raw, raw_size, output, output_capacity, &encoded_size
    );
    if (result == ESP_OK && encoded_size > 0) {
        image.assign(output, output + encoded_size);
    }
    free(output);
    jpeg_del_encoder_engine(encoder);
    return result == ESP_OK && !image.empty();
}

bool capture_jpeg(std::vector<std::uint8_t> &image)
{
    if (bsp_camera_start(nullptr) != ESP_OK) {
        ESP_LOGE(kTag, "Could not initialise the camera");
        return false;
    }

    int fd = open(BSP_CAMERA_DEVICE, O_RDWR);
    bool streaming = false;
    std::array<void *, kBufferCount> buffers{};
    std::array<std::size_t, kBufferCount> buffer_sizes{};
    bool success = false;
    const int type = V4L2_BUF_TYPE_VIDEO_CAPTURE;

    if (fd < 0) goto cleanup;
    {
        v4l2_format format{};
        format.type = type;
        if (ioctl(fd, VIDIOC_G_FMT, &format) != 0) goto cleanup;
        if (format.fmt.pix.pixelformat == V4L2_PIX_FMT_RGB565X) {
            format.fmt.pix.pixelformat = V4L2_PIX_FMT_RGB565;
            if (ioctl(fd, VIDIOC_S_FMT, &format) != 0) goto cleanup;
        }
        if (format.fmt.pix.pixelformat != V4L2_PIX_FMT_RGB565) goto cleanup;

        v4l2_requestbuffers requested{};
        requested.count = kBufferCount;
        requested.type = type;
        requested.memory = V4L2_MEMORY_MMAP;
        if (ioctl(fd, VIDIOC_REQBUFS, &requested) != 0
            || requested.count < kBufferCount) goto cleanup;

        for (std::size_t index = 0; index < kBufferCount; ++index) {
            v4l2_buffer buffer{};
            buffer.type = type;
            buffer.memory = V4L2_MEMORY_MMAP;
            buffer.index = index;
            if (ioctl(fd, VIDIOC_QUERYBUF, &buffer) != 0) goto cleanup;
            buffers[index] = mmap(
                nullptr, buffer.length, PROT_READ | PROT_WRITE,
                MAP_SHARED, fd, buffer.m.offset
            );
            if (buffers[index] == MAP_FAILED) {
                buffers[index] = nullptr;
                goto cleanup;
            }
            buffer_sizes[index] = buffer.length;
            if (ioctl(fd, VIDIOC_QBUF, &buffer) != 0) goto cleanup;
        }

        if (ioctl(fd, VIDIOC_STREAMON, &type) != 0) goto cleanup;
        streaming = true;
        for (unsigned frame = 0; frame < 4; ++frame) {
            v4l2_buffer buffer{};
            buffer.type = type;
            buffer.memory = V4L2_MEMORY_MMAP;
            if (ioctl(fd, VIDIOC_DQBUF, &buffer) != 0) goto cleanup;
            if (frame == 3 && (buffer.flags & V4L2_BUF_FLAG_DONE) != 0) {
                success = encode_jpeg(
                    static_cast<const std::uint8_t *>(buffers[buffer.index]),
                    buffer.bytesused,
                    format.fmt.pix.width,
                    format.fmt.pix.height,
                    image
                );
            }
            if (ioctl(fd, VIDIOC_QBUF, &buffer) != 0) goto cleanup;
        }
    }

cleanup:
    if (streaming) ioctl(fd, VIDIOC_STREAMOFF, &type);
    for (std::size_t index = 0; index < kBufferCount; ++index) {
        if (buffers[index] != nullptr) munmap(buffers[index], buffer_sizes[index]);
    }
    if (fd >= 0) close(fd);
    esp_video_deinit();
    bsp_feature_enable(BSP_FEATURE_CAMERA, false);
    return success;
}

bool upload_jpeg(const CaptureRequest &request, const std::vector<std::uint8_t> &image)
{
    const std::string url = upload_url(request);
    esp_http_client_config_t config{};
    config.url = url.c_str();
    config.method = HTTP_METHOD_PUT;
    config.timeout_ms = 10000;
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == nullptr) return false;
    esp_http_client_set_header(client, "Content-Type", "image/jpeg");
    esp_http_client_set_header(client, "X-RoomHub-Camera-Token", request.upload_token.c_str());

    bool success = esp_http_client_open(client, image.size()) == ESP_OK;
    std::size_t written = 0;
    while (success && written < image.size()) {
        const int result = esp_http_client_write(
            client,
            reinterpret_cast<const char *>(image.data() + written),
            image.size() - written
        );
        if (result <= 0) success = false;
        else written += static_cast<std::size_t>(result);
    }
    if (success) {
        esp_http_client_fetch_headers(client);
        const int status = esp_http_client_get_status_code(client);
        success = status >= 200 && status < 300;
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return success;
}

void capture_task(void *argument)
{
    auto *request = static_cast<CaptureRequest *>(argument);
    std::vector<std::uint8_t> image;
    const bool captured = capture_jpeg(image);
    const bool uploaded = captured && upload_jpeg(*request, image);
    ESP_LOGI(
        kTag, "Camera request %s %s (%u bytes)", request->request_id.c_str(),
        uploaded ? "uploaded" : "failed", static_cast<unsigned>(image.size())
    );
    delete request;
    capture_active = false;
    vTaskDelete(nullptr);
}

}

bool start_tab5_camera_capture(
    const std::string &roomhub_url,
    const std::string &upload_path,
    const std::string &upload_token,
    const std::string &request_id
)
{
    bool expected = false;
    if (!capture_active.compare_exchange_strong(expected, true)) return false;
    auto *request = new (std::nothrow) CaptureRequest{
        roomhub_url, upload_path, upload_token, request_id
    };
    if (request == nullptr || xTaskCreate(
        capture_task, "roomhub_camera", 8192, request, 5, nullptr
    ) != pdPASS) {
        delete request;
        capture_active = false;
        return false;
    }
    return true;
}

}
