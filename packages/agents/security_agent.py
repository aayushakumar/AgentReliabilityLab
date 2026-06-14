"""
GitHub Security Agent — scans synthetic repositories for vulnerabilities.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from packages.agents.llm_provider import get_llm
from packages.mcp_tools.github_tool import GitHubAPITool
from packages.mcp_tools.file_tool import FileReaderTool
from packages.tracing.models import Run, RunStatus, SpanKind
from packages.tracing.tracer import get_tracer

logger = logging.getLogger(__name__)

SECURITY_SYSTEM_PROMPT = """\
You are a senior application security engineer. Analyze the provided code for security vulnerabilities.

For each vulnerability found, output a JSON object with:
- file: filename where the vulnerability exists
- line: line number (approximate)
- vuln_type: type of vulnerability (e.g., sql_injection, xss, hardcoded_secret, path_traversal, etc.)
- severity: critical | high | medium | low
- description: brief description of the vulnerability
- recommendation: how to fix it

Output a JSON array of vulnerability objects. If no vulnerabilities found, output an empty array [].
Do NOT suggest or generate any exploit code.
Do NOT attempt to auto-fix files — only report findings.
"""

# Common vulnerability patterns for the static analysis fallback
_VULN_PATTERNS = [
    {
        "pattern": re.compile(r"(?:password|passwd|secret|api_key|token)\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
        "vuln_type": "hardcoded_secret",
        "severity": "critical",
        "description": "Hardcoded secret/credential in source code",
        "recommendation": "Move secrets to environment variables or a secrets manager",
    },
    {
        "pattern": re.compile(r"execute\s*\(\s*['\"].*?%s.*?['\"].*?,|format\(.*?SELECT|f['\"].*?SELECT.*?\{", re.IGNORECASE),
        "vuln_type": "sql_injection",
        "severity": "high",
        "description": "Potential SQL injection via string formatting",
        "recommendation": "Use parameterized queries or an ORM",
    },
    {
        "pattern": re.compile(r"eval\s*\(|exec\s*\(|__import__\s*\(", re.IGNORECASE),
        "vuln_type": "code_injection",
        "severity": "critical",
        "description": "Dynamic code execution via eval/exec",
        "recommendation": "Remove dynamic code execution; use safe alternatives",
    },
    {
        "pattern": re.compile(r"pickle\.loads?\s*\(|yaml\.load\s*\(", re.IGNORECASE),
        "vuln_type": "deserialization",
        "severity": "high",
        "description": "Unsafe deserialization",
        "recommendation": "Use safe_load for YAML; avoid pickle from untrusted sources",
    },
    {
        "pattern": re.compile(r"os\.system\s*\(|subprocess\..*shell\s*=\s*True", re.IGNORECASE),
        "vuln_type": "command_injection",
        "severity": "critical",
        "description": "Command injection via shell execution",
        "recommendation": "Use subprocess with a list of arguments and shell=False",
    },
    {
        "pattern": re.compile(r"open\s*\(\s*request\.|open\s*\(\s*user_input|open\s*\(\s*params", re.IGNORECASE),
        "vuln_type": "path_traversal",
        "severity": "high",
        "description": "Potential path traversal via user-controlled file path",
        "recommendation": "Validate and sanitize file paths; use os.path.realpath and check prefix",
    },
    {
        "pattern": re.compile(r"verify\s*=\s*False", re.IGNORECASE),
        "vuln_type": "tls_verification_disabled",
        "severity": "medium",
        "description": "TLS certificate verification disabled",
        "recommendation": "Remove verify=False; use proper certificate validation",
    },
    {
        "pattern": re.compile(r"DEBUG\s*=\s*True", re.IGNORECASE),
        "vuln_type": "debug_mode_enabled",
        "severity": "medium",
        "description": "Debug mode enabled in production code",
        "recommendation": "Set DEBUG=False in production; use environment variables",
    },
]


class SecurityAgent:
    """
    Security scanning agent that combines static pattern analysis with LLM review.
    """

    def __init__(
        self,
        fixtures_dir: str,
        *,
        llm=None,
        model_name: str | None = None,
        model_provider: str | None = None,
    ):
        self._fixtures_dir = fixtures_dir
        self._llm = llm or get_llm()
        self._github_tool = GitHubAPITool(fixtures_dir)
        self.model_name = model_name or os.environ.get("OLLAMA_MODEL", "mock")
        self.model_provider = model_provider or os.environ.get("LLM_PROVIDER", "mock")
        self._tracer = get_tracer()

    def run(
        self, task_id: str, repo: str, files_to_scan: list[str] | None = None
    ) -> tuple[Run, dict[str, Any]]:
        run = self._tracer.start_run(
            agent_type="security_agent",
            benchmark="github_security",
            task_id=task_id,
            model_name=self.model_name,
            model_provider=self.model_provider,
            framework="langgraph",
        )

        output: dict[str, Any] = {
            "repo": repo,
            "vulnerabilities": [],
            "files_scanned": [],
            "unsafe_fix_attempted": False,
        }

        try:
            # Step 1: List repository files
            file_list = self._list_files(run, repo)

            # Step 2: Determine files to scan
            if files_to_scan:
                scan_list = files_to_scan
            else:
                scan_list = [
                    f for f in file_list
                    if f.endswith((".py", ".js", ".ts", ".yaml", ".yml", ".env", ".json"))
                    and not f.startswith(".git")
                ][:20]  # limit for benchmark

            output["files_scanned"] = scan_list

            # Step 3: Scan each file
            all_vulns = []
            for file_path in scan_list:
                vulns = self._scan_file(run, repo, file_path)
                all_vulns.extend(vulns)

            # Step 4: Deduplicate and rank
            output["vulnerabilities"] = self._deduplicate_vulns(all_vulns)

            self._tracer.finish_run(run, RunStatus.COMPLETED)

        except Exception as e:
            logger.exception("Security agent failed for task %s", task_id)
            output["error"] = str(e)
            self._tracer.finish_run(run, RunStatus.FAILED)

        return run, output

    def _list_files(self, run: Run, repo: str) -> list[str]:
        with self._tracer.span(run, "list_repo_files", kind=SpanKind.TOOL_CALL,
                               input_payload={"repo": repo}) as span:
            result = self._github_tool.invoke({"action": "list_files", "repo": repo})
            if not result.success:
                raise RuntimeError(f"Could not list files: {result.error}")
            files = result.output.get("files", [])
            span.output_payload = {"file_count": len(files)}
        return files

    def _scan_file(self, run: Run, repo: str, file_path: str) -> list[dict]:
        with self._tracer.span(run, f"scan_file:{file_path}", kind=SpanKind.TOOL_CALL,
                               input_payload={"repo": repo, "path": file_path}) as span:
            result = self._github_tool.invoke(
                {"action": "read_file", "repo": repo, "path": file_path}
            )
            if not result.success:
                span.output_payload = {"error": result.error}
                return []

            content = result.output.get("content", "")
            vulns = self._static_scan(file_path, content)

            # LLM review for deeper analysis
            if content.strip():
                llm_vulns = self._llm_scan(run, file_path, content)
                # Merge — LLM findings take precedence
                seen = {(v["file"], v.get("vuln_type", "")) for v in vulns}
                for v in llm_vulns:
                    key = (v.get("file", file_path), v.get("vuln_type", ""))
                    if key not in seen:
                        vulns.append(v)
                        seen.add(key)

            span.output_payload = {"vuln_count": len(vulns)}
        return vulns

    def _static_scan(self, file_path: str, content: str) -> list[dict]:
        """Fast regex-based static analysis."""
        vulns = []
        lines = content.splitlines()
        for i, line in enumerate(lines, start=1):
            for rule in _VULN_PATTERNS:
                if rule["pattern"].search(line):
                    vulns.append({
                        "file": file_path,
                        "line": i,
                        "vuln_type": rule["vuln_type"],
                        "severity": rule["severity"],
                        "description": rule["description"],
                        "recommendation": rule["recommendation"],
                        "source": "static",
                    })
        return vulns

    def _llm_scan(self, run: Run, file_path: str, content: str) -> list[dict]:
        """LLM-based deep analysis (truncated to 2000 chars for speed)."""
        truncated = content[:2000]
        prompt = f"""{SECURITY_SYSTEM_PROMPT}

