from agents.conditional import ConditionalAgent
from agents.sub_agents.code_analyzer import code_analyzer_agent
from agents.utils.predicates import is_code_issue


def create_conditional_code_analyzer():
    """Create a conditional code analyzer that only runs for code issues."""

    return ConditionalAgent(
        name="ConditionalCodeAnalyzer",
        predicate=is_code_issue,
        sub_agents=[code_analyzer_agent],
        skip_message="Incident type is not 'code_issue'; skipping code analysis.",
    )

