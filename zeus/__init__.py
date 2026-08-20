"""Zeus agent harness."""

__version__ = "0.1.0"

# Import tools so they self-register
from zeus.tools import (  # noqa: F401
    browser,
    code_execution,
    database,
    file,
    git,
    memory_tools,
    sandbox,
    scheduler,
    terminal,
    user_profile_tools,
    web,
)
