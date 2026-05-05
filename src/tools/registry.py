"""Tool schema definitions in Anthropic API format."""

from typing import Any

ToolDefinition = dict[str, Any]

_READ_FILE: ToolDefinition = {
    "name": "read_file",
    "description": (
        "Read the full contents of a file. Use this to understand existing code, "
        "configuration, or documentation before making changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to the project root.",
            }
        },
        "required": ["path"],
    },
}

_LIST_DIRECTORY: ToolDefinition = {
    "name": "list_directory",
    "description": "List files and subdirectories at a given path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path relative to project root. Use '.' for the root.",
            }
        },
        "required": ["path"],
    },
}

_SEARCH_CODE: ToolDefinition = {
    "name": "search_code",
    "description": (
        "Search for a pattern in the codebase using grep. Use this to find usages, "
        "definitions, imports, or patterns across files."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "grep-compatible pattern to search for.",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in. Defaults to '.' (project root).",
            },
            "file_glob": {
                "type": "string",
                "description": "File glob to filter results, e.g. '*.py' or '*.ts'.",
            },
        },
        "required": ["pattern"],
    },
}

_GET_GIT_DIFF: ToolDefinition = {
    "name": "get_git_diff",
    "description": "Get the current git diff to see what has changed.",
    "input_schema": {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "If true, show only staged changes (--cached). Defaults to false.",
            },
            "path": {
                "type": "string",
                "description": "Optional path to limit the diff to a specific file or directory.",
            },
        },
    },
}

_GET_GIT_LOG: ToolDefinition = {
    "name": "get_git_log",
    "description": "Get recent git commit history to understand context and patterns.",
    "input_schema": {
        "type": "object",
        "properties": {
            "n": {
                "type": "integer",
                "description": "Number of commits to show. Defaults to 10.",
            },
            "path": {
                "type": "string",
                "description": "Optional path to show history for a specific file.",
            },
        },
    },
}

_RUN_SHELL: ToolDefinition = {
    "name": "run_shell",
    "description": (
        "Run a shell command in the project directory. Use for: running tests, "
        "checking types, linting, listing packages, getting git status. "
        "Destructive commands (rm -rf, git push, git reset --hard, sudo) are blocked."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute.",
            }
        },
        "required": ["command"],
    },
}

_WRITE_FILE: ToolDefinition = {
    "name": "write_file",
    "description": (
        "Write content to a file, creating parent directories as needed. "
        "Use for creating new files or fully replacing file content. "
        "For small changes, prefer read_file first to understand existing content."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to project root.",
            },
            "content": {
                "type": "string",
                "description": "Full content to write to the file.",
            },
        },
        "required": ["path", "content"],
    },
}

_PATCH_FILE: ToolDefinition = {
    "name": "patch_file",
    "description": (
        "Replace an exact string in a file with new content. "
        "Use this for targeted edits — read the file first to get the exact text to replace."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path relative to project root.",
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to find and replace. Must be unique in the file.",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement string.",
            },
        },
        "required": ["path", "old_string", "new_string"],
    },
}

# Tool sets per permission level
READONLY_TOOLS: list[ToolDefinition] = [
    _READ_FILE,
    _LIST_DIRECTORY,
    _SEARCH_CODE,
    _GET_GIT_DIFF,
    _GET_GIT_LOG,
    _RUN_SHELL,
]

WRITE_TOOLS: list[ToolDefinition] = [
    _READ_FILE,
    _LIST_DIRECTORY,
    _SEARCH_CODE,
    _GET_GIT_DIFF,
    _GET_GIT_LOG,
    _RUN_SHELL,
    _WRITE_FILE,
    _PATCH_FILE,
]

ALL_TOOLS = WRITE_TOOLS
