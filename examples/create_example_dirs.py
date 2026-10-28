from sys import path
from pathlib import Path

ppm_path = Path(__file__).parent.parent
path.append(str(ppm_path))

from ppm.ppm import NewProject  # noqa

NewProject(
    "ddgs-search",
    "ddgs-search",
    "v1.0.0",
    "main.py",
    Author="TestPerson",
    License="GPL-3.0-only",
    Description="Simple program that searches for something using ddgs",
)