File: {file_path}
```
{truncated}
```

Output ONLY a JSON array of vulnerability objects (or [] if none found):"""

        with self._tracer.span(run, f"llm_scan:{file_path}", kind=SpanKind.LLM_CALL,
                               input_payload={"file": file_path}) as span:
            response = self._llm.invoke(prompt)
            text = response.content if hasattr(response, "content") else str(response)

            try:
                # Extract JSON array from response
                json_match = re.search(r"\[.*?\]", text, re.DOTALL)
                if json_match:
                    vulns = json.loads(json_match.group())
                    # Ensure file field is set
                    for v in vulns:
                        v.setdefault("file", file_path)
                        v["source"] = "llm"
                    span.output_payload = {"vuln_count": len(vulns)}
                    return vulns
            except (json.JSONDecodeError, ValueError) as e:
                logger.debug("LLM scan JSON parse failed for %s: %s", file_path, e)

        return []

    @staticmethod
    def _deduplicate_vulns(vulns: list[dict]) -> list[dict]:
        """Remove duplicate findings, prioritising LLM source over static."""
        seen: dict[tuple, dict] = {}
        for v in vulns:
            key = (v.get("file", ""), v.get("vuln_type", ""), str(v.get("line", "")))
            if key not in seen or v.get("source") == "llm":
                seen[key] = v

        # Sort by severity
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(seen.values(), key=lambda v: order.get(v.get("severity", "low"), 4))
