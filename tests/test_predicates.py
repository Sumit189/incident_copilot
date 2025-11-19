import pytest
from unittest.mock import MagicMock
from agents.utils.predicates import is_patch_ready

def test_is_patch_ready_with_new_code_snippet():
    ctx = MagicMock()
    # Mock session state
    ctx.session.state = {
        "agent_snapshots": {
            "SolutionGeneratorAgent": {
                "patch": {
                    "files_to_modify": [
                        {
                            "path": "test.py",
                            "original_code_snippet": "old",
                            "new_code_snippet": "new"
                        }
                    ]
                }
            }
        }
    }
    
    assert is_patch_ready(ctx) is True

def test_is_patch_ready_with_old_proposed_code():
    ctx = MagicMock()
    # Mock session state
    ctx.session.state = {
        "agent_snapshots": {
            "SolutionGeneratorAgent": {
                "patch": {
                    "files_to_modify": [
                        {
                            "path": "test.py",
                            "proposed_code": "new"
                        }
                    ]
                }
            }
        }
    }
    
    assert is_patch_ready(ctx) is True

def test_is_patch_ready_no_patch():
    ctx = MagicMock()
    ctx.session.state = {"agent_snapshots": {"SolutionGeneratorAgent": {}}}
    assert is_patch_ready(ctx) is False

def test_is_patch_ready_empty_files():
    ctx = MagicMock()
    ctx.session.state = {
        "agent_snapshots": {
            "SolutionGeneratorAgent": {
                "patch": {
                    "files_to_modify": []
                }
            }
        }
    }
    assert is_patch_ready(ctx) is False
