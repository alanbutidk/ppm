# ruff: noqa

from AddSrcDirToPyImportPath import AddPPMDirPath

AddPPMDirPath()

from ppm import InitProject

InitProject(
    ProjName="test",
    ProjVer="v1.0.0",
    MainFile="main.py",
    Yes=False,
    Author="ppm_user",
    License="GPL-3.0-only",
    Description="Test to showcase ppm",
    Silent=False,
)
