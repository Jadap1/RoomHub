#include "unity.h"
#include "roomhub/recovery_backoff.hpp"

TEST_CASE("recovery backoff doubles and remains bounded", "[recovery]")
{
    roomhub::recovery::Backoff backoff(1000, 30000);
    TEST_ASSERT_EQUAL_UINT32(1000, backoff.next_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(2000, backoff.next_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(4000, backoff.next_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(8000, backoff.next_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(16000, backoff.next_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(30000, backoff.next_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(30000, backoff.next_delay_ms());
}

TEST_CASE("successful recovery resets the backoff", "[recovery]")
{
    roomhub::recovery::Backoff backoff(500, 5000);
    backoff.next_delay_ms();
    backoff.next_delay_ms();
    backoff.reset();
    TEST_ASSERT_EQUAL_UINT32(500, backoff.current_delay_ms());
    TEST_ASSERT_EQUAL_UINT32(500, backoff.next_delay_ms());
}
