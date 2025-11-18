import logging

from agents.conditional import ConditionalAgent
from agents.utils.predicates import is_incident_confirmed


def create_conditional_workflow(incident_response_agents):
    """Return a conditional workflow driven by the last IncidentDetectionAgent output."""

    return ConditionalAgent(
        name="ConditionalIncidentWorkflow",
        predicate=is_incident_confirmed,
        sub_agents=incident_response_agents,
        skip_message="IncidentDetectionAgent reported no incident; skipping follow-up agents.",
    )


def create_incident_only_agent(agent, *, name=None, skip_message=None):
    """Wrap a single agent so it only runs when an incident is confirmed."""

    wrapper_name = name or f"Conditional{agent.name}"
    wrapper_skip = skip_message or f"IncidentDetectionAgent reported no incident; skipping {agent.name}."

    return ConditionalAgent(
        name=wrapper_name,
        predicate=is_incident_confirmed,
        sub_agents=[agent],
        skip_message=wrapper_skip,
    )

