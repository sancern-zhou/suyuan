package com.suyuan.mobile

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 对话 tab 的常驻底栏；键盘弹出占位时滑出隐藏（微信式），避免顶跳输入区。隐藏信号的取法见调用方。 */
@Composable
internal fun BottomNavBar(
    currentTab: String,
    showWatch: Boolean,
    taskBadge: Int,
    hidden: Boolean,
    onTab: (String) -> Unit
) {
    AnimatedVisibility(
        visible = !hidden,
        enter = slideInVertically { it } + fadeIn(),
        exit = slideOutVertically { it } + fadeOut()
    ) {
        // 紧凑纯图标形态（56dp）：底部 tab 即标题，无文字；输入框贴近拇指热区。
        NavigationBar(
            containerColor = Color.White,
            tonalElevation = 0.dp,
            modifier = Modifier.fillMaxWidth().height(56.dp)
        ) {
        NavigationBarItem(
            selected = currentTab == "chat",
            onClick = { onTab("chat") },
            icon = { TabIcon(R.drawable.ic_tab_chat, "对话", badge = 0) },

            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = SuyuanColors.primary,
                selectedTextColor = SuyuanColors.primary,
                unselectedIconColor = SuyuanColors.secondaryText,
                unselectedTextColor = SuyuanColors.secondaryText,
                indicatorColor = SuyuanColors.primary.copy(alpha = 0.12f)
            )
        )
        if (showWatch) {
            NavigationBarItem(
                selected = currentTab == "watch",
                onClick = { onTab("watch") },
                icon = { TabIcon(R.drawable.ic_tab_monitor, "现状", badge = 0) },

                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = SuyuanColors.primary,
                    selectedTextColor = SuyuanColors.primary,
                    unselectedIconColor = SuyuanColors.secondaryText,
                    unselectedTextColor = SuyuanColors.secondaryText,
                    indicatorColor = SuyuanColors.primary.copy(alpha = 0.12f)
                )
            )
        }
        if (showWatch) {
            NavigationBarItem(
                selected = currentTab == "map",
                onClick = { onTab("map") },
                icon = { TabIcon(R.drawable.ic_tab_map, "实时地图", badge = 0) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = SuyuanColors.primary,
                    selectedTextColor = SuyuanColors.primary,
                    unselectedIconColor = SuyuanColors.secondaryText,
                    unselectedTextColor = SuyuanColors.secondaryText,
                    indicatorColor = SuyuanColors.primary.copy(alpha = 0.12f)
                )
            )
        }
        NavigationBarItem(
            selected = currentTab == "tasks",
            onClick = { onTab("tasks") },
            icon = { TabIcon(R.drawable.ic_tab_tasks, "任务", badge = taskBadge) },

            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = SuyuanColors.primary,
                selectedTextColor = SuyuanColors.primary,
                unselectedIconColor = SuyuanColors.secondaryText,
                unselectedTextColor = SuyuanColors.secondaryText,
                indicatorColor = SuyuanColors.primary.copy(alpha = 0.12f)
            )
        )
        }
    }
}

@Composable
private fun TabIcon(drawableRes: Int, contentDescription: String, badge: Int) {
    Box {
        Icon(
            painterResource(drawableRes),
            contentDescription = contentDescription,
            modifier = Modifier.size(24.dp)
        )
        if (badge > 0) {
            Box(
                Modifier
                    .size(8.dp)
                    .background(SuyuanColors.error, androidx.compose.foundation.shape.CircleShape)
                    .align(Alignment.TopEnd)
            )
        }
    }
}

/** 任务 tab 内的子切换（定时任务 | 广播消息）：分段控件样式，广播未读角标随标签。 */
@Composable
internal fun TasksSubTabRow(selected: String, broadcastBadge: Int, onSelect: (String) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 8.dp)
            .background(Color(0xFFEDEEF1), RoundedCornerShape(10.dp))
            .padding(2.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        listOf("reports" to "定时任务", "broadcasts" to "广播消息").forEach { (key, label) ->
            val active = selected == key
            Surface(
                color = if (active) Color.White else Color.Transparent,
                shape = RoundedCornerShape(8.dp),
                shadowElevation = if (active) 1.dp else 0.dp,
                modifier = Modifier
                    .weight(1f)
                    .clickable { onSelect(key) }
            ) {
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 7.dp),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        label,
                        color = if (active) SuyuanColors.text else SuyuanColors.secondaryText,
                        fontSize = 13.sp,
                        fontWeight = if (active) FontWeight.SemiBold else FontWeight.Normal
                    )
                    if (key == "broadcasts" && broadcastBadge > 0) {
                        Spacer(Modifier.size(5.dp))
                        Box(Modifier.size(6.dp).background(SuyuanColors.error, CircleShape))
                    }
                }
            }
        }
    }
}
