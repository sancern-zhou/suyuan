package com.suyuan.mobile

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 大屏受限 WebView 的白名单与入口 URL 纯函数测试。
 * 红线：跨域一律拒绝；令牌只进首屏 URL；路径穿越/非法配置返回 null。
 */
class DashboardAccessTest {

    private val webBase = "https://xuchang.example.com"

    @Test
    fun sameHostIsAllowedRegardlessOfPath() {
        assertTrue(isAllowedDashboardHost(webBase, "https://xuchang.example.com/fieldwatch?access_token=t"))
        assertTrue(isAllowedDashboardHost(webBase, "https://xuchang.example.com/assets/x.js"))
        assertTrue(isAllowedDashboardHost(webBase, "https://xuchang.example.com/api/xuchang-dashboard/screen-snapshot"))
        // 大屏页面内部整页导航（如守卫跳转）也在同域内放行
        assertTrue(isAllowedDashboardHost(webBase, "https://xuchang.example.com/login"))
    }

    @Test
    fun crossHostAndLookalikeHostsAreRejected() {
        assertFalse(isAllowedDashboardHost(webBase, "https://evil.example.com/fieldwatch"))
        // 大小写归一化后仍须精确匹配 host，前缀相似不等于同 host
        assertFalse(isAllowedDashboardHost(webBase, "https://xuchang.example.com.evil.net/fieldwatch"))
        assertFalse(isAllowedDashboardHost(webBase, "https://127.0.0.1/fieldwatch"))
        // 相对地址无法判定 host，一律拒绝（导航拦截应保守）
        assertFalse(isAllowedDashboardHost(webBase, "/fieldwatch"))
        assertFalse(isAllowedDashboardHost(webBase, ""))
    }

    @Test
    fun hostComparisonIsCaseInsensitive() {
        assertTrue(isAllowedDashboardHost("https://Xuchang.Example.com", "https://xuchang.example.com/fieldwatch"))
        assertTrue(isAllowedDashboardHost(webBase, "https://XUCHANG.EXAMPLE.COM/bigscreen"))
    }

    @Test
    fun entryUrlJoinsTokenOnlyForFirstScreen() {
        assertEquals(
            "https://xuchang.example.com/fieldwatch?access_token=secret-token",
            dashboardEntryUrl(webBase, "/fieldwatch", "secret-token")
        )
        // 无令牌（部署未配置）仍可生成入口 URL，交给后端网关登录兜底
        assertEquals(
            "https://xuchang.example.com/fieldwatch",
            dashboardEntryUrl(webBase, "/fieldwatch", "")
        )
        assertEquals(
            "https://xuchang.example.com/bigscreen?access_token=t",
            dashboardEntryUrl(webBase, "/bigscreen", "t")
        )
    }

    @Test
    fun entryUrlRejectsInvalidBaseOrPath() {
        // 前端地址未配置（无 host）
        assertNull(dashboardEntryUrl("", "/fieldwatch", "t"))
        assertNull(dashboardEntryUrl("not-a-url", "/fieldwatch", "t"))
        // 非法 path
        assertNull(dashboardEntryUrl(webBase, "fieldwatch", "t"))
        assertNull(dashboardEntryUrl(webBase, "/fieldwatch/../admin", "t"))
        assertNull(dashboardEntryUrl(webBase, "//evil.example.com/x", "t"))
    }

    @Test
    fun entryUrlTrimsTrailingSlashOnBase() {
        assertEquals(
            "https://xuchang.example.com/fieldwatch",
            dashboardEntryUrl("https://xuchang.example.com/", "/fieldwatch", "")
        )
    }
}
