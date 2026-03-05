"""
code_executor.py — Safe Python Sandbox for Agent Self-Improvement
Agents can write and execute Python code to analyse data and backtest strategies.
Only allows safe data-science imports. DB is read-only.
"""

import asyncio
import sys
import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
from typing import Any
from loguru import logger

# ── Whitelist of allowed imports ──────────────────────────
ALLOWED_MODULES = {
    "pandas", "pd",
    "numpy", "np",
    "math", "statistics", "datetime", "json", "re",
    "collections", "itertools", "functools",
    "scipy", "scipy.stats",
    "ta",           # technical analysis library
}

# ── Banned builtins ───────────────────────────────────────
BANNED_BUILTINS = {
    "open", "exec", "eval", "__import__",
    "compile", "globals", "locals", "vars",
    "breakpoint", "input",
}

MAX_RUNTIME_SECONDS = 30
MAX_OUTPUT_CHARS    = 5_000


class ExecutionResult:
    def __init__(self, stdout: str, stderr: str, error: str | None, success: bool):
        self.stdout  = stdout
        self.stderr  = stderr
        self.error   = error
        self.success = success

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output":  self.stdout[:MAX_OUTPUT_CHARS],
            "error":   self.error,
        }


def _build_safe_globals(db_data: dict | None = None) -> dict:
    """Build a restricted global scope for code execution."""
    import pandas as pd
    import numpy as np
    import math
    import statistics
    import json
    import re
    import datetime
    import collections

    safe_builtins = {k: v for k, v in __builtins__.items()
                     if k not in BANNED_BUILTINS} if isinstance(__builtins__, dict) \
                else {k: getattr(__builtins__, k) for k in dir(__builtins__)
                      if k not in BANNED_BUILTINS and not k.startswith("_")}

    globs = {
        "__builtins__": safe_builtins,
        "pd": pd, "pandas": pd,
        "np": np, "numpy": np,
        "math": math,
        "statistics": statistics,
        "json": json,
        "re": re,
        "datetime": datetime,
        "collections": collections,
        "print": print,
    }

    # Inject pre-fetched DB data if provided
    if db_data:
        globs.update(db_data)

    return globs


async def execute_code(
    code: str,
    db_data: dict | None = None,
    timeout: int = MAX_RUNTIME_SECONDS,
) -> ExecutionResult:
    """
    Execute agent-written Python code in a sandboxed environment.

    Args:
        code:     Python code string to execute
        db_data:  Optional pre-fetched DataFrames/dicts injected as variables
        timeout:  Max execution time in seconds

    Returns:
        ExecutionResult with stdout, stderr, and success flag
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    safe_globals = _build_safe_globals(db_data)

    def _run():
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exec(compile(code, "<agent_code>", "exec"), safe_globals)  # noqa: S102

    try:
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, _run),
            timeout=timeout,
        )
        output = stdout_buf.getvalue()
        logger.debug(f"[EXECUTOR] Success. Output: {len(output)} chars")
        return ExecutionResult(stdout=output, stderr=stderr_buf.getvalue(),
                               error=None, success=True)

    except asyncio.TimeoutError:
        msg = f"Execution timed out after {timeout}s"
        logger.warning(f"[EXECUTOR] {msg}")
        return ExecutionResult(stdout="", stderr="", error=msg, success=False)

    except Exception as e:
        err = traceback.format_exc()
        logger.warning(f"[EXECUTOR] Error: {e}")
        return ExecutionResult(stdout=stdout_buf.getvalue(), stderr="",
                               error=err[:2000], success=False)


# ── Convenience: execute with candle data pre-loaded ─────
async def execute_with_candles(code: str, symbol: str, timeframe: str = "1h", limit: int = 200) -> ExecutionResult:
    """Pre-load candle data as `df` and inject into the execution scope."""
    from data.indicators import get_candles
    df = await get_candles(symbol, timeframe, limit)
    return await execute_code(code, db_data={"df": df, "symbol": symbol})
