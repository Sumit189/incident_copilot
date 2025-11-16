from typing import Optional
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.adk.models.google_llm import Gemini

from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams, StdioServerParameters
from incident_copilot.config import GITHUB_TOKEN, GITHUB_REPO, RETRY_CONFIG
from incident_copilot.github import get_owner_repo, get_owner_repo_source

_github_mcp_toolset = None


def _get_github_mcp_toolset() -> Optional[McpToolset]:
    """Initialize and return GitHub MCP toolset."""
    global _github_mcp_toolset
    
    if _github_mcp_toolset is not None:
        return _github_mcp_toolset
    
    if not GITHUB_TOKEN:
        print("[CODE ANALYZER] Warning: GITHUB_TOKEN not set. GitHub MCP features will be unavailable.")
        return None
    
    try:
        _github_mcp_toolset = McpToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command="npx",
                    args=[
                        "-y",
                        "@modelcontextprotocol/server-github",
                    ],
                    env={"GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN},
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

    owner_repo = get_owner_repo()
    owner_repo_source = get_owner_repo_source()
    has_valid_repo = owner_repo is not None
    owner = owner_repo[0] if has_valid_repo else ""
    repo = owner_repo[1] if has_valid_repo else ""
    resolved_repo = (owner + "/" + repo) if has_valid_repo else ""
    env_repo_value = (GITHUB_REPO or "").strip()
    env_repo_valid = owner_repo_source == "env"

    if mcp_toolset and has_valid_repo:
        tools_list.append(mcp_toolset)
    elif mcp_toolset and not has_valid_repo:
        print("[CODE ANALYZER] GitHub MCP toolset initialized but repository is missing or invalid; skipping tool registration.")
    else:
        if not GITHUB_TOKEN:
            print("[CODE ANALYZER] Reason: GITHUB_TOKEN environment variable is not set")
        if not env_repo_value:
            print("[CODE ANALYZER] Warning: GITHUB_REPO environment variable is not set")
    
    if has_valid_repo:
        if owner_repo_source == "env":
            repo_source_line = "- Source: GITHUB_REPO environment variable"
        elif env_repo_value and not env_repo_valid:
            repo_source_line = "- Source: Auto-detected from git remote because GITHUB_REPO was invalid"
        else:
            repo_source_line = "- Source: Auto-detected from git remote origin"

        repo_instruction = """
REPOSITORY CONFIGURATION (READ THIS CAREFULLY):
- GitHub repository is configured
- Repository format: owner/repo
- The resolved repository is: """ + resolved_repo + """
- OWNER VALUE (use this in owner parameter): """ + owner + """
- REPO VALUE (use this in repo parameter): """ + repo + """
""" + repo_source_line + """

CRITICAL: When calling search_code or get_file_contents, you MUST use:
  - owner=""" + owner + """ (exact value shown above)
  - repo=""" + repo + """ (exact value shown above)
  - DO NOT use repository parameter
  - DO NOT omit owner or repo parameters
- Tool name for getting file contents: get_file_contents
"""
        repo_example = 'search_code(query="Gemini API quota retry repo:' + resolved_repo + '", owner="' + owner + '", repo="' + repo + '")'
        repo_call = 'search_code(query="error keywords repo:' + resolved_repo + '", owner="' + owner + '", repo="' + repo + '")'
        get_file_call = 'get_file_contents(path="file/path.js", owner="' + owner + '", repo="' + repo + '")'
        repo_rule = '- ALWAYS use owner="' + owner + '" and repo="' + repo + '" as SEPARATE parameters when calling search_code or get_file_contents (NOT repository parameter)'
    else:
        if env_repo_value:
            repo_instruction = """
REPOSITORY CONFIGURATION:
- ERROR: GITHUB_REPO is set to '""" + env_repo_value + """' but it is NOT in 'owner/repo' format.
- GitHub repository could not be resolved automatically.
- Set mcp_available=false and return analysis based on error patterns only
- Do NOT call search_code or get_file_contents if repository is invalid
"""
        else:
            repo_instruction = """
REPOSITORY CONFIGURATION:
- WARNING: GITHUB_REPO is not configured and repository could not be auto-detected from git remote
- Set mcp_available=false and return analysis based on error patterns only
- Do NOT call search_code or get_file_contents if repository is not configured
"""
        repo_example = ""
        repo_call = "- Skip search_code if repository is not configured"
        get_file_call = "- Skip get_file_contents if repository is not configured"
        repo_rule = "- Repository is unavailable. Set mcp_available=false and skip code search"
    
    # Build step instructions based on whether GITHUB_REPO is configured
    if has_valid_repo:
        step1_repo = "- Repository is configured (see REPOSITORY CONFIGURATION above)"
        step1_use = "- ALWAYS use owner=\"" + owner + "\" and repo=\"" + repo + "\" as SEPARATE parameters when calling MCP tools (NOT repository parameter)"
        step2_example = "- Example: " + repo_example if repo_example else ""
    elif env_repo_value:
        step1_repo = "- GITHUB_REPO is invalid format - must be owner/repo (e.g., google/example-repo)"
        step1_use = "- Invalid repository format - skip code search"
        step2_example = ""
    else:
        step1_repo = "- GITHUB_REPO is not configured - set mcp_available=false and return analysis without code search"
        step1_use = "- No repository configured - skip code search"
        step2_example = ""
    
    return LlmAgent(
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=RETRY_CONFIG),
        name="CodeAnalyzerAgent",
        description="Find problematic code locations using GitHub MCP and LLM analysis.",
        instruction=f"""
Find problematic code locations using available tools and LLM analysis.

If CodeAnalyzerGuardAgent already concluded "SKIP: Not a code issue", mirror that response and exit; otherwise continue.

INPUT: service, error_messages, error_type, function_names (optional)

{repo_instruction}

AVAILABLE TOOLS:
- search_code: Search codebase for keywords/functions (from GitHub MCP) - requires owner and repo as separate parameters
- get_file_contents: Get file or directory contents (from GitHub MCP) - requires owner, repo, and path parameters

STEPS:
1. Extract repository information:
   {step1_repo}
   - Repository format: "owner/repo" (e.g., "google/example-repo")
   {step1_use}
   - Look at the REPOSITORY CONFIGURATION section above to find the Owner and Repo values
   - Extract owner and repo from the configuration (they are shown separately in the REPOSITORY CONFIGURATION section)
   - IMPORTANT: search_code and get_file_contents require owner and repo as SEPARATE parameters, NOT a combined repository parameter

2. Use search_code tool to find files matching error keywords:
   - CRITICAL: Look at the REPOSITORY CONFIGURATION section above and copy the exact OWNER VALUE and REPO VALUE
   - You MUST use these exact values in your search_code call
   - Build the query string by combining: error keywords + " repo:owner/repo" (e.g., "Validation error repo:google/example-repo")
   - Example: If REPOSITORY CONFIGURATION shows "OWNER VALUE: google" and "REPO VALUE: example-repo", then call:
     search_code(query="Validation error repo:google/example-repo", owner="google", repo="example-repo")
   - {repo_call}
   {step2_example}
   - Build query from actual error messages in logs (e.g., "429 error", "quota exceeded", "rate limit", "Validation error")
   - ALWAYS include " repo:owner/repo" in the query string to scope search to the specific repository
   - The search_code tool will return file paths and code snippets matching the query
   - MANDATORY: You MUST include both owner and repo parameters AND include " repo:owner/repo" in the query string
   - DO NOT call search_code without owner and repo parameters
   - DO NOT use placeholder values - use the exact owner and repo values from REPOSITORY CONFIGURATION

3. Use get_file_contents tool to retrieve file contents:
   - CRITICAL: Look at the REPOSITORY CONFIGURATION section above and copy the exact OWNER VALUE and REPO VALUE
   - You MUST use these exact values in your get_file_contents call
   - Example: If REPOSITORY CONFIGURATION shows "OWNER VALUE: google" and "REPO VALUE: example-repo", then call:
     get_file_contents(path="src/api/process.js", owner="google", repo="example-repo")
   - {get_file_call}
   - Use file paths returned from search_code results
   - Analyze the code content using LLM to identify problematic code
   - MANDATORY: You MUST include owner, repo, and path parameters in every get_file_contents call
   - DO NOT call get_file_contents without owner, repo, and path parameters
   - DO NOT use placeholder values - use the exact owner and repo values from REPOSITORY CONFIGURATION
   - Tool name is get_file_contents (NOT get_file)

4. Analyze code:
   - Match error patterns to code logic
   - Identify exact functions/lines causing issue
   - Look for: retry without backoff, quota handling issues, error handling gaps, resource exhaustion

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
{repo_rule}
- Repository format must be "owner/repo" (e.g., "google/example-repo")
- The search_code tool is the correct tool for searching code within repositories (NOT search_repositories)
- search_repositories searches for repositories themselves, not code - DO NOT use it
- ALWAYS extract owner and repo from the REPOSITORY CONFIGURATION section at the top of this instruction
- When calling search_code: 
  * You MUST include " repo:owner/repo" in the query string (e.g., "Validation error repo:google/example-repo")
  * You MUST use owner parameter with owner value
  * You MUST use repo parameter with repo value
- When calling get_file_contents: You MUST use path parameter with file path, AND owner parameter with owner value, AND repo parameter with repo value
- Tool name is get_file_contents (NOT get_file - that tool does not exist)
- CORRECT: search_code(query="Validation error repo:google/example-repo", owner="google", repo="example-repo")
- WRONG: search_code(query="Validation error", repository="owner/repo") - DO NOT use repository parameter
- WRONG: search_code(query="Validation error") - DO NOT omit owner, repo parameters, or repo: in query
- WRONG: Using search_repositories - This searches for repositories, not code. Use search_code instead.
- If you call search_code or get_file_contents without required parameters, the tool will fail
- CRITICAL: The tool is called get_file_contents, NOT get_file
- If GITHUB_REPO is empty or tools return errors, set mcp_available=false and provide error-based analysis
- DO NOT call tools that don't exist in the available tools list
- If repository is not configured, return mcp_available=false and provide analysis based on error patterns only
- The MCP tools are available directly - just call them by name (search_code, get_file_contents) with the required parameters
- Available tool names: search_code, get_file_contents (NOT get_file)
""",
        tools=tools_list
    )

code_analyzer_agent = _create_code_analyzer_agent()

