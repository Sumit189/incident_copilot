import os
import shutil
from pathlib import Path
from typing import Optional
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams, StdioServerParameters
from agents.config import GITHUB_TOKEN, GITHUB_REPO, RETRY_CONFIG, BEST_MODEL
from agents.github import get_owner_repo, get_owner_repo_source
from agents.utils.tool_config import get_tool_config

_github_mcp_toolset = None


def _resolve_mcp_server_command() -> tuple[str, list[str]]:
    """Locate an executable command for the GitHub MCP server."""
    npx_path = shutil.which("npx")
    if npx_path:
        return npx_path, ["-y", "@modelcontextprotocol/server-github"]

    repo_root = Path(__file__).resolve().parents[2].parent
    local_server = repo_root / "node_modules" / ".bin" / "server-github"

    if local_server.exists():
        return str(local_server), []

    raise FileNotFoundError(
        "Could not find `npx` or `node_modules/.bin/server-github`. "
        "Install Node.js and run `npm install` before enabling the GitHub MCP toolset."
    )


def _get_github_mcp_toolset() -> Optional[McpToolset]:
    """Initialize and return GitHub MCP toolset."""
    global _github_mcp_toolset
    
    if _github_mcp_toolset is not None:
        return _github_mcp_toolset
    
    if not GITHUB_TOKEN:
        print("[CODE ANALYZER] Warning: GITHUB_TOKEN not set. GitHub MCP features will be unavailable.")
        return None
    
    try:
        command, args = _resolve_mcp_server_command()

        _github_mcp_toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command=command,
                    args=args,
                    env={"GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN, **os.environ},
                ),
                timeout=30,
            ),
            tool_filter=[
                'get_file_contents',
                'search_code'
            ]
        )
        return _github_mcp_toolset
    except Exception as e:
        print(f"[CODE ANALYZER] Error initializing MCP toolset: {e}")
        return None


def _create_code_analyzer_agent():
    """Create Code Analyzer Agent with MCP toolset if available."""
    tools_list = []
    mcp_toolset = _get_github_mcp_toolset()
    
    env_repo_value = (GITHUB_REPO or "").strip()

    # Determine if we can enable MCP tools
    # We enable them if GITHUB_TOKEN is set, even if GITHUB_REPO is not in env,
    # because the repo might be provided in the webhook payload.
    if mcp_toolset and GITHUB_TOKEN:
        tools_list.append(mcp_toolset)
    else:
        if not GITHUB_TOKEN:
            print("[CODE ANALYZER] Reason: GITHUB_TOKEN environment variable is not set")
    
    # Instructions now handle dynamic repo from context
    repo_instruction = """
REPOSITORY CONFIGURATION (READ THIS CAREFULLY):
- The repository to analyze is determined dynamically from the input context or environment variables.
- PRIORITY 1: `github_repo` from the input JSON (if present).
- PRIORITY 2: `GITHUB_REPO` environment variable (fallback).

STEPS TO RESOLVE REPOSITORY:
1. Check if `github_repo` is present in the input JSON.
   - If yes, use that value as the repository (format: "owner/repo").
2. If `github_repo` is NOT in input, check the `GITHUB_REPO` environment variable.
   - Value from env: """ + (env_repo_value or "NOT SET") + """
3. If neither is available, you CANNOT use code search tools.

CRITICAL: When calling search_code or get_file_contents, you MUST use:
  - owner="<extracted_owner>"
  - repo="<extracted_repo>"
  - DO NOT use repository parameter
  - DO NOT omit owner or repo parameters
  - Tool name for getting file contents: get_file_contents
"""
    
    return LlmAgent(
        model=Gemini(
            model=BEST_MODEL,
            retry_options=RETRY_CONFIG,
            tool_config=get_tool_config(allowed_function_names=["search_code", "get_file_contents"]),
        ),
        name="CodeAnalyzerAgent",
        description="Find problematic code locations using GitHub MCP and LLM analysis.",
        instruction=f"""
Find problematic code locations using available tools and LLM analysis. You are an expert software engineer.

If CodeAnalyzerGuardAgent already concluded "SKIP: Not a code issue", mirror that response and exit; otherwise continue.

INPUT: service, error_messages, error_type, function_names (optional), github_repo (optional), github_base_branch (optional)

{repo_instruction}

AVAILABLE TOOLS:
- search_code: Search codebase for keywords/functions (from GitHub MCP) - requires owner and repo as separate parameters
- get_file_contents: Get file or directory contents (from GitHub MCP) - requires owner, repo, and path parameters

STEPS:
1. Extract repository information:
   - Resolve the repository using the "STEPS TO RESOLVE REPOSITORY" above.
   - Split the resolved "owner/repo" string into `owner` and `repo`.
   - Example: "google/example-repo" -> owner="google", repo="example-repo".
   - If you cannot resolve a valid repository, set `mcp_available=false` and skip code search.

2. Use search_code tool to find files matching error keywords:
   - CRITICAL: Use the `owner` and `repo` values you extracted in Step 1.
   - Build the query string by combining: error keywords + " repo:owner/repo" (e.g., "Validation error repo:google/example-repo")
   - Example: If you resolved owner="google" and repo="example-repo", then call:
     search_code(query="Validation error repo:google/example-repo", owner="google", repo="example-repo")
   - Build query from actual error messages in logs.
   - ALWAYS include " repo:owner/repo" in the query string to scope search to the specific repository.
   - MANDATORY: You MUST include both owner and repo parameters AND include " repo:owner/repo" in the query string.

3. Use get_file_contents tool to retrieve file contents:
   - CRITICAL: Use the `owner` and `repo` values you extracted in Step 1.
   - Example: If you resolved owner="google" and repo="example-repo", then call:
     get_file_contents(path="src/api/process.js", owner="google", repo="example-repo")
   - Use file paths returned from search_code results.
   - MANDATORY: You MUST include owner, repo, and path parameters in every get_file_contents call.
   - Tool name is get_file_contents (NOT get_file).

4. Analyze code:
   - Match error patterns to code logic.
   - Identify exact functions/lines causing issue.
   - Look for: retry without backoff, quota handling issues, error handling gaps, resource exhaustion.

5. Return JSON:
{{
  "service": "<name>",
  "problematic_files": [{{
    "path": "<file>",
    "function_name": "<function>",
    "line_start": <line>,
    "line_end": <line>,
    "code_snippet": "<code>",
    "issue_description": "<why problematic>",
    "error_correlation": "<how relates to error>"
  }}],
  "suggested_fix_locations": [{{
    "file": "<file>",
    "function": "<function>",
    "lines": "<range>",
    "reason": "<why fix needed>"
  }}],
  "analysis_summary": "<summary>",
  "mcp_available": true|false
}}

CRITICAL RULES:
- Repository format must be "owner/repo".
- The search_code tool is the correct tool for searching code within repositories.
- ALWAYS extract owner and repo from the resolved repository.
- When calling search_code: 
  * You MUST include " repo:owner/repo" in the query string.
  * You MUST use owner parameter with owner value.
  * You MUST use repo parameter with repo value.
- When calling get_file_contents: You MUST use path parameter, owner parameter, and repo parameter.
- Tool name is get_file_contents (NOT get_file).
- If repository is not configured (neither in input nor env), return mcp_available=false and provide analysis based on error patterns only.
""",
        tools=tools_list
    )

code_analyzer_agent = _create_code_analyzer_agent()

