from typing import List, Optional, Dict, Any

def get_tool_config(allowed_function_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Generates a dictionary-based ToolConfig for Gemini models.

    Args:
        allowed_function_names: A list of function names to whitelist. 
                                If None or empty, tool use is disabled (mode="NONE").

    Returns:
        A dictionary matching the expected structure for `tool_config`.
    """
    if allowed_function_names:
        return {
            "function_calling_config": {
                "mode": "AUTO",
                "allowed_function_names": allowed_function_names,
            }
        }
    else:
        return {
            "function_calling_config": {
                "mode": "NONE",
            }
        }
