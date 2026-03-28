#!/usr/bin/env python3
"""
快速诊断 ChannelManager 和 MessageBus 的状态
"""

import asyncio
import sys
import os
sys.path.insert(0, '/home/xckj/suyuan/backend')
os.chdir('/home/xckj/suyuan/backend')

from app.social.message_bus import MessageBus
from app.social.config import load_social_config
from app.channels.manager import ChannelManager

async def main():
    print("=" * 60)
    print("ChannelManager 和 MessageBus 诊断")
    print("=" * 60)

    # 1. 加载配置
    config = load_social_config()
    print(f"\n1. 配置加载:")
    print(f"   微信启用: {config.weixin.enabled}")
    print(f"   微信账号数量: {len(config.weixin.accounts)}")
    for acc in config.weixin.accounts:
        print(f"     - {acc.id}: {acc.name} (enabled={acc.enabled})")

    # 2. 创建 MessageBus
    bus = MessageBus()
    print(f"\n2. MessageBus 创建:")
    print(f"   入站队列大小: {bus.inbound_size}")
    print(f"   出站队列大小: {bus.outbound_size}")

    # 3. 创建 ChannelManager
    manager = ChannelManager(config=config, bus=bus)
    print(f"\n3. ChannelManager 创建:")
    print(f"   渠道数量: {len(manager.channels)}")
    for key, channel in manager.channels.items():
        print(f"     - {key}")
        print(f"       类型: {type(channel).__name__}")
        print(f"       运行中: {channel.is_running}")
        print(f"       机器人账号: {channel.bot_account}")

    # 4. 检查是否有 auto_mn88papa 账号
    print(f"\n4. 检查 weixin:auto_mn88papa:")
    target_key = "weixin:auto_mn88papa"
    if target_key in manager.channels:
        print(f"   ✓ 找到渠道: {target_key}")
        channel = manager.channels[target_key]
        print(f"     实例ID: {channel.instance_id}")
        print(f"     Token: {channel._token[:20] if channel._token else '(无)'}...")
    else:
        print(f"   ✗ 未找到渠道: {target_key}")
        print(f"   可用渠道: {list(manager.channels.keys())}")

    # 5. 测试消息路由
    print(f"\n5. 测试消息路由:")
    from app.social.events import OutboundMessage
    test_msg = OutboundMessage(
        channel=target_key,
        chat_id="o9cq804zfK_aJ137yI6dIZSvF1Zg@im.wechat",
        content="测试消息",
        reply_to="o9cq804zfK_aJ137yI6dIZSvF1Zg@im.wechat"
    )

    await bus.publish_outbound(test_msg)
    print(f"   已发布测试消息到出站队列")
    print(f"   出站队列大小: {bus.outbound_size}")

    # 尝试消费消息
    try:
        msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
        print(f"   ✓ 成功消费出站消息")
        print(f"     渠道: {msg.channel}")
        print(f"     内容: {msg.content[:50]}")

        # 检查路由
        target_channel = manager.channels.get(msg.channel)
        if target_channel:
            print(f"   ✓ 找到目标渠道: {target_channel.name}")
        else:
            print(f"   ✗ 未找到目标渠道: {msg.channel}")
            print(f"   可用渠道: {list(manager.channels.keys())}")
    except asyncio.TimeoutError:
        print(f"   ✗ 消费消息超时")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
