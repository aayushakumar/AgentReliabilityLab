"""File reader tool — MCP-wrapped, policy-guarded."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from packages.mcp_tools.base import BaseTool, ToolSchema
from packages.policies.filesystem_policy import FilesystemPolicy


class FileReaderTool(BaseTool):
    schema: ClassVar[ToolSchema] = ToolSchema(
        name="file_read",
        description=(
            "Read the contents of a file. "
            "Only files within the allowed read directories can be accessed."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read."},
                "encoding": {"type": "string", "description": "File encoding (default: utf-8)."},
            },
            "required": ["path"],
        },
    )

    def __init__(self, allowed_dirs: list[str], policy_engine=None):
        super().__init__(policy_engine=policy_engine)
        self._fs_policy = FilesystemPolicy(
            sandbox_dir=allowed_dirs[0] if allowed_dirs else "./sandbox",
            allowed_read_dirs=allowed_dirs,
        )

    def _execute(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        path = input_dict["path"]
        encoding = input_dict.get("encoding", "utf-8")

        result = self._fs_policy.check_read(path)
        if not result.is_allowed:
            raise ValueError(f"File read blocked: {result.reason}")

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not p.is_file():
            raise ValueError(f"Not a file: {path}")

        content = p.read_text(encoding=encoding)
        return {
            "path": str(p),
            "content": content,
            "size_bytes": p.stat().st_size,
            "lines": content.count("\n") + 1,
        }


class FileWriterTool(BaseTool):
    schema: ClassVar[ToolSchema] = ToolSchema(
        name="file_write",
        description="Write content to a file within the sandbox directory.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write to (must be inside sandbox)."},
                "content": {"type": "string", "description": "Content to write."},
                "append": {"type": "string", "description": "If 'true', append instead of overwrite."},
            },
            "required": ["path", "content"],
        },
    )

    def __init__(self, sandbox_dir: str, policy_engine=None):
        super().__init__(policy_engine=policy_engine)
        self._fs_policy = FilesystemPolicy(sandbox_dir=sandbox_dir)
        self._sandbox = Path(sandbox_dir)

    def _execute(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        path = input_dict["path"]
        content = input_dict["content"]
        append = input_dict.get("append", "false").lower() == "true"

        result = self._fs_policy.check_write(path)
        if not result.is_allowed:
            raise ValueError(f"File write blocked: {result.reason}")

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(p, mode) as f:
            f.write(content)

        return {"path": str(p), "bytes_written": len(content.encode()), "append": append}
