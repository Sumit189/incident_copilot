"""
Main orchestrator agent for Incident CoPilot.

This is the central agent that coordinates all sub-agents in the incident response workflow.
"""

import os
import json
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from google.adk.agents import SequentialAgent, ParallelAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.memory import InMemoryMemoryService
from google.adk.plugins.logging_plugin import LoggingPlugin
from google.genai import types

try:
    from google.adk.app import App
    HAS_APP_MODULE = True
except ImportError:
    HAS_APP_MODULE = False

from incident_copilot.config import APP_NAME
from incident_copilot.sub_agents import (
    incident_detection_agent,
    rca_agent,
    suggestion_agent,
    email_writer_agent,
    code_analyzer_agent,
    solution_generator_agent,
    pr_executor_agent,
    create_conditional_workflow
)
from incident_copilot.sub_agents.code_analyzer_conditional import create_conditional_code_analyzer
from incident_copilot.sub_agents.solution_pr_conditional import create_conditional_solution_pr_workflow
from incident_copilot.email_failover import compose_incident_email
from incident_copilot.tools import get_on_call_engineers, reset_pr_workflow_gate
from tools.email_helper import (
    reset_email_status,
    was_email_sent,
    get_last_email_status,
    send_incident_email,
)


# Services
session_service = InMemorySessionService()
memory_service = InMemoryMemoryService()

# Step 1: Log fetch and categorize (incident_detection_agent already does this)
# Step 2: Conditional code analyzer (only if code issue)
conditional_code_analyzer = create_conditional_code_analyzer()

# Step 3a: Parallel analysis (RCA and Suggestion can run in parallel)
parallel_analysis_agent = ParallelAgent(
    name="ParallelAnalysisAgent",
    sub_agents=[rca_agent, suggestion_agent]
)

# Step 3b: Conditional Solution and PR workflow (only if code issue)
# PR Executor MUST run after Solution Generator because it needs the patch
# This workflow is skipped if incident_type_hint is not "code_issue"
conditional_solution_pr_workflow = create_conditional_solution_pr_workflow()

# Step 4: Send email
# Create conditional workflow that checks incident detection before proceeding
# This ensures we only run the workflow if incident is detected
incident_response_agents = [
    conditional_code_analyzer,
    parallel_analysis_agent,
    conditional_solution_pr_workflow,
    email_writer_agent
]

conditional_workflow = create_conditional_workflow(incident_response_agents)

# Main workflow: Incident Detection -> Conditional Workflow
workflow = SequentialAgent(
    name="E2EIncidentWorkflow",
    sub_agents=[
        incident_detection_agent,
        conditional_workflow
    ]
)

# Export as root_agent for ADK Playground compatibility
root_agent = workflow

logging_plugin = LoggingPlugin()

if HAS_APP_MODULE:
    incident_app = App(
        name=APP_NAME,
        root_agent=workflow,
    )
    runner = Runner(
        app=incident_app,
        session_service=session_service,
        memory_service=memory_service,
        plugins=[logging_plugin]
    )
else:
    incident_app = None
    runner = Runner(
        app_name=APP_NAME,
        agent=workflow,
        session_service=session_service,
        memory_service=memory_service,
        plugins=[logging_plugin]
    )


