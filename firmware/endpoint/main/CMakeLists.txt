idf_component_register(
    SRCS "app_main.cpp" "roomhub_transport.cpp" "tab5_bringup.cpp" "tab5_wake_word.cpp" "tab5_wireless.cpp" "usb_provisioning.cpp"
    INCLUDE_DIRS "."
    REQUIRES roomhub_config roomhub_voice
    PRIV_REQUIRES esp_event esp_netif esp_system esp_wifi json mbedtls
)
