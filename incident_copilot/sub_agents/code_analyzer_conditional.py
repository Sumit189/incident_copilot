from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from incident_copilot.config import RETRY_CONFIG
from incident_copilot.sub_agents.code_analyzer import code_analyzer_agent


def create_conditional_code_analyzer():
    """
    Create a conditional workflow that only runs code analyzer if incident is a code issue.
    
    Returns:
        SequentialAgent that conditionally executes code_analyzer_agent
    """
    
    code_analyzer_guard_agent = LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="CodeAnalyzerGuardAgent",
        description="Check if incident is a code issue and conditionally run code analyzer.",
        instruction="""
Check if incident is a code issue and conditionally run code analyzer.

STEPS:
1. Extract from Incident Detection Agent output:
   - incident_type_hint field (should be "code_issue" or other)
   - Look for JSON with "incident_type_hint" field

2. Decision logic:
   - If incident_type_hint="code_issue":
     => Return: "PROCEED: Code issue detected. Running code analyzer."
   
   - If incident_type_hint != "code_issue" (config_issue, infrastructure_issue, etc.):
     => Return: "SKIP: Not a code issue. Skipping code analyzer."

3. Response format (exactly one line):
   - "SKIP: Not a code issue. Skipping code analyzer."
   - "PROCEED: Code issue detected. Running code analyzer."

CRITICAL RULES:
- Check incident_type_hint from Incident Detection Agent
- Only proceed if incident_type_hint="code_issue"
- If skipping, return SKIP message (CodeAnalyzerAgent will mirror it)
""",
        tools=[]
    )
    
    # Create conditional workflow: Guard -> (if proceed) -> Code Analyzer
    conditional_code_analyzer = SequentialAgent(
        name="ConditionalCodeAnalyzer",
        sub_agents=[code_analyzer_guard_agent, code_analyzer_agent]
    )
    
    return conditional_code_analyzer

