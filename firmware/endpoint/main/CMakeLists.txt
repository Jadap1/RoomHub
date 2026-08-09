idf_component_register(
    SRCS "app_main.cpp" "roomhub_transport.cpp" "tab5_audio_playback.cpp" "tab5_audio_service.cpp" "tab5_bringup.cpp" "tab5_wake_word.cpp" "tab5_wireless.cpp" "usb_provisioning.cpp"
    INCLUDE_DIRS "."
    REQUIRES roomhub_audio roomhub_config roomhub_recovery roomhub_voice
    PRIV_REQUIRES esp_event esp_http_client esp_netif esp_system esp_wifi json mbedtls
)
