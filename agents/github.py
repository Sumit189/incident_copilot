import base64
import os
import subprocess
import uuid
from typing import Any, Dict, Optional, Tuple

import httpx

GITHUB_REPO = os.getenv("GITHUB_REPO", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")

_OWNER_REPO_CACHE: Optional[Tuple[str, str]] = None
_OWNER_REPO_SOURCE: Optional[str] = None


def _normalize_owner_repo(owner: str, repo: str) -> Optional[Tuple[str, str]]:
    owner = (owner or "").strip()
    repo = (repo or "").strip()
    if repo.endswith(".git"):
        repo = repo[:-4]
    if owner and repo:
        return owner, repo
    return None


def _parse_repo_string(repo_str: str) -> Optional[Tuple[str, str]]:
    if not repo_str or "/" not in repo_str:
        return None
    owner, repo = repo_str.split("/", 1)
    return _normalize_owner_repo(owner, repo)


def _parse_remote_url(remote_url: str) -> Optional[Tuple[str, str]]:
    if not remote_url:
        return None
    remote_url = remote_url.strip()
    if "github.com" not in remote_url:
        return None

    sanitized = remote_url
    if sanitized.endswith(".git"):
        sanitized = sanitized[:-4]

    path_segment = ""
    if sanitized.startswith("git@"):
        try:
            _, path_segment = sanitized.split(":", 1)
        except ValueError:
            return None
    else:
        if "://" in sanitized:
            _, remainder = sanitized.split("://", 1)
        else:
            remainder = sanitized
        # remainder might be e.g. github.com/owner/repo
        if "github.com" in remainder:
            _, path_segment = remainder.split("github.com", 1)
        else:
            path_segment = remainder

    path_segment = path_segment.lstrip("/").strip()
    if not path_segment:
        return None

    parts = path_segment.split("/")
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    return _normalize_owner_repo(owner, repo)


def _detect_owner_repo_from_git() -> Optional[Tuple[str, str]]:
    repo_path = os.getenv("GIT_REPO_PATH", ".")
    git_cmd = ["git", "-C", repo_path, "config", "--get", "remote.origin.url"]
    try:
        result = subprocess.run(
            git_cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    remote_url = result.stdout.strip()
    return _parse_remote_url(remote_url)


def get_owner_repo() -> Optional[Tuple[str, str]]:
    """
    Return the configured GitHub owner/repo tuple.

    Preference order:
    1. Explicit GITHUB_REPO env var in owner/repo format.
    2. Auto-detected from local git remote (origin).
    """
    global _OWNER_REPO_CACHE, _OWNER_REPO_SOURCE

    if _OWNER_REPO_CACHE:
        return _OWNER_REPO_CACHE

    repo_from_env = _parse_repo_string(GITHUB_REPO)
    if repo_from_env:
        _OWNER_REPO_CACHE = repo_from_env
        _OWNER_REPO_SOURCE = "env"
        return _OWNER_REPO_CACHE

    if GITHUB_REPO:
        print(
            "[GITHUB] Warning: GITHUB_REPO is set but not in 'owner/repo' format. "
            "Attempting to auto-detect from git remote."
        )

    detected = _detect_owner_repo_from_git()
    if detected:
        _OWNER_REPO_CACHE = detected
        _OWNER_REPO_SOURCE = "git_remote"
        return _OWNER_REPO_CACHE

    return None


def get_owner_repo_source() -> Optional[str]:
    """Return the source used for resolving owner/repo ("env", "git_remote", or None)."""
    if _OWNER_REPO_CACHE is None:
        get_owner_repo()
    return _OWNER_REPO_SOURCE


def _github_headers() -> Dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _normalize_generated_content(text: Optional[str]) -> str:
    """
    Best-effort cleanup for LLM generated content that may contain escaped newlines/tabs.
    Keeps indentation by expanding common escape sequences when no real newlines exist.
    """
    if text is None:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")

    if "\n" not in normalized and "\\n" in normalized:
        try:
            normalized = normalized.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            normalized = normalized.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    else:
        normalized = normalized.replace("\\r\\n", "\\n")

    return normalized


def _evaluate_branch_diff(
    client: httpx.Client,
    owner: str,
    repo: str,
    base_branch: str,
    head_branch: str,
) -> Tuple[Optional[bool], str]:
    """
    Compare base/head and determine if the head branch has commits ahead of base.

    Returns:
        (has_commits, message)
        - has_commits True => branch contains new commits/files relative to base.
        - has_commits False => no commits/diffs; message explains why.
        - has_commits None => comparison failed; message contains error.
    """
    compare_url = f"https://api.github.com/repos/{owner}/{repo}/compare/{base_branch}...{head_branch}"
    resp = client.get(compare_url, headers=_github_headers())

    if resp.status_code == 404:
        message = ""
        if resp.content:
            try:
                message = resp.json().get("message") or ""
            except ValueError:
                message = resp.text
        message = message or "Branch comparison failed"
        return None, f"Unable to compare '{head_branch}' with '{base_branch}': {message}"

    if resp.status_code != 200:
        detail = resp.text
        return (
            None,
            f"Failed to compare branches '{base_branch}' and '{head_branch}': {detail}",
        )

    data = resp.json()
    ahead_by = data.get("ahead_by") or 0
    total_commits = data.get("total_commits") or 0
    files = data.get("files") or []

    if ahead_by == 0 and total_commits == 0 and len(files) == 0:
        return (
            False,
            f"Branch '{head_branch}' has no commits ahead of base '{base_branch}'.",
        )

    return True, ""


def _repo_api(path: str) -> Optional[str]:
    owner_repo = get_owner_repo()
    if not owner_repo:
        return None
    owner, repo = owner_repo
    return f"https://api.github.com/repos/{owner}/{repo}{path}"


def create_incident_branch(
    branch_name: str,
    base_branch: Optional[str] = None,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """
    Create a GitHub branch for the incident workflow.
    Automatically appends a short suffix when the branch already exists.
    """
    branch_name = (branch_name or "").strip().replace(" ", "-")
    if not branch_name:
        return {
            "status": "error",
            "branch_name": None,
            "message": "Branch name is required",
        }

    owner_repo = get_owner_repo()
    if not owner_repo:
        return {
            "status": "error",
            "branch_name": None,
            "message": "GITHUB_REPO is not configured as owner/repo",
        }

    if not GITHUB_TOKEN:
        return {
            "status": "error",
            "branch_name": None,
            "message": "GITHUB_TOKEN is not set; cannot create branch",
        }

    owner, repo = owner_repo
    branch_to_use = base_branch or GITHUB_BASE_BRANCH or "main"

    try:
        with httpx.Client(timeout=30.0) as client:
            ref_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch_to_use}",
                headers=_github_headers(),
            )
            if ref_resp.status_code != 200:
                return {
                    "status": "error",
                    "branch_name": None,
                    "message": f"Failed to load base branch '{branch_to_use}': {ref_resp.text}",
                }

            base_sha = (ref_resp.json().get("object") or {}).get("sha")
            if not base_sha:
                return {
                    "status": "error",
                    "branch_name": None,
                    "message": f"Base branch '{branch_to_use}' has no commit SHA",
                }

            for attempt in range(max_attempts):
                candidate = branch_name
                if attempt > 0:
                    candidate = f"{branch_name}-{uuid.uuid4().hex[:4]}"

                payload = {"ref": f"refs/heads/{candidate}", "sha": base_sha}
                create_resp = client.post(
                    f"https://api.github.com/repos/{owner}/{repo}/git/refs",
                    json=payload,
                    headers=_github_headers(),
                )

                if create_resp.status_code == 201:
                    return {
                        "status": "success",
                        "branch_name": candidate,
                        "message": f"Branch '{candidate}' created from '{branch_to_use}'",
                    }

                error_body = create_resp.json() if create_resp.content else {}
                message = error_body.get("message", create_resp.text)

                if (
                    create_resp.status_code == 422
                    and "Reference already exists" in message
                    and attempt < max_attempts - 1
                ):
                    continue

                return {
                    "status": "error",
                    "branch_name": None,
                    "message": f"Failed to create branch '{candidate}': {message}",
                }

    except httpx.HTTPError as exc:
        return {
            "status": "error",
            "branch_name": None,
            "message": f"HTTP error while creating branch: {exc}",
        }

    return {
        "status": "error",
        "branch_name": None,
        "message": f"Branch '{branch_name}' already exists after {max_attempts} attempts",
    }


def create_or_update_file(
    path: str,
    content: str,
    branch: str,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or update a file on the specified branch using the GitHub REST API.
    """
    path = (path or "").lstrip("/")
    if not path:
        return {
            "status": "error",
            "path": None,
            "message": "File path is required",
        }

    if branch is None or not branch.strip():
        return {
            "status": "error",
            "path": path,
            "message": "Branch name is required to update files",
        }

    owner_repo = get_owner_repo()
    if not owner_repo:
        return {
            "status": "error",
            "path": path,
            "message": "GITHUB_REPO is not configured as owner/repo",
        }

    if not GITHUB_TOKEN:
        return {
            "status": "error",
            "path": path,
            "message": "GITHUB_TOKEN is not set; cannot update files",
        }

    owner, repo = owner_repo
    branch = branch.strip()
    message = message or f"Update {path}"
    normalized_content = _normalize_generated_content(content)
    encoded_content = base64.b64encode(normalized_content.encode("utf-8")).decode("utf-8")

    try:
        with httpx.Client(timeout=30.0) as client:
            sha = None
            get_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
                headers=_github_headers(),
            )
            if get_resp.status_code == 200:
                sha = get_resp.json().get("sha")
            elif get_resp.status_code not in (404,):
                return {
                    "status": "error",
                    "path": path,
                    "message": f"Failed to read existing file: {get_resp.text}",
                }

            payload = {
                "message": message,
                "content": encoded_content,
                "branch": branch,
            }
            if sha:
                payload["sha"] = sha

            put_resp = client.put(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                json=payload,
                headers=_github_headers(),
            )

            if put_resp.status_code in (200, 201):
                body = put_resp.json()
                content_info = body.get("content", {})
                commit_info = body.get("commit", {})
                return {
                    "status": "success",
                    "path": path,
                    "branch": branch,
                    "file_sha": content_info.get("sha"),
                    "commit_sha": commit_info.get("sha"),
                    "message": f"{'Updated' if sha else 'Created'} {path} on {branch}",
                }

            error_body = put_resp.json() if put_resp.content else {}
            return {
                "status": "error",
                "path": path,
                "branch": branch,
                "message": error_body.get("message", put_resp.text),
            }

    except httpx.HTTPError as exc:
        return {
            "status": "error",
            "path": path,
            "branch": branch,
            "message": f"HTTP error while updating file: {exc}",
        }


def apply_change_to_file(
    path: str,
    search_content: str,
    replace_content: str,
    branch: str,
    message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Apply a targeted change to a file by searching for content and replacing it.
    """
    path = (path or "").lstrip("/")
    if not path:
        return {"status": "error", "message": "File path is required"}
    
    if not search_content:
        return {"status": "error", "message": "search_content is required"}
        
    if branch is None or not branch.strip():
        return {"status": "error", "message": "Branch name is required"}

    owner_repo = get_owner_repo()
    if not owner_repo:
        return {"status": "error", "message": "GITHUB_REPO is not configured"}
        
    if not GITHUB_TOKEN:
        return {"status": "error", "message": "GITHUB_TOKEN is not set"}

    owner, repo = owner_repo
    branch = branch.strip()
    
    try:
        with httpx.Client(timeout=30.0) as client:
            # 1. Get current content
            get_resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
                headers=_github_headers(),
            )
            
            if get_resp.status_code != 200:
                return {
                    "status": "error",
                    "path": path,
                    "message": f"Failed to read file '{path}' on branch '{branch}': {get_resp.text}"
                }
                
            content_data = get_resp.json()
            sha = content_data.get("sha")
            
            if content_data.get("encoding") != "base64":
                return {"status": "error", "message": "File content is not base64 encoded, cannot edit safely"}
                
            current_b64 = content_data.get("content", "").replace("\n", "")
            try:
                current_content = base64.b64decode(current_b64).decode("utf-8")
            except Exception as e:
                return {"status": "error", "message": f"Failed to decode file content: {e}"}

            # 2. Apply replacement
            # Normalize line endings for robust matching
            normalized_current = current_content.replace("\r\n", "\n")
            normalized_search = search_content.replace("\r\n", "\n")
            normalized_replace = replace_content.replace("\r\n", "\n")
            
            if normalized_search not in normalized_current:
                # Try a more fuzzy match if exact match fails (e.g. stripping whitespace)
                if normalized_search.strip() in normalized_current:
                     normalized_search = normalized_search.strip()
                else:
                    # Flexible Whitespace Match Strategy
                    # 1. Split into lines
                    search_lines = [line.strip() for line in normalized_search.splitlines() if line.strip()]
                    current_lines = normalized_current.splitlines()
                    
                    if not search_lines:
                         return {
                            "status": "error", 
                            "message": "Search content is empty or only whitespace."
                        }

                    # 2. Find matching block
                    match_start_index = -1
                    match_end_index = -1
                    
                    # Naive scanning for the block of lines
                    # This finds the first occurrence where the sequence of non-empty search lines 
                    # matches a sequence of lines in the file (ignoring whitespace).
                    for i in range(len(current_lines)):
                        if i + len(search_lines) > len(current_lines):
                            break
                        
                        match = True
                        # Check if search_lines match current_lines[i : i+len(search_lines)]
                        # We need to account for the fact that current_lines might have extra empty lines 
                        # interspersed, but for now let's try strict line-by-line ignoring whitespace.
                        # Actually, a better approach is to find the first line, then check subsequent lines.
                        
                        current_slice = current_lines[i : i + len(search_lines)]
                        for j, s_line in enumerate(search_lines):
                            if current_slice[j].strip() != s_line:
                                match = False
                                break
                        
                        if match:
                            match_start_index = i
                            match_end_index = i + len(search_lines)
                            break
                    
                    if match_start_index != -1:
                        # Reconstruct the exact string from the file to use as the "search" target for replacement
                        # We need to capture exactly what was in the file, including original indentation/newlines
                        # that we ignored during matching.
                        
                        # However, simply replacing the lines might lose surrounding context if we aren't careful.
                        # But since we found the lines in `current_lines`, we can join them back.
                        # Wait, `current_lines` was split by `splitlines()`, so we lost the original newline chars.
                        # But `normalized_current` has `\n`.
                        
                        # Let's find the character offsets of these lines in `normalized_current`.
                        # This is tricky because of duplicate lines.
                        
                        # Alternative: We know the content we want to replace is `current_lines[match_start_index : match_end_index]`.
                        # We can construct a regex or just use the fact that we want to replace this block.
                        
                        # Let's try to locate the block in the original string.
                        # We can construct a "fuzzy regex" or just use the lines we found.
                        
                        # Let's reconstruct the "actual" content segment from the file
                        # We need to be careful about which specific instance we matched if there are duplicates.
                        # Our loop found the *first* instance.
                        
                        # Let's re-scan `normalized_current` line by line to find the byte offsets.
                        # This is safer.
                        
                        lines_with_offsets = []
                        offset = 0
                        for line in current_lines:
                            # We need to account for the newline character we split on. 
                            # splitlines() consumes it.
                            # We can't easily know if it was \n or \r\n without looking at original, 
                            # but we normalized to \n.
                            length = len(line) + 1 # +1 for \n
                            lines_with_offsets.append((line, offset, offset + length))
                            offset += length
                        
                        # This assumes every line ends with \n, which might not be true for the last line.
                        # But `normalized_current` usually ends with \n or we can append one for processing.
                        
                        # Let's refine the match logic to work on `lines_with_offsets`
                        
                        # Re-run the match logic on `lines_with_offsets`
                        # (We could have done this first, but I'm iterating)
                        
                        # We found `match_start_index` and `match_end_index` in `current_lines`.
                        # So the start offset is `lines_with_offsets[match_start_index][1]`
                        # And the end offset is `lines_with_offsets[match_end_index-1][2]`
                        
                        # Wait, we need to handle the last line case (no newline).
                        # `normalized_current.splitlines()` drops the final newline if it exists? No.
                        # `splitlines(keepends=True)` would be better.
                        
                        current_lines_keepends = normalized_current.splitlines(keepends=True)
                        
                        # Re-match using keepends to get exact text
                        # We match based on .strip() content
                        
                        match_found = False
                        start_idx = -1
                        end_idx = -1
                        
                        for i in range(len(current_lines_keepends)):
                            if i + len(search_lines) > len(current_lines_keepends):
                                break
                                
                            # Check match
                            current_slice = current_lines_keepends[i : i + len(search_lines)]
                            slice_stripped = [l.strip() for l in current_slice]
                            
                            # Compare slice_stripped vs search_lines
                            # search_lines are already stripped and non-empty.
                            # We need to ignore empty lines in the file? 
                            # The previous logic `search_lines = [line.strip() for line in normalized_search.splitlines() if line.strip()]`
                            # implies we ignore empty lines in SEARCH query.
                            # But if the file has empty lines *between* the code lines, we should probably fail 
                            # or handle it.
                            # For now, let's assume the user provided a contiguous block.
                            
                            if slice_stripped == search_lines:
                                match_found = True
                                start_idx = i
                                end_idx = i + len(search_lines)
                                break
                        
                        if match_found:
                            # Construct the EXACT string to replace
                            matched_block = "".join(current_lines_keepends[start_idx:end_idx])
                            normalized_search = matched_block
                            
                            # Infer indentation from the first line of the matched block
                            first_line = current_lines_keepends[start_idx]
                            indentation = ""
                            for char in first_line:
                                if char.isspace():
                                    indentation += char
                                else:
                                    break
                            
                            # Apply indentation to replacement content if it doesn't have it
                            # We only apply it if the replacement is multiline and the first line isn't indented?
                            # Or should we just prepend indentation to every line of replacement?
                            # The replacement content provided by LLM usually lacks context indentation.
                            
                            if indentation:
                                replace_lines = normalized_replace.splitlines()
                                indented_replace_lines = []
                                for i, line in enumerate(replace_lines):
                                    # Don't double indent if LLM already provided indentation?
                                    # It's safer to assume LLM provided code relative to the block start.
                                    # But if LLM provided "    print('foo')", and we add indent, it becomes double.
                                    # Let's check if the first line of replacement already has the same indentation.
                                    
                                    current_line_indent = ""
                                    for char in line:
                                        if char.isspace():
                                            current_line_indent += char
                                        else:
                                            break
                                            
                                    if i == 0 and current_line_indent.startswith(indentation):
                                         # Replacement already has at least this indentation, assume it's correct
                                         indented_replace_lines = replace_lines
                                         break
                                    
                                    indented_replace_lines.append(indentation + line)
                                else:
                                    normalized_replace = "\n".join(indented_replace_lines)
                                    # Restore trailing newline if original had it?
                                    # normalized_replace usually doesn't have trailing newline unless explicitly added.
                            
                            # Now `normalized_search` matches exactly a block in `normalized_current`
                        else:
                             return {
                                "status": "error", 
                                "message": f"Search content not found in file '{path}'. Flexible matching also failed. Please ensure the code snippet is unique and accurate."
                            }
                    else:
                        return {
                            "status": "error", 
                            "message": f"Search content not found in file '{path}'. Please ensure 'current_code' matches exactly."
                        }
            
            new_content = normalized_current.replace(normalized_search, normalized_replace, 1)
            
            if new_content == normalized_current:
                 return {"status": "error", "message": "Replacement resulted in no change."}

            # 3. Write back
            commit_message = message or f"Update {path}: Apply patch"
            encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
            
            payload = {
                "message": commit_message,
                "content": encoded_content,
                "branch": branch,
                "sha": sha
            }
            
            put_resp = client.put(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                json=payload,
                headers=_github_headers(),
            )
            
            if put_resp.status_code in (200, 201):
                body = put_resp.json()
                return {
                    "status": "success",
                    "path": path,
                    "branch": branch,
                    "commit_sha": (body.get("commit") or {}).get("sha"),
                    "message": f"Successfully updated {path}"
                }
            else:
                return {
                    "status": "error",
                    "message": f"Failed to commit changes: {put_resp.text}"
                }
                
    except httpx.HTTPError as exc:
        return {"status": "error", "message": f"HTTP error: {exc}"}


def create_pull_request(
    title: str,
    body: str,
    head: str,
    base: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create (or reuse) a pull request using the GitHub REST API.
    """
    if not head or not head.strip():
        return {
            "status": "error",
            "pr_number": None,
            "pr_url": None,
            "message": "Branch (head) is required to open a pull request",
        }

    owner_repo = get_owner_repo()
    if not owner_repo:
        return {
            "status": "error",
            "message": "GITHUB_REPO is not configured as owner/repo",
            "pr_number": None,
            "pr_url": None,
        }

    if not GITHUB_TOKEN:
        return {
            "status": "error",
            "message": "GITHUB_TOKEN is not set; cannot create pull requests",
            "pr_number": None,
            "pr_url": None,
        }

    owner, repo = owner_repo
    head = head.strip()
    base_branch = (base or GITHUB_BASE_BRANCH or "main").strip()

    payload = {
        "title": title or f"Auto-fix for {head}",
        "head": head,
        "base": base_branch,
        "body": body or "",
    }

    def _format_pr_response(pr_data: Dict[str, Any], status: str) -> Dict[str, Any]:
        return {
            "status": status,
            "pr_number": pr_data.get("number"),
            "pr_url": pr_data.get("html_url"),
            "branch": head,
            "base": base_branch,
            "message": pr_data.get("title", "Pull request ready"),
            "merged": pr_data.get("merged", False),
        }

    try:
        with httpx.Client(timeout=30.0) as client:
            has_commits, compare_message = _evaluate_branch_diff(
                client,
                owner,
                repo,
                base_branch,
                head,
            )

            if has_commits is None:
                return {
                    "status": "error",
                    "pr_number": None,
                    "pr_url": None,
                    "branch": head,
                    "base": base_branch,
                    "message": compare_message,
                    "merged": False,
                }

            if has_commits is False:
                return {
                    "status": "skipped",
                    "pr_number": None,
                    "pr_url": None,
                    "branch": head,
                    "base": base_branch,
                    "message": compare_message,
                    "merged": False,
                }

            resp = client.post(
                f"https://api.github.com/repos/{owner}/{repo}/pulls",
                json=payload,
                headers=_github_headers(),
            )

            if resp.status_code in (200, 201):
                return _format_pr_response(resp.json(), "success")

            # If a PR already exists for this branch, surface it instead of failing.
            error_body = resp.json() if resp.content else {}
            message = error_body.get("message", resp.text)
            errors = error_body.get("errors")
            if errors:
                error_messages = []
                for err in errors:
                    if isinstance(err, dict):
                        detail = err.get("message") or err.get("code")
                        if err.get("field"):
                            detail = f"{err.get('field')}: {detail}"
                    else:
                        detail = str(err)
                    if detail:
                        error_messages.append(detail)
                if error_messages:
                    message = f"{message}: {'; '.join(error_messages)}"

            error_text = message.lower()
            if errors and not error_text:
                error_text = str(errors).lower()

            if resp.status_code == 422 and "already exists" in error_text:
                existing = client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/pulls",
                    params={"head": f"{owner}:{head}", "state": "open"},
                    headers=_github_headers(),
                )
                if existing.status_code == 200:
                    items = existing.json()
                    if items:
                        return _format_pr_response(items[0], "exists")

            return {
                "status": "error",
                "pr_number": None,
                "pr_url": None,
                "branch": head,
                "message": message,
            }

    except httpx.HTTPError as exc:
        return {
            "status": "error",
            "pr_number": None,
            "pr_url": None,
            "branch": head,
            "message": f"HTTP error while creating pull request: {exc}",
        }


def verify_patch(
    files: list[dict[str, str]],
    base_branch: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check if the proposed file changes are actually different from the base branch.
    
    Args:
        files: List of dicts with 'path' and 'proposed_code'.
        base_branch: Branch to compare against (default: configured base or main).
        
    Returns:
        Dict with 'needs_changes' (bool) and 'message'.
    """
    if not files:
        return {"needs_changes": False, "message": "No files to check"}

    owner_repo = get_owner_repo()
    if not owner_repo:
        return {"needs_changes": False, "message": "Repository not configured"}
    
    if not GITHUB_TOKEN:
        return {"needs_changes": False, "message": "GITHUB_TOKEN not set"}

    owner, repo = owner_repo
    branch = base_branch or GITHUB_BASE_BRANCH or "main"
    
    try:
        with httpx.Client(timeout=30.0) as client:
            changes_needed = False
            checked_files = 0
            
            for file_entry in files:
                path = file_entry.get("path")
                proposed = file_entry.get("proposed_code")
                
                if not path or proposed is None:
                    continue
                
                path = path.lstrip("/")
                
                # Fetch current content
                resp = client.get(
                    f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                    params={"ref": branch},
                    headers=_github_headers(),
                )
                
                if resp.status_code == 404:
                    # File doesn't exist, so creating it is a change
                    changes_needed = True
                    break
                
                if resp.status_code == 200:
                    content_data = resp.json()
                    if content_data.get("encoding") == "base64":
                        current_b64 = content_data.get("content", "").replace("\n", "")
                        try:
                            current_content = base64.b64decode(current_b64).decode("utf-8")
                        except Exception:
                            # Binary or decode error, assume changed to be safe
                            changes_needed = True
                            break
                            
                        # Normalize both for comparison
                        norm_current = _normalize_generated_content(current_content).strip()
                        norm_proposed = _normalize_generated_content(proposed).strip()
                        
                        if norm_current != norm_proposed:
                            changes_needed = True
                            break
                    else:
                        # Unknown encoding, assume changed
                        changes_needed = True
                        break
                else:
                    # Error reading file, assume changed to be safe/robust
                    changes_needed = True
                    break
                
                checked_files += 1
            
            if changes_needed:
                return {"needs_changes": True, "message": "Found files requiring updates"}
            else:
                return {"needs_changes": False, "message": f"All {checked_files} files are identical to {branch}"}
                
    except Exception as e:
        return {"needs_changes": True, "message": f"Error verifying patch: {e}"}


def read_file_content(
    path: str,
    branch: str,
) -> str:
    """
    Read the content of a file from the specified branch.
    Returns the decoded string content or an error message starting with "Error:".
    """
    path = (path or "").lstrip("/")
    if not path:
        return "Error: File path is required"
        
    if not branch or not branch.strip():
        return "Error: Branch name is required"

    owner_repo = get_owner_repo()
    if not owner_repo:
        return "Error: GITHUB_REPO is not configured"
        
    if not GITHUB_TOKEN:
        return "Error: GITHUB_TOKEN is not set"

    owner, repo = owner_repo
    branch = branch.strip()
    
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
                headers=_github_headers(),
            )
            
            if resp.status_code == 404:
                return f"Error: File '{path}' not found on branch '{branch}'"
            
            if resp.status_code != 200:
                return f"Error: Failed to read file: {resp.text}"
                
            content_data = resp.json()
            if content_data.get("encoding") != "base64":
                return "Error: File content is not base64 encoded"
                
            current_b64 = content_data.get("content", "").replace("\n", "")
            try:
                return base64.b64decode(current_b64).decode("utf-8")
            except Exception as e:
                return f"Error: Failed to decode file content: {e}"
                
    except httpx.HTTPError as exc:
        return f"Error: HTTP error: {exc}"

