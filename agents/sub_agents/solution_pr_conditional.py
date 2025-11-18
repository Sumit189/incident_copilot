"""
Conditional Solution and PR workflow driven by incident detection + solution output.
"""

from google.adk.agents import SequentialAgent

from agents.conditional import ConditionalAgent
from agents.sub_agents.solution_generator import solution_generator_agent
from agents.sub_agents.pr_executor import pr_executor_agent
from agents.utils.predicates import is_code_issue, is_patch_ready


def create_conditional_solution_pr_workflow():
    """Run solution + PR execution only when we have a code issue and a patch."""

    solution_and_pr_workflow = SequentialAgent(
        name="SolutionAndPRWorkflow",
        sub_agents=[
            solution_generator_agent,
            ConditionalAgent(
                name="ConditionalPRExecutor",
                predicate=is_patch_ready,
                sub_agents=[pr_executor_agent],
                skip_message="SolutionGeneratorAgent did not produce a patch; skipping PR executor.",
            ),
        ],
    )

    return ConditionalAgent(
        name="ConditionalSolutionPRWorkflow",
        predicate=is_code_issue,
        sub_agents=[solution_and_pr_workflow],
        skip_message="Incident is not classified as code_issue; skipping solution + PR workflow.",
    )

