import asyncio

from app.agent.workflow.actors import AgentActorRegistry


def test_same_actor_turns_are_serialized_but_different_actors_can_run():
    async def run():
        registry = AgentActorRegistry()
        active = 0
        maximum = 0
        order = []
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def worker(actor, name):
            nonlocal active, maximum
            async with registry.lease(actor):
                active += 1
                maximum = max(maximum, active)
                order.append(name)
                if name == "a1":
                    first_entered.set()
                    await release_first.wait()
                active -= 1

        first = asyncio.create_task(worker("actor-a", "a1"))
        await first_entered.wait()
        second = asyncio.create_task(worker("actor-a", "a2"))
        other = asyncio.create_task(worker("actor-b", "b1"))
        await asyncio.sleep(0)
        assert order == ["a1", "b1"]
        release_first.set()
        await asyncio.gather(first, second, other)
        assert order == ["a1", "b1", "a2"]
        assert maximum == 2

    asyncio.run(run())
