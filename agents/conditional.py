import logging
from typing import Callable, Sequence

from google.adk.agents import SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext


Predicate = Callable[[InvocationContext], bool]


class ConditionalAgent(SequentialAgent):
    """Runs wrapped sub-agents only when the predicate evaluates to True."""

    def __init__(
        self,
        *,
        name: str,
        predicate: Predicate,
        sub_agents: Sequence[BaseAgent],
        skip_message: str | None = None,
    ):
        super().__init__(name=name, sub_agents=list(sub_agents))
        self._predicate = predicate
        self._skip_message = skip_message or f"{name} predicate evaluated to False; skipping."

    async def _run_async_impl(self, ctx: InvocationContext):
        if not self._predicate(ctx):
            logging.info("[ConditionalAgent:%s] %s", self.name, self._skip_message)
            return

        async for event in super()._run_async_impl(ctx):
            yield event

