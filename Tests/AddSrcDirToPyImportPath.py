import sys
from pathlib import Path


def AddPPMDirPath():
    TDir = Path(__file__).resolve().parent.parent / "src"
    sys.path.append(str(TDir))
