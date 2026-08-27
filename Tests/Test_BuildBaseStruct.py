"""This test showcases the build_venv function to build the base struct."""

# ruff: noqa

from AddSrcDirToPyImportPath import AddPPMDirPath

AddPPMDirPath()

from ppm import build_venv

build_venv(color=True, shush=False)
