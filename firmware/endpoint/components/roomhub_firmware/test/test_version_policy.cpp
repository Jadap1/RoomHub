#include "unity.h"
#include "roomhub/version_policy.hpp"

TEST_CASE("firmware policy accepts a newer semantic version", "[firmware]")
{
    TEST_ASSERT_TRUE(roomhub::firmware::is_upgrade("0.2.1", "0.3.0"));
    TEST_ASSERT_TRUE(roomhub::firmware::is_upgrade("0.2.9", "0.2.10"));
}

TEST_CASE("firmware policy rejects same older and malformed versions", "[firmware]")
{
    TEST_ASSERT_FALSE(roomhub::firmware::is_upgrade("0.2.1", "0.2.1"));
    TEST_ASSERT_FALSE(roomhub::firmware::is_upgrade("0.2.1", "0.2.0"));
    TEST_ASSERT_FALSE(roomhub::firmware::is_upgrade("0.2.1", "0.3"));
    TEST_ASSERT_FALSE(roomhub::firmware::is_upgrade("0.2.1", "0.3.0-beta"));
}
