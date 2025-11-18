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
        print(
            f"[GITHUB] Auto-detected repository {_OWNER_REPO_CACHE[0]}/{_OWNER_REPO_CACHE[1]} from git remote."
        )
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

            base_sha = ref_resp.json().get("object", {}).get("sha")
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

