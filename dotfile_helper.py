"""
Dotfile helper for ppm.
Copyright (c) 2026 Alan. All Rights Reserved.
"""

from typing import Any
from os import environ
from pathlib import Path


def LoadEnv(EnvFile=".ppm_paths") -> str | Any:
    EnvPath = Path(EnvFile)
    if not EnvPath.is_file():
        raise IsADirectoryError(
            f"File {str(EnvPath.as_posix())} is NOT a file, rather a directory."
        )
    for line in EnvPath.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            environ[key] = value
    return True
