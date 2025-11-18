from google.adk.agents import SequentialAgent
from agents.sub_agents.pr_branch_creator import branch_creator_agent
from agents.sub_agents.pr_file_updater import file_updater_agent
from agents.sub_agents.pr_creator import pr_creator_agent


def _create_pr_executor_agent():
    """Create PR Executor as a SequentialAgent that runs branch creation, file updates, and PR creation in sequence."""
    return SequentialAgent(
        name="PRExecutorAgent",
        sub_agents=[
            branch_creator_agent,
            file_updater_agent,
            pr_creator_agent
        ]
    )

pr_executor_agent = _create_pr_executor_agent()
