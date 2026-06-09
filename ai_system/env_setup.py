"""
Helpers for loading OpenAI-compatible credentials from env vars or a local `.env`.
"""

import os
from pathlib import Path


def _parse_dotenv(dotenv_path: Path) -> dict:
    values = {}
    if not dotenv_path.exists():
        return values
    for raw_line in dotenv_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def setup_openai_env(
    api_key: str = None,
    base_url: str = None,
    dotenv_path: str = None,
):
    """
    Populate `OPENAI_API_KEY` and `OPENAI_BASE_URL` if possible.

    Precedence:
    1. Explicit arguments
    2. Existing environment variables
    3. A `.env` file in `dotenv_path`, cwd, or project root
    """

    dotenv_values = {}
    search_paths = []
    if dotenv_path:
        search_paths.append(Path(dotenv_path))
    search_paths.append(Path.cwd() / ".env")
    search_paths.append(Path(__file__).resolve().parent.parent / ".env")

    for path in search_paths:
        dotenv_values = _parse_dotenv(path)
        if dotenv_values:
            break

    resolved_api_key = (
        api_key
        or os.environ.get("OPENAI_API_KEY")
        or dotenv_values.get("OPENAI_API_KEY")
    )
    resolved_base_url = (
        base_url
        or os.environ.get("OPENAI_BASE_URL")
        or dotenv_values.get("OPENAI_BASE_URL")
    )

    for key, value in dotenv_values.items():
        if value and not os.environ.get(key):
            os.environ[key] = value

    if resolved_api_key and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = resolved_api_key
    if resolved_base_url and not os.environ.get("OPENAI_BASE_URL"):
        os.environ["OPENAI_BASE_URL"] = resolved_base_url
