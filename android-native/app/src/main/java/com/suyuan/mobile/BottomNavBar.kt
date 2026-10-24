package com.suyuan.mobile

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.isImeVisible
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 对话 tab 的常驻底栏；键盘弹出时整体隐藏（微信式），避免顶跳输入区。 */
@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
internal fun BottomNavBar(currentTab: String, showWatch: Boolean, taskBadge: Int, onTab: (String) -> Unit) {
    if (WindowInsets.isImeVisible) return
    NavigationBar(
        containerColor = Color.White,
        tonalElevation = 0.dp,
        modifier = Modifier.fillMaxWidth()
    ) {
        NavigationBarItem(
            selected = currentTab == "chat",
            onClick = { onTab("chat") },
            icon = { TabIcon(R.drawable.ic_tab_chat, "对话", badge = 0) },
            label = { Text("对话") },
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
                icon = { TabIcon(R.drawable.ic_campaign, "巡查快报", badge = 0) },
                label = { Text("巡查快报") },
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
            icon = { TabIcon(R.drawable.ic_history, "任务", badge = taskBadge) },
            label = { Text("任务") },
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

/** 任务 tab 内的子切换（定时任务 | 广播消息）；广播未读角标挂在子切换钮上。 */
@Composable
internal fun TasksSubTabRow(selected: String, broadcastBadge: Int, onSelect: (String) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = 12.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        listOf("reports" to "定时任务", "broadcasts" to "广播消息").forEach { (key, label) ->
            Box {
                Surface(
                    color = if (selected == key) SuyuanColors.primary.copy(alpha = 0.12f) else SuyuanColors.panel,
                    shape = RoundedCornerShape(16.dp),
                    modifier = Modifier.clickable { onSelect(key) }
                ) {
                    Text(
                        label,
                        color = if (selected == key) SuyuanColors.primary else SuyuanColors.text,
                        fontSize = 13.sp,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)
                    )
                }
                if (key == "broadcasts" && broadcastBadge > 0) {
                    Box(
                        Modifier
                            .size(8.dp)
                            .background(SuyuanColors.error, CircleShape)
                            .align(Alignment.TopEnd)
                    )
                }
            }
        }
    }
}
