from __future__ import annotations

from typing import Any


def error_message(error: Any) -> str:
    if isinstance(error, BaseException):
        message = str(error).strip()
        if message:
            return f"{type(error).__name__}: {message}"
        return type(error).__name__
    return str(error)


def format_errors(errors: list[Any]) -> str:
    return "\n".join(f"- {error_message(error)}" for error in errors)


def operation_error(action: str, errors: list[Any]) -> ValueError:
    return ValueError(f"{action} failed:\n{format_errors(errors)}")