async def run_workflow(
    user_id: str, 
    service: str, 
    start_time: str, 
    end_time: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run the E2E incident workflow.
    
    The workflow detects incidents, analyzes root causes, generates solutions,
    creates PRs for code patches, and sends email reports to on-call engineers.
    
    Args:
        user_id: User identifier
        service: Service name (for backward compatibility)
        start_time: Incident detection time (ISO 8601 format, e.g., "2025-11-14T11:00:00Z")
        end_time: Optional end time (defaults to start_time if not provided)
    
    Returns:
        Dict with workflow results
    """
    from incident_copilot.config import LOOKUP_WINDOW_SECONDS
    from datetime import datetime, timedelta
    
    # If end_time not provided, use start_time as end_time
    # The lookup window is handled by the Incident Detection Agent
    if end_time is None:
        end_time = start_time
    
    reset_email_status()
    reset_pr_workflow_gate()

    payload = {
        "start_time": start_time,
        "end_time": end_time
    }
    
    content = types.Content(parts=[types.Part(text=str(payload))], role="user")

    session_id = f"incident_{uuid.uuid4().hex[:8]}"

    session = await session_service.create_session(
        app_name=APP_NAME, 
        user_id=user_id,
        session_id=session_id
    )

    agent_responses = session.state.get("agent_responses")
    if not isinstance(agent_responses, dict):
        agent_responses = {}
        session.state["agent_responses"] = agent_responses

    def _append_agent_response(agent_name: Optional[str], content: Optional[str]) -> None:
        """Store per-agent responses (text or JSON) for downstream consumers."""
        if not content:
            return
        key = agent_name or "unknown"
        if key not in agent_responses:
            agent_responses[key] = []
        agent_responses[key].append(content)
    all_responses = []
    events = []
    
    print("\n[ORCHESTRATOR] Starting workflow execution...")
    print(f"[ORCHESTRATOR] User ID: {user_id}, Session ID: {session.id}")
    
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session.id,
        new_message=content
    ):
        events.append(event)
        
        event_type = type(event).__name__
        print(f"\n[ORCHESTRATOR] Event received: {event_type}")
        
        if hasattr(event, 'agent_name'):
            print(f"[ORCHESTRATOR] Agent: {event.agent_name}")
        
        if hasattr(event, 'content') and event.content:
            if hasattr(event.content, 'parts') and event.content.parts:
                for i, part in enumerate(event.content.parts):
                    print(f"[ORCHESTRATOR] Content part {i}: type={type(part).__name__}")
                    if hasattr(part, 'function_call'):
                        print(f"[ORCHESTRATOR] Function call in part {i}: {part.function_call}")
                    if hasattr(part, 'function_response'):
                        print(f"[ORCHESTRATOR] Function response in part {i}: {part.function_response}")
                        fr_payload = getattr(part.function_response, 'response', None)
                        if fr_payload is not None:
                            if isinstance(fr_payload, str):
                                serialized_response = fr_payload
                            else:
                                serialized_response = json.dumps(
                                    fr_payload,
                                    ensure_ascii=False,
                                    default=str
                                )
                            agent_for_record = getattr(event, 'agent_name', None) or getattr(
                                part.function_response, 'name', None
                            )
                            _append_agent_response(agent_for_record, serialized_response)
                    if hasattr(part, 'text'):
                        print(f"[ORCHESTRATOR] Text in part {i}: {part.text[:100] if part.text else 'None'}...")
        
        if event.is_final_response():
            print(f"[ORCHESTRATOR] Final response received")
            if event.content and event.content.parts:
                final = event.content.parts[0].text
                print(f"[ORCHESTRATOR] Final response text: {final[:200]}...")
                all_responses.append(final)
                
                agent_name = getattr(event, 'agent_name', 'unknown')
                _append_agent_response(agent_name, final)
            else:
                print("[ORCHESTRATOR] Warning: Final response has no content or parts")
                if hasattr(event, 'text'):
                    final = event.text
                    all_responses.append(final)
                    agent_name = getattr(event, 'agent_name', 'unknown')
                    _append_agent_response(agent_name, final)

    await memory_service.add_session_to_memory(session)

    email_report = None
    fallback_email_result = None
    if all_responses:
        email_report = all_responses[-1]

    email_content = compose_incident_email(agent_responses)
    if email_content and not was_email_sent():
        recipients = get_on_call_engineers()
        if recipients:
            print("[ORCHESTRATOR] Email not sent by agent. Triggering failover sender.")
            fallback_email_result = send_incident_email(
                to=recipients,
                subject=email_content["subject"],
                body=email_content["body"],
                pr_url=email_content.get("pr_url"),
                pr_number=email_content.get("pr_number"),
            )
            if fallback_email_result.get("status") == "sent":
                print("[ORCHESTRATOR] Failover email dispatched successfully.")
            else:
                print(f"[ORCHESTRATOR] Failover email attempt failed: {fallback_email_result.get('message')}")
            email_report = email_content["body"]
        else:
            print("[ORCHESTRATOR] Warning: No on-call recipients configured; unable to send fallback email.")
    
    output = {
        "incident_id": session.id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input": {
            "user_id": user_id,
            "service": service,
            "start_time": start_time,
            "end_time": end_time
        },
        "status": "completed",
        "agent_responses": agent_responses,
        "all_responses": all_responses,
        "email_report": email_report,
        "workflow_summary": {
            "incident_detection": "Completed - Fetched logs and categorized incident",
            "code_analyzer": "Completed - Found problematic code locations (if code issue)",
            "rca": "Completed - Performed root cause analysis (parallel with suggestion)",
            "suggestion": "Completed - Generated fix suggestions (parallel with RCA)",
            "solution_generator": "Completed - Generated solutions and patch code (sequential after RCA/suggestion)",
            "pr_executor": "Completed - Created PR for review (sequential after solution generator, if code issue and code found)",
            "email_writer": "Completed - Generated and sent email report with PR link"
        },
        "email_delivery": {
            "agent_triggered": was_email_sent(),
            "fallback_triggered": fallback_email_result is not None,
            "fallback_result": fallback_email_result,
            "last_status": get_last_email_status(),
        }
    }
    
    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    timestamp_str = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(output_dir, f"incident_{session.id}_{timestamp_str}.json")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"Full results saved to: {output_file}")
    
    return output