"""
Sub-agents for Incident CoPilot.

Each sub-agent is a specialized agent that handles a specific part of the incident response workflow.
"""

from agents.sub_agents.incident_detection import incident_detection_agent
from agents.sub_agents.rca import rca_agent
from agents.sub_agents.suggestion import suggestion_agent
from agents.sub_agents.post_process import post_process_agent
from agents.sub_agents.code_analyzer import code_analyzer_agent
from agents.sub_agents.solution_generator import solution_generator_agent
from agents.sub_agents.pr_executor import pr_executor_agent
from agents.sub_agents.pr_file_updater import file_updater_agent
from agents.sub_agents.pr_creator import pr_creator_agent
from agents.sub_agents.workflow_guard import create_conditional_workflow, create_incident_only_agent
from agents.sub_agents.code_analyzer_conditional import create_conditional_code_analyzer
from agents.sub_agents.solution_pr_conditional import create_conditional_solution_pr_workflow

__all__ = [
    "incident_detection_agent",
    "rca_agent",
    "suggestion_agent",
    "post_process_agent",
    "code_analyzer_agent",
    "solution_generator_agent",
    "pr_executor_agent",
    "file_updater_agent",
    "pr_creator_agent",
    "create_conditional_workflow",
    "create_incident_only_agent",
    "create_conditional_code_analyzer",
    "create_conditional_solution_pr_workflow",
]
