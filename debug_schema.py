import json
from google.adk.tools import FunctionTool
from tools.incident_actions import publish_incident_report

tool = FunctionTool(func=publish_incident_report)
print(json.dumps(tool.definition, indent=2, default=str))
