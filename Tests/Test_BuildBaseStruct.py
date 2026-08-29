"""This test showcases the build_venv function to build the base struct."""

# ruff: noqa

from AddSrcDirToPyImportPath import AddPPMDirPath

AddPPMDirPath()

from os import chdir
from pathlib import Path
from ppm import build_base

testdir = Path("test").mkdir(parents=True, exist_ok=True)
chdir("Test")

build_base(color=True, shush=False)
