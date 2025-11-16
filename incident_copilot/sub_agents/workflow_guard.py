"""
Workflow Guard Agent - Checks incident detection result and conditionally proceeds.
"""

import json
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.tools import check_incident_detection_result, stop_workflow
from incident_copilot.config import RETRY_CONFIG

def create_conditional_workflow(incident_response_agents):
    """
    Create a conditional workflow that only proceeds if incident is detected.
    
    The guard agent checks first, and only if it says PROCEED will subsequent agents run.
    
    Args:
        incident_response_agents: List of agents to run if incident is detected
    
    Returns:
        SequentialAgent that conditionally executes
    """
    
    workflow_guard_agent = LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="WorkflowGuardAgent",
        description="Check incident detection result and conditionally proceed with workflow.",
        instruction="""
Check incident detection result and conditionally proceed with workflow.

STEPS:
1. Find IncidentDetectionAgent's JSON output in conversation history:
   - Look for JSON with "incident_detected" and "recommendation" fields
   - Extract incident_detected (true|false) and recommendation ("proceed"|"skip")

2. Decision logic:
   - If incident_detected=true AND recommendation="proceed":
     => Return: "PROCEED: Incident confirmed. Continuing workflow."
   
   - If incident_detected=false OR recommendation="skip":
     => Call stop_workflow("No incident detected")
     => Return: "SKIP: No incident detected. Workflow terminated."

3. Response format (exactly one line):
   - "SKIP: No incident detected. Workflow terminated."
   - "PROCEED: Incident confirmed. Continuing workflow."

CRITICAL RULES:
- Check BOTH incident_detected AND recommendation fields
- If incident_detected=true => workflow should PROCEED (even if recommendation seems wrong)
- Only skip if incident_detected=false OR recommendation="skip"
- Call stop_workflow() FIRST if skipping so downstream agents know the workflow ended
- No additional text when skipping
- This is the guard - if SKIP, workflow stops completely
""",
        tools=[
            FunctionTool(func=check_incident_detection_result),
            FunctionTool(func=stop_workflow)
        ]
    )
    
    # Create conditional workflow: Guard -> (if proceed) -> Rest of workflow
    conditional_workflow = SequentialAgent(
        name="ConditionalIncidentWorkflow",
        sub_agents=[workflow_guard_agent] + incident_response_agents
    )
    
    return conditional_workflow

