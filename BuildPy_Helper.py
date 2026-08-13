"""
Build Python helper, Exposes a API that allows the main ppm module to build programs.
----------
Options:
- Nuitka
- Pyinstaller
Unstable:
- PyCC (No development done for PyCC Building).
---------
Copyright (c) 2026 Alan. All Rights Reserved.
"""
# pyright: reportArgumentType=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportUnusedImport=false
# pyright: reportUnusedVariable=false
# From-imports:
from pathlib import Path
from sys import executable, platform
from subprocess import run
from importlib.util import find_spec
from typing import Any

# We check if our powerhouses are importable under THIS interpreter — this is
# only used for informational purposes (e.g. `ppm build --check`); the actual
# build always subprocesses into the target interpreter (see Builder below),
# since a backend installed into a project venv isn't importable from here.
PyinstallerSpec = find_spec("pyinstaller")
NuitkaSpec = find_spec("nuitka")
_pyi = 1 if PyinstallerSpec is not None else 0
_n = 1 if NuitkaSpec is not None else 0


def InstallPkgFromPip(
    pipPath: str | Path, pkg: str, printR: bool = False
) -> Any | bool:
    if isinstance(pipPath, Path):
        if not pipPath.exists():
            if printR:
                print(
                    f"\033[31mPath to pip was not found, Given PATH: {pipPath}\033[0m"
                )
            return False
        pipPath = str(pipPath)
    irun = run([pipPath, "install", pkg], capture_output=True, text=True)
    if irun.returncode != 0:
        if printR:
            print(
                f"\033[31mSomething happened while install {pkg}, errno: {irun.returncode}. Error output: {irun.stderr}!\033[0m"
            )
        return False
    return True


