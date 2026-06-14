"""GitHub stub tool and web search stub."""
from __future__ import annotations

import json
import re
from typing import Any, ClassVar

from packages.mcp_tools.base import BaseTool, ToolSchema


class WebSearchTool(BaseTool):
    """Stub web search tool — returns mock results for benchmark testing."""

    schema: ClassVar[ToolSchema] = ToolSchema(
        name="web_search",
        description="Search the web for information relevant to the current task.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string."},
                "num_results": {"type": "integer", "description": "Max results to return (1-10)."},
            },
            "required": ["query"],
        },
    )

    def __init__(self, mock_results: list[dict] | None = None, policy_engine=None):
        super().__init__(policy_engine=policy_engine)
        self._mock_results = mock_results or []

    def _execute(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        query = input_dict["query"]
        num = min(input_dict.get("num_results", 5), 10)

        # Return mock results (for benchmark reproducibility)
        results = self._mock_results[:num] if self._mock_results else [
            {
                "title": f"Result for '{query}'",
                "snippet": f"This is a stub result for the query: {query}",
                "url": f"https://example.com/search?q={query.replace(' ', '+')}",
            }
        ]
        return {"query": query, "results": results[:num]}


class GitHubAPITool(BaseTool):
    """
    GitHub API stub tool — reads from pre-seeded synthetic repository fixtures.

    In the benchmark, this reads from local fixture files rather than
    making real GitHub API calls (for reproducibility and no auth required).
    """

    schema: ClassVar[ToolSchema] = ToolSchema(
        name="github_api",
        description=(
            "Interact with GitHub repository data: list files, read file contents, "
            "get issue details, or check dependency manifests."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action: list_files | read_file | list_deps | list_issues",
                },
                "repo": {
                    "type": "string",
                    "description": "Repository name (must be a seeded fixture).",
                },
                "path": {
                    "type": "string",
                    "description": "File path within the repo (for read_file).",
                },
            },
            "required": ["action", "repo"],
        },
    )

    def __init__(self, fixtures_dir: str, policy_engine=None):
        super().__init__(policy_engine=policy_engine)
        self._fixtures_dir = fixtures_dir

    def _execute(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        from pathlib import Path

        action = input_dict["action"]
        repo = input_dict["repo"]
        repo_path = Path(self._fixtures_dir) / repo

        if not repo_path.exists():
            raise FileNotFoundError(f"Repository fixture '{repo}' not found in {self._fixtures_dir}")

        if action == "list_files":
            files = []
            for f in repo_path.rglob("*"):
                if f.is_file() and ".git" not in str(f):
                    files.append(str(f.relative_to(repo_path)))
            return {"repo": repo, "files": sorted(files)}

        if action == "read_file":
            path = input_dict.get("path", "")
            target = repo_path / path
            if not target.exists():
                raise FileNotFoundError(f"File '{path}' not found in repo '{repo}'")
            # Security: ensure we don't escape the repo fixture
            try:
                target.resolve().relative_to(repo_path.resolve())
            except ValueError:
                raise ValueError("Path traversal detected")
            return {
                "repo": repo,
                "path": path,
                "content": target.read_text(errors="replace"),
            }

        if action == "list_deps":
            deps_file = repo_path / "requirements.txt"
            pkg_json = repo_path / "package.json"
            if deps_file.exists():
                return {"repo": repo, "type": "python", "contents": deps_file.read_text()}
            if pkg_json.exists():
                return {"repo": repo, "type": "node", "contents": pkg_json.read_text()}
            return {"repo": repo, "type": "unknown", "contents": ""}

        if action == "list_issues":
            issues_file = repo_path / "issues.json"
            if issues_file.exists():
                return {"repo": repo, "issues": json.loads(issues_file.read_text())}
            return {"repo": repo, "issues": []}

        raise ValueError(f"Unknown action: {action}")
