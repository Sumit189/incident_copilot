from google.adk.agents import SequentialAgent, ParallelAgent
from google.adk.apps import App
from google.adk.plugins.logging_plugin import LoggingPlugin

from dotenv import load_dotenv
import logging
import os

load_dotenv()

# Import subagents
from agents.sub_agents import (
    incident_detection_agent,
    rca_agent,
    suggestion_agent,
    email_writer_agent,
    create_conditional_workflow,
    create_incident_only_agent,
)
from agents.sub_agents.code_analyzer_conditional import create_conditional_code_analyzer
from agents.sub_agents.solution_pr_conditional import create_conditional_solution_pr_workflow

from custom_plugins.event_tracer_plugin import EventTracerPlugin

conditional_code_analyzer = create_conditional_code_analyzer()
parallel_analysis_agent = ParallelAgent(
    name="ParallelAnalysisAgent",
    sub_agents=[rca_agent, suggestion_agent],
)
conditional_solution_pr_workflow = create_conditional_solution_pr_workflow()

conditional_email_agent = create_incident_only_agent(
    email_writer_agent,
    name="ConditionalEmailWriter",
    skip_message="No incident detected; skipping EmailWriterAgent.",
)

incident_response = [
    conditional_code_analyzer,
    parallel_analysis_agent,
    conditional_solution_pr_workflow,
]

root_agent = SequentialAgent(
    name="E2EIncidentWorkflow",
    sub_agents=[
        incident_detection_agent,
        create_conditional_workflow(incident_response),
        conditional_email_agent,
    ]
)

def _get_env(*names: str):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


plugins = [
    LoggingPlugin(),
]

mongo_uri = _get_env("MONGODB_URI")
mongo_db = _get_env("MONGODB_TRACE_DB_NAME", "MONGODB_DB_NAME")
mongo_coll = _get_env("MONGODB_TRACE_COLL_NAME", "MONGODB_COLL_TRACE_NAME")

custom_tracer = EventTracerPlugin(
    mongo_uri=mongo_uri,
    db_name=mongo_db,
    coll_name=mongo_coll,
)
plugins.append(custom_tracer)

if not all([mongo_uri, mongo_db, mongo_coll]):
    missing = [
        name
        for name, value in [
            ("MONGODB_URI", mongo_uri),
            ("MONGODB_TRACE_DB_NAME|MONGODB_DB_NAME", mongo_db),
            ("MONGODB_TRACE_COLL_NAME|MONGODB_COLL_TRACE_NAME", mongo_coll),
        ]
        if not value
    ]
    logging.warning(
        "EventTracerPlugin Mongo persistence disabled; missing env vars: %s",
        ", ".join(missing),
    )


# Build App WITH plugins
app = App(
    name="agents",
    root_agent=root_agent,
    plugins=plugins,
)

__all__ = ["app", "root_agent"]
