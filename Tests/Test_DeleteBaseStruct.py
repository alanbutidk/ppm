# ruff: noqa
from AddSrcDirToPyImportPath import AddPPMDirPath

AddPPMDirPath()

from ppm import delete_base

delete_base(color=True, delete_ppm_paths=True)