class Builder:
    def __init__(
        self,
        PyI: bool = False,
        Nuitka: bool = False,
        InstallPyI_IfNotFound: bool = False,
        InstallN_IfNotFound: bool = False,
    ):
        self.pyi = PyI
        self.n = Nuitka
        self.installpyi = InstallPyI_IfNotFound
        self.installn = InstallN_IfNotFound

    @staticmethod
    def _module_importable(python_path: str, module: str) -> bool:
        """Checks whether `module` is importable under the given interpreter
        by actually asking it, rather than trusting find_spec() from the ppm
        process's own interpreter (which may differ from the target venv)."""
        Result = run([python_path, "-c", f"import {module}"], capture_output=True, text=True)
        return Result.returncode == 0

    def _ensure_backend(self, pip_path: str | Path, python_path: str, import_name: str, want: bool, auto_install: bool, shush: bool) -> bool:
        """Shared readiness check: makes sure the chosen backend is actually
        importable under the TARGET interpreter (python_path), installing it
        via the target's pip on the fly if asked to."""
        if not want:
            return False
        if self._module_importable(python_path, import_name):
            return True
        if not auto_install:
            if not shush:
                print(f"\033[31m{import_name} is not installed under {python_path} and auto-install was not requested.\033[0m")
            return False
        if not shush:
            print(f"\033[33m{import_name} not found, installing...\033[0m")
        pkg_name = "pyinstaller" if import_name == "PyInstaller" else import_name
        ok = InstallPkgFromPip(pip_path, pkg_name, printR=not shush)
        if not ok:
            if not shush:
                print(f"\033[31mFailed to install {pkg_name}.\033[0m")
            return False
        if not self._module_importable(python_path, import_name):
            if not shush:
                print(f"\033[31m{import_name} still not importable under {python_path} after install.\033[0m")
            return False
        return True

    def NuitkaBuild(
        self,
        FileName: str | Path,
        *args,
        PipPath: str | Path = "pip",
        PythonPath: str | Path = None,
        ShallRemoveJunk: bool = False,
        Shush: bool = False,
    ) -> bool:
        if isinstance(FileName, Path):
            if not FileName.exists():
                if not Shush:
                    print(
                        f"\033[31m{str(FileName)} is NOT a real file. Please check the path and retry.\033[0m"
                    )
                return False
            FileName = str(FileName)
        elif not Path(FileName).exists():
            if not Shush:
                print(
                    f"\033[31m{FileName} is NOT a real file. Please check the path and retry.\033[0m"
                )
            return False

        RunnerPython = str(PythonPath) if PythonPath else executable
        ready = self._ensure_backend(PipPath, RunnerPython, "nuitka", self.n, self.installn, Shush)
        if not ready:
            return False

        cmd = [RunnerPython, "-m", "nuitka", *args, FileName]
        if not Shush:
            print(f"\033[33m> {' '.join(cmd)}\033[0m")
        Result = run(cmd, capture_output=Shush, text=True)

        if Result.returncode != 0:
            if not Shush:
                stderr = getattr(Result, "stderr", None)
                print(f"\033[31mNuitka build failed (exit {Result.returncode}).{f' {stderr}' if stderr else ''}\033[0m")
            return False

        if ShallRemoveJunk:
            self._remove_nuitka_junk(FileName)

        if not Shush:
            print("\033[36mNuitka build finished!\033[0m")
        return True

    @staticmethod
    def _remove_nuitka_junk(FileName: str):
        """Removes Nuitka's intermediate build directory (<name>.build) and
        the .dist folder's non-essential cache artifacts, keeping the final binary."""
        from shutil import rmtree

        stem = Path(FileName).stem
        for suffix in (".build", ".onefile-build"):
            junk = Path(f"{stem}{suffix}")
            if junk.is_dir():
                rmtree(junk, ignore_errors=True)

    def PyinstallerBuild(
        self,
        FileName: str | Path,
        *args,
        PipPath: str | Path = "pip",
        PythonPath: str | Path = None,
        OneFile: bool = True,
        ShallRemoveJunk: bool = False,
        Shush: bool = False,
    ) -> bool:
        if isinstance(FileName, Path):
            if not FileName.exists():
                if not Shush:
                    print(
                        f"\033[31m{str(FileName)} is NOT a real file. Please check the path and retry.\033[0m"
                    )
                return False
            FileName = str(FileName)
        elif not Path(FileName).exists():
            if not Shush:
                print(
                    f"\033[31m{FileName} is NOT a real file. Please check the path and retry.\033[0m"
                )
            return False

        RunnerPython = str(PythonPath) if PythonPath else executable
        ready = self._ensure_backend(PipPath, RunnerPython, "PyInstaller", self.pyi, self.installpyi, Shush)
        if not ready:
            return False

        cmd_args = list(args)
        if OneFile and "--onefile" not in cmd_args and "-F" not in cmd_args:
            cmd_args.append("--onefile")
        cmd_args.append(FileName)

        cmd = [RunnerPython, "-m", "PyInstaller", *cmd_args]
        if not Shush:
            print(f"\033[33m> {' '.join(cmd)}\033[0m")
        Result = run(cmd, capture_output=Shush, text=True)

        if Result.returncode != 0:
            if not Shush:
                stderr = getattr(Result, "stderr", None)
                print(f"\033[31mPyInstaller build failed (exit {Result.returncode}).{f' {stderr}' if stderr else ''}\033[0m")
            return False

        if ShallRemoveJunk:
            self._remove_pyinstaller_junk(FileName)

        if not Shush:
            print("\033[36mPyInstaller build finished!\033[0m")
        return True

    @staticmethod
    def _remove_pyinstaller_junk(FileName: str):
        """Removes PyInstaller's build/ dir and generated .spec file, keeping dist/."""
        from shutil import rmtree

        stem = Path(FileName).stem
        BuildDir = Path("build")
        if BuildDir.is_dir():
            rmtree(BuildDir, ignore_errors=True)
        SpecFile = Path(f"{stem}.spec")
        if SpecFile.is_file():
            SpecFile.unlink()

    def Build(
        self,
        FileName: str | Path,
        *args,
        PipPath: str | Path = "pip",
        PythonPath: str | Path = None,
        ShallRemoveJunk: bool = False,
        Shush: bool = False,
    ) -> bool:
        """Convenience dispatcher: builds with whichever backend was
        requested at construction time (self.pyi / self.n). If both are
        requested, Nuitka runs first, then PyInstaller."""
        ran_any = False
        ok = True

        if self.n:
            ran_any = True
            ok = self.NuitkaBuild(FileName, *args, PipPath=PipPath, PythonPath=PythonPath, ShallRemoveJunk=ShallRemoveJunk, Shush=Shush) and ok
        if self.pyi:
            ran_any = True
            ok = self.PyinstallerBuild(FileName, *args, PipPath=PipPath, PythonPath=PythonPath, ShallRemoveJunk=ShallRemoveJunk, Shush=Shush) and ok

        if not ran_any and not Shush:
            print("\033[31mNo build backend selected (PyI/Nuitka both False).\033[0m")
            return False
        return ok
