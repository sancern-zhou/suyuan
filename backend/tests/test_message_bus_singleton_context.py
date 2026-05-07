import asyncio

from app.social.message_bus_singleton import (
    get_current_bot_account,
    get_current_channel,
    get_current_chat_id,
    reset_current_context,
    set_current_context,
)


def test_social_context_is_isolated_between_async_tasks():
    async def worker(channel: str, chat_id: str, bot_account: str, delay: float):
        tokens = set_current_context(
            channel=channel,
            chat_id=chat_id,
            bot_account=bot_account,
        )
        try:
            await asyncio.sleep(delay)
            return (
                get_current_channel(),
                get_current_chat_id(),
                get_current_bot_account(),
            )
        finally:
            reset_current_context(tokens)

    async def run():
        return await asyncio.gather(
            worker("weixin:auto_a", "chat_a", "bot_a", 0.02),
            worker("qq", "chat_b", "bot_b", 0.01),
        )

    assert asyncio.run(run()) == [
        ("weixin:auto_a", "chat_a", "bot_a"),
        ("qq", "chat_b", "bot_b"),
    ]
