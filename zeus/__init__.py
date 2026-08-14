"""Zeus agent harness."""

__version__ = "0.1.0"

# Import tools so they self-register
from zeus.tools import terminal, file, web, memory_tools, sandbox, git, code_execution, browser, database, scheduler  # noqa: F401
