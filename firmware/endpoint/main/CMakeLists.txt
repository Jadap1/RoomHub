idf_component_register(
    SRCS "app_main.cpp" "tab5_bringup.cpp" "tab5_wake_word.cpp"
    INCLUDE_DIRS "."
    REQUIRES roomhub_config roomhub_voice
)
