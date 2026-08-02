"""
ppm, the python project manager.
Copyright (c) 2026 Alan. All Rights Reserved.
"""

# from-based imports
from typing import Any, Optional
from venv import create
from pathlib import Path
from sys import platform, argv, executable
from sys import exit as e  # This decision was taken after this whole file was written.
from subprocess import run
from os import environ, chdir, pathsep
from shutil import rmtree, copy2
from re import split

# Custom files:
from dotfile_helper import LoadEnv
from TOMLFile_Helper import TOMLArrayOfTables, TOMLDocument, TOMLTable
from CloneRepoHandler import CloneRepoHandler, CloneError
from BuildPy_Helper import Builder

# Only import-based imports:
import tomllib
import urllib.request
import json

EXE = ".exe" if platform == "win32" else ""


# Classes that can be raised
class DependsError(Exception):
    pass


def build_venv(color=False, shush=False) -> bool | tuple:
    if color:
        YLW = "\033[33m"
        RST = "\033[0m"
    else:
        YLW = ""
        RST = ""

    EnvDir = Path(".venv").resolve().as_posix()
    create(EnvDir, with_pip=True)
    BinDir = "Scripts" if platform == "win32" else "bin"
    Paths = [
        f'PPM_DIR="{str(Path(EnvDir).parent).replace("\\", "/")}/"',
        f'PPM_PYTHON="{EnvDir}/{BinDir}/python{EXE}"',
        f'PPM_PIP="{EnvDir}/{BinDir}/pip{EXE}"',
    ]

    with open(".ppm_paths", "w") as f:
        f.writelines(line + "\n" for line in Paths)
    PPMScriptName = "ppm.bat" if platform == "win32" else "ppm.sh"
    with open(".gitignore", "w") as f:
        f.write(f".ppm_paths\n.venv\n{PPMScriptName}")
    if not shush:
        print(f"{YLW}Created venv at: {EnvDir}{RST}")
        print(f'{YLW}PPM has placed venv paths at: ".ppm_paths"!{RST}')
    return (EnvDir, Paths)


def delete_venv(color=False, delete_ppm_paths=False) -> bool | None:
    if color:
        YLW = "\033[33m"
        RST = "\033[0m"
    else:
        YLW = ""
        RST = ""
    DIR = ".venv"
    PPM_FILE = ".ppm_paths"
    rmtree(DIR, ignore_errors=True)
    print(f"{YLW}Removed .venv directory!{RST}")
    try:
        if delete_ppm_paths:
            Path(PPM_FILE).unlink()
            print(f"{YLW}Removed .ppm_paths file!{RST}")
    except OSError:
        pass


class DependsHandler:
    def __init__(self, Depends: list = None):
        self.depends = Depends
        self.lock_file = Path("ppm.lock")
        if Path(".ppm_paths").is_file():
            LoadEnv()

    def _get_pip_path(self) -> str:
        """Helper to fetch the active pip executable path."""
        BinDir = "Scripts" if platform == "win32" else "bin"
        return environ.get("PPM_PIP", f".venv/{BinDir}/pip{EXE}")

    def _read_lockfile(self) -> list:
        """Reads the current lock file using built-in tomllib parser."""
        if not self.lock_file.exists():
            return []
        try:
            # tomllib requires binary mode execution
            with self.lock_file.open("rb") as f:
                data = tomllib.load(f)
                return data.get("package", [])
        except Exception:
            return []

    def _write_lockfile(self, packages: list):
        """Saves package mutations using your imported custom TOML writer."""
        doc = TOMLDocument()
        PkgArray = doc.add_array(TOMLArrayOfTables("package"))
        for pkg in packages:
            entry = PkgArray.create_entry()
            for k, v in pkg.items():
                entry.add(k, v)
        self.lock_file.write_text(doc.render(), encoding="utf-8")

    def _fetch_installed_metadata(self, pkg_name: str) -> dict:
        """Inspects the local environment and PyPI to build a locked entry."""
        # Ask local pip what exact version got installed
        pip_show = run(
            [self._get_pip_path(), "show", pkg_name], capture_output=True, text=True
        )
        version = "unknown"
        if pip_show.returncode == 0:
            for line in pip_show.stdout.splitlines():
                if line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()
                    break

        # Ping PyPI JSON API to extract the real checksum hash
        checksum = "unknown"
        try:
            url = f"https://pypi.org/pypi/{pkg_name}/{version}/json"
            with urllib.request.urlopen(url, timeout=3) as response:
                pypi_data = json.loads(response.read().decode())
                releases = pypi_data.get("urls", [])
                wheel = next(
                    (r for r in releases if r.get("packagetype") == "bdist_wheel"), None
                )
                chosen = wheel or (releases[0] if releases else None)
                if chosen:
                    checksum = chosen["digests"]["sha256"]
        except Exception:
            pass

        return {
            "name": pkg_name,
            "version": version,
            "source": "registry+https://pypi.org",
            "checksum": checksum,
            "dependencies": [],
        }

    def _normalize_pkg_name(self, spec: str) -> str:
        return split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip()

    def InstallDepends(self, dry_run: bool = False):
        if self.depends is None:
            raise DependsError("NO Dependencies provided with DependsHandler.")

        packages = self._read_lockfile()

        for i in self.depends:
            name = self._normalize_pkg_name(i)
            if dry_run:
                existing = next(
                    (p for p in packages if p["name"].lower() == name.lower()), None
                )
                if existing and existing.get("version") != "carted":
                    print(
                        f"\033[33m[dry-run] would reinstall/update {i} (currently {existing.get('version')})\033[0m"
                    )
                else:
                    print(f"\033[33m[dry-run] would install {i}\033[0m")
                continue

            Run = run(
                [self._get_pip_path(), "install", i],
                capture_output=True,
                text=True,
            )
            if Run.returncode != 0:
                raise DependsError(
                    f"Error while installing: {i}, Error Output: {Run.stderr}"
                )

            # Remove any pre-existing entry (or cart entry) before locking the real installation
            packages = [p for p in packages if p["name"].lower() != name.lower()]

            # Generate layout snapshot and append to file state
            meta = self._fetch_installed_metadata(name)
            packages.append(meta)

        if dry_run:
            return
        self._write_lockfile(packages)
        print("\033[36mFinished install(s)!\033[0m")

    def DeleteDepends(self, DependsToDel: list, dry_run: bool = False):
        if DependsToDel is None:
            raise DependsError("No dependencies provided with DeleteDepends.")

        packages = self._read_lockfile()

        for i in DependsToDel:
            if dry_run:
                name = self._normalize_pkg_name(i)
                present = any(p["name"].lower() == name.lower() for p in packages)
                if present:
                    print(f"\033[33m[dry-run] would uninstall {i}\033[0m")
                else:
                    print(
                        f"\033[33m[dry-run] {i} is not tracked; nothing to uninstall\033[0m"
                    )
                continue

            Run = run(
                [self._get_pip_path(), "uninstall", i, "-y"],
                capture_output=True,
                text=True,
            )
            if Run.returncode != 0:
                raise DependsError(
                    f"Error while deleting/uninstalling: {i}, Error Output: {Run.stderr}"
                )

            packages = [p for p in packages if p["name"].lower() != i.lower()]

        if dry_run:
            return
        self._write_lockfile(packages)
        print("\033[36mUninstalled package(s)!\033[0m")

    def CartDepend(self, DependsToCart: list):
        """Adds a package entry directly to the lockfile without invoking pip install."""
        if DependsToCart is None:
            raise DependsError("No dependencies provided with CartDepend.")

        packages = self._read_lockfile()

        for i in DependsToCart:
            name = self._normalize_pkg_name(i)
            # Prevent duplicating entries if already carted or installed (match by real name)
            if any(p["name"].lower() == name.lower() for p in packages):
                continue

            cart_meta = {
                "name": name,
                "version": "carted",
                "source": "cart",
                "checksum": "pending",
                "dependencies": [],
                "spec": i,  # preserves any version constraint (e.g. "click==8.1.7") for order/install
            }
            packages.append(cart_meta)

        self._write_lockfile(packages)
        print("\033[36mCarted dependencies!\033[0m")

    def RemoveFromCartDepend(self, DependsToUncart: list):
        """Removes a carted or pending dependency string from the lockfile array."""
        if DependsToUncart is None:
            raise DependsError("No dependencies provided with RemoveFromCartDepend.")

        packages = self._read_lockfile()

        to_remove = {self._normalize_pkg_name(name).lower() for name in DependsToUncart}
        packages = [p for p in packages if p["name"].lower() not in to_remove]

        self._write_lockfile(packages)
        print("\033[36mUncarted dependencies!\033[0m")

    def OrderCarted(self):
        """Installs every package currently marked as 'carted' in the lockfile,
        using their preserved spec (with version pin, if any) rather than just the name."""
        packages = self._read_lockfile()
        carted = [
            p.get("spec", p["name"]) for p in packages if p.get("version") == "carted"
        ]
        if not carted:
            return
        self.depends = carted
        self.InstallDepends()
        print("\033[36mOrder finished for carted dependencies!\033[0m")

    def ListDepends(self):
        """Prints every package tracked in the lockfile, split into installed vs carted."""
        packages = self._read_lockfile()
        if not packages:
            print("\033[33mNo dependencies tracked in ppm.lock.\033[0m")
            return

        installed = [p for p in packages if p.get("version") != "carted"]
        carted = [p for p in packages if p.get("version") == "carted"]

        if installed:
            print("\033[36mInstalled:\033[0m")
            for p in installed:
                print(f"  \033[33m{p['name']}\033[0m == {p.get('version', 'unknown')}")
        if carted:
            print("\033[36mCarted (not yet installed):\033[0m")
            for p in carted:
                print(f"  \033[33m{p['name']}\033[0m")

    def UpdateDepends(
        self, DependsToUpdate: Optional[list] = None, dry_run: bool = False
    ):
        """Reinstalls packages with --upgrade and refreshes their lockfile entries.
        If DependsToUpdate is None, every currently-installed (non-carted) package is updated."""
        packages = self._read_lockfile()
        installed = [p["name"] for p in packages if p.get("version") != "carted"]

        if DependsToUpdate:
            targets = [
                p
                for p in DependsToUpdate
                if p.lower() in {n.lower() for n in installed}
            ]
            missing = [
                p
                for p in DependsToUpdate
                if p.lower() not in {n.lower() for n in installed}
            ]
            for m in missing:
                print(f"\033[33m{m} is not installed, skipping.\033[0m")
        else:
            targets = installed

        if not targets:
            print("\033[33mNothing to update.\033[0m")
            return

        if dry_run:
            for i in targets:
                current = next(
                    (
                        p.get("version")
                        for p in packages
                        if p["name"].lower() == i.lower()
                    ),
                    "unknown",
                )
                print(
                    f"\033[33m[dry-run] would update {i} (currently {current})\033[0m"
                )
            return

        for i in targets:
            Run = run(
                [self._get_pip_path(), "install", "--upgrade", i],
                capture_output=True,
                text=True,
            )
            if Run.returncode != 0:
                raise DependsError(
                    f"Error while updating: {i}, Error Output: {Run.stderr}"
                )
            packages = [p for p in packages if p["name"].lower() != i.lower()]
            meta = self._fetch_installed_metadata(self._normalize_pkg_name(i))
            packages.append(meta)

        self._write_lockfile(packages)
        print("\033[36mFinished update(s)!\033[0m")


class ProjectTOMLHandler:
    def __init__(self, projname: str):
        self.toml_name = Path("ppm.toml")
        self.projname = projname
        self.scripts = {}

    def SetMeta(self, version: str, main_file: str):
        self.version = version
        self.main_file = main_file

    def SetScripts(self, scripts: dict):
        self.scripts = scripts or {}

    def BuildTOML(self, DontWriteDoNotEdit=False):
        doc = TOMLDocument()
        ProjArray = doc.add_array(TOMLArrayOfTables(self.projname))
        entry = ProjArray.create_entry()
        entry.add("project_name", self.projname)
        entry.add("Version", self.version)
        entry.add("main_file", self.main_file)
        if self.scripts:
            ScriptsTable = TOMLTable("scripts")
            for name, cmd in self.scripts.items():
                ScriptsTable.add(name, cmd)
            doc.add_table(ScriptsTable)
        if DontWriteDoNotEdit:
            toml_string = doc.render(dontwrite_dontedit=True)
        else:
            toml_string = doc.render()
        self.toml_name.write_text(toml_string, encoding="utf-8")
        return toml_string


def RuffCheck(File: str, fix=False) -> bool | tuple:
    if fix:
        CMD = f"check {File} --fix"
    else:
        CMD = f"check {File}"

    RuffPath = (
        (Path(__file__).parent / "Scripts" / "ruff" / f"ruff{EXE}").resolve().as_posix()
    )
    CMD = f"{RuffPath} {CMD}"
    Run = run(CMD.split(), capture_output=True, text=True)
    if Run.returncode != 0:
        print(
            f"\033[31mGot error from ruff, Error Number: {Run.returncode}\033[0m, Output: {Run.stderr}"
        )
        return (False, Run.returncode, Run.stderr)
    print("\033[36mPassed ruff-test! No errors found...\033[0m")
    return (True, Run.returncode, Run.stdout)


def ClearRuffCache() -> None | bool:
    Dir = Path(".ruff_cache").resolve().as_posix()
    rmtree(Dir, ignore_errors=True)
    print("\033[36mCleared ruff-cache!\033[0m")


def NewProject(
    DirName: str = None,
    ProjName: str = None,
    ProjVer: str = None,
    MainFile: str = None,
    Yes: bool = False,
) -> Any | None:
    YLW = "\033[33m"
    # RED = "\033[31m"
    CYN = "\033[36m"  # Uncomment when needed.
    RST = "\033[0m"

    if DirName is None:
        if Yes:
            DirName = "new-project"
        else:
            DirName = str(
                input(f"{YLW}Directory name (Full PATH if you want to): {RST}")
            )
    Path(DirName).mkdir(parents=True, exist_ok=True)
    chdir(DirName)
    InitProject(ProjName, ProjVer, MainFile, Yes=Yes)
    print(f"{CYN}Created project in directory: {DirName}!{RST}")


def InitProject(
    ProjName: str = None, ProjVer: str = None, MainFile: str = None, Yes: bool = False
):
    YLW = "\033[33m"
    # RED = "\033[31m"
    CYN = "\033[36m"
    RST = "\033[0m"
    if ProjName is None:
        ProjName = Path.cwd().name if Yes else str(input(f"{YLW}Program name: {RST}"))
    if ProjVer is None:
        ProjVer = "0.1.0" if Yes else str(input(f"{YLW}Program version: {RST}"))
    if MainFile is None:
        MainFile = "main.py" if Yes else str(input(f"{YLW}Project main file: {RST}"))

    print(f"{YLW}Initializing project{RST} {CYN}{ProjName}: {ProjVer}!{RST}")
    build_venv(color=True, shush=True)
    TOML = ProjectTOMLHandler(ProjName)
    TOML.SetMeta(ProjVer, MainFile)
    TOML.BuildTOML(DontWriteDoNotEdit=True)

    MainFilePath = Path(MainFile)
    if not MainFilePath.exists():
        MainFilePath.parent.mkdir(parents=True, exist_ok=True)
        MainFilePath.write_text('print("Hello, world!")\n', encoding="utf-8")
        print(f"{YLW}Created main file: {MainFile}{RST}")

    if Path(".ppm_paths").exists():
        LoadEnv()
    DEFAULT_JSON_PYRIGHT = """
{
    \"venvPath\": \".venv\",
    \"venv\": \".venv\"
}
    """
    with open(f"{environ['PPM_DIR']}/pyrightconfig.json", "w") as f:
        f.write(DEFAULT_JSON_PYRIGHT)

    ExpandedPath = Path(__file__).resolve().parent
    ExpandedPathFile = Path(__file__).resolve()
    PPMScriptDir = ExpandedPath / "Scripts" / "ppm"

    PPMScript = PPMScriptDir / "ppm.bat" if platform == "win32" else "ppm.sh"
    with open(PPMScript, "r", encoding="utf-8") as f:
        content = f.read()
        UpdatedCnt = content.replace("REPLACE_WITH_PATH", str(ExpandedPathFile))
        FileName = "ppm.bat" if platform == "win32" else "ppm.sh"

        with open(f"{environ['PPM_DIR']}/{FileName}", "w") as file:
            file.write(UpdatedCnt)

    print("\033[36mInitialized project!\033[0m")


def DeInitProject() -> None | bool:
    # YLW = "\033[33m" # Uncomment this when needed.
    # RED = "\033[31m" # Uncomment this when needed.
    CYN = "\033[36m"
    RST = "\033[0m"
    delete_venv(color=True, delete_ppm_paths=True)
    Path(".gitignore").unlink() if Path(".gitignore").exists() else ""
    Path("ppm.lock").unlink() if Path("ppm.lock").exists() else ""
    Path("ppm.toml").unlink() if Path("ppm.toml").exists() else ""
    Path("pyrightconfig.json").unlink() if Path("ppm.lock").exists() else ""

    print(f"{CYN}Deinitialized project!{RST}")
    return True


def _GetMainFileFromTOML() -> Optional[str]:
    """Reads the main_file entry back out of ppm.toml, if it exists."""
    TomlPath = Path("ppm.toml")
    if not TomlPath.is_file():
        return None
    try:
        with TomlPath.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return None
    for entries in data.values():
        if isinstance(entries, list):
            for entry in entries:
                if "main_file" in entry:
                    return entry["main_file"]
    return None


def _GetScriptsFromTOML() -> dict:
    """Reads the [scripts] table out of ppm.toml, if present."""
    TomlPath = Path("ppm.toml")
    if not TomlPath.is_file():
        return {}
    try:
        with TomlPath.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}
    scripts = data.get("scripts", {})
    return scripts if isinstance(scripts, dict) else {}


def RunProject(MainFile: str, use_global: bool = False) -> bool:
    """Runs the project using either the local venv python or the system-global python."""
    if use_global:
        PythonPath = executable
    else:
        LoadEnv()
        BinDir = "Scripts" if platform == "win32" else "bin"
        PythonPath = environ.get("PPM_PYTHON", f".venv/{BinDir}/python{EXE}")
    Run = run([PythonPath, MainFile])
    return Run.returncode == 0


def RunScriptCommand(ScriptName: str) -> bool:
    """Runs a named command from ppm.toml's [scripts] table, using a shell
    so scripts can be arbitrary commands (not just python invocations)."""
    scripts = _GetScriptsFromTOML()
    if ScriptName not in scripts:
        available = ", ".join(scripts) if scripts else "(none defined)"
        print(
            f"\033[31mNo script named '{ScriptName}' in ppm.toml. Available: {available}\033[0m"
        )
        return False

    LoadEnv()
    BinDir = "Scripts" if platform == "win32" else "bin"
    VenvBin = Path(
        environ.get("PPM_PYTHON", f".venv/{BinDir}/python{EXE}")
    ).parent.resolve()
    Env = environ.copy()
    if VenvBin.is_dir():
        Env["PATH"] = f"{VenvBin}{pathsep}{Env.get('PATH', '')}"

    print(f"\033[33m> {scripts[ScriptName]}\033[0m")
    Result = run(scripts[ScriptName], shell=True, env=Env)
    return Result.returncode == 0


def CartCommand(Depends: list):
    """Carts the given dependencies into the lockfile."""
    Handler = DependsHandler()
    Handler.CartDepend(Depends)


def DecartCommand(Depends: list):
    """Decarts (removes) the given dependencies from the lockfile."""
    Handler = DependsHandler()
    Handler.RemoveFromCartDepend(Depends)


def OrderCommand():
    """Installs all carted packages found in the lockfile."""
    Handler = DependsHandler()
    Handler.OrderCarted()


def ListCommand():
    """Lists installed and carted dependencies from the lockfile."""
    Handler = DependsHandler()
    Handler.ListDepends()


def UpdateCommand(Depends: Optional[list] = None, dry_run: bool = False):
    """Updates the given dependencies (or all installed ones) to their latest version."""
    Handler = DependsHandler()
    Handler.UpdateDepends(Depends if Depends else None, dry_run=dry_run)


def StatusCommand():
    """Prints an overview of the current project: metadata, venv state, and dependency counts."""
    ProjName = None
    ProjVer = None
    MainFile = None
    TomlPath = Path("ppm.toml")
    if TomlPath.is_file():
        try:
            with TomlPath.open("rb") as f:
                data = tomllib.load(f)
            for name, entries in data.items():
                if isinstance(entries, list) and entries:
                    ProjName = entries[0].get("project_name", name)
                    ProjVer = entries[0].get("Version")
                    MainFile = entries[0].get("main_file")
                    break
        except Exception:
            pass

    print(
        f"\033[36mProject:\033[0m {ProjName or '\033[31mUnknown (no ppm.toml)\033[0m'}"
    )
    if ProjVer:
        print(f"\033[36mVersion:\033[0m {ProjVer}")
    if MainFile:
        MainExists = Path(MainFile).is_file()
        Marker = "" if MainExists else " \033[31m(missing)\033[0m"
        print(f"\033[36mMain file:\033[0m {MainFile}{Marker}")

    VenvExists = Path(".venv").is_dir()
    print(
        f"\033[36mVirtual env:\033[0m {'present' if VenvExists else '\033[31mnot built\033[0m'}"
    )

    Handler = DependsHandler()
    packages = Handler._read_lockfile()
    installed = [p for p in packages if p.get("version") != "carted"]
    carted = [p for p in packages if p.get("version") == "carted"]
    print(
        f"\033[36mDependencies:\033[0m {len(installed)} installed, {len(carted)} carted"
    )


def DoctorCommand(fix: bool = False):
    """Runs a fuller consistency check across ppm.toml, ppm.lock, and the venv:
    catches drift between what's locked and what's actually installed, a
    missing/misconfigured venv, an unreachable main file, and orphaned carts.
    With fix=True, auto-remediates whatever it can instead of only reporting."""
    Issues = 0
    Warnings = 0
    Fixed = 0

    def ok(msg):
        print(f"\033[36m[ok]\033[0m {msg}")

    def warn(msg, remedy=None):
        nonlocal Warnings, Fixed
        if fix and remedy is not None:
            remedy()
            Fixed += 1
            print(f"\033[33m[fixed]\033[0m {msg}")
        else:
            Warnings += 1
            print(f"\033[33m[warn]\033[0m {msg}")

    def bad(msg, remedy=None):
        nonlocal Issues, Fixed
        if fix and remedy is not None:
            remedy()
            Fixed += 1
            print(f"\033[33m[fixed]\033[0m {msg}")
        else:
            Issues += 1
            print(f"\033[31m[fail]\033[0m {msg}")

    TomlPath = Path("ppm.toml")
    if not TomlPath.is_file():
        bad("No ppm.toml found in the current directory.")
    else:
        ok("ppm.toml present.")
        MainFile = _GetMainFileFromTOML()
        if MainFile is None:
            warn("ppm.toml has no main_file entry.")
        elif not Path(MainFile).is_file():

            def _fix_main_file(mf=MainFile):
                Path(mf).parent.mkdir(parents=True, exist_ok=True)
                Path(mf).write_text('print("Hello, world!")\n', encoding="utf-8")

            bad(
                f"main_file '{MainFile}' listed in ppm.toml does not exist.",
                remedy=_fix_main_file,
            )
        else:
            ok(f"main_file '{MainFile}' exists.")

    VenvDir = Path(".venv")
    BinDir = "Scripts" if platform == "win32" else "bin"
    VenvOk = VenvDir.is_dir() and (VenvDir / BinDir / f"python{EXE}").exists()
    if not VenvDir.is_dir():
        warn(
            "No .venv directory found; run 'ppm build-venv'.",
            remedy=lambda: build_venv(color=True, shush=True),
        )
        VenvOk = True
    elif not (VenvDir / BinDir / f"python{EXE}").exists():

        def _fix_venv():
            delete_venv(color=False, delete_ppm_paths=True)
            build_venv(color=True, shush=True)

        bad(
            f".venv exists but has no python{EXE} under {BinDir}/; venv may be corrupt.",
            remedy=_fix_venv,
        )
        VenvOk = True
    else:
        ok(".venv is present and has a usable python executable.")

    if not Path(".ppm_paths").is_file():
        warn(
            "No .ppm_paths file found; venv path resolution will fall back to defaults.",
            remedy=lambda: build_venv(color=True, shush=True) if VenvOk else None,
        )
    else:
        ok(".ppm_paths present.")

    Handler = DependsHandler()
    packages = Handler._read_lockfile()
    installed = [p for p in packages if p.get("version") != "carted"]
    carted = [p for p in packages if p.get("version") == "carted"]

    if not Path("ppm.lock").is_file():
        warn("No ppm.lock found; no dependencies are tracked yet.")
    else:
        ok(f"ppm.lock present ({len(installed)} installed, {len(carted)} carted).")

        # Drift check: is everything the lock thinks is installed actually
        # present in the venv according to pip?
        if VenvDir.is_dir():
            PipShow = run(
                [Handler._get_pip_path(), "list", "--format=freeze"],
                capture_output=True,
                text=True,
            )
            if PipShow.returncode == 0:
                venv_names = {
                    line.split("==")[0].lower()
                    for line in PipShow.stdout.splitlines()
                    if "==" in line
                }
                drifted = [p for p in installed if p["name"].lower() not in venv_names]
                for p in drifted:

                    def _fix_drift(pkg=p):
                        DepHandler = DependsHandler([pkg.get("spec", pkg["name"])])
                        DepHandler.InstallDepends()

                    bad(
                        f"'{p['name']}' is locked as installed but missing from the venv (drift).",
                        remedy=_fix_drift,
                    )
                if not drifted and installed:
                    ok("Lockfile and venv are in sync for installed packages.")
            else:
                warn(
                    "Could not query the venv's installed packages to check for drift."
                )

        for p in carted:
            if p.get("spec") is None:
                warn(f"Carted package '{p['name']}' has no preserved version spec.")

    if fix:
        print(
            f"\033[36mDoctor --fix finished:\033[0m {Fixed} issue(s) fixed, {Issues} unfixable, {Warnings} warning(s) left."
        )
    elif Issues == 0 and Warnings == 0:
        print("\033[36mAll checks passed!\033[0m")
    else:
        print(
            f"\033[36mDoctor finished:\033[0m {Issues} issue(s), {Warnings} warning(s). Run with --fix to auto-remediate."
        )


def ScanTreeCommand(root: str = ".", include_all: bool = False):
    """Recursively scans the given directory (default: cwd) and prints a tree
    of every .py file found, skipping noise directories (.venv, __pycache__,
    .git, .ruff_cache) unless include_all is set."""
    SkipDirs = (
        set()
        if include_all
        else {".venv", "__pycache__", ".git", ".ruff_cache", "node_modules"}
    )
    RootPath = Path(root).resolve()

    if not RootPath.is_dir():
        print(f"\033[31m'{root}' is not a directory.\033[0m")
        return

    def build(dir_path: Path):
        """Returns (subdirs_with_content, py_files) for a directory, recursing
        only into subdirectories that themselves contain (or lead to) .py files."""
        entries = sorted(
            dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
        )
        py_files = [p for p in entries if p.is_file() and p.suffix == ".py"]
        subdirs = []
        for p in entries:
            if p.is_dir() and p.name not in SkipDirs:
                child_subdirs, child_files = build(p)
                if child_files or child_subdirs:
                    subdirs.append((p, child_subdirs, child_files))
        return subdirs, py_files

    subdirs, py_files = build(RootPath)

    if not py_files and not subdirs:
        print(f"\033[33mNo Python files found under '{RootPath}'.\033[0m")
        return

    print(f"\033[36m{RootPath.name or RootPath}/\033[0m")
    TotalFiles = 0

    def render(subdirs, py_files, prefix=""):
        nonlocal TotalFiles
        items = subdirs + [(f, [], []) for f in py_files]
        for idx, (entry, child_subdirs, child_files) in enumerate(items):
            is_last = idx == len(items) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")
            if entry.is_dir():
                print(f"{prefix}{connector}\033[33m{entry.name}/\033[0m")
                render(child_subdirs, child_files, child_prefix)
            else:
                TotalFiles += 1
                print(f"{prefix}{connector}{entry.name}")

    render(subdirs, py_files)
    print(f"\033[36m{TotalFiles} Python file(s) found.\033[0m")


def CloneCommand(url: str, dest: str = None, branch: str = None):
    """Clones a remote git repo (no system git required) into `dest` (or a
    directory derived from the repo name), then, if the cloned project has a
    ppm.toml/ppm.lock, builds a venv and installs the locked dependencies."""
    if dest is None:
        # Derive a directory name from the last path segment of the URL.
        cleaned = url.rstrip("/")
        if cleaned.endswith(".git"):
            cleaned = cleaned[:-4]
        dest = cleaned.split("/")[-1]

    DestPath = Path(dest)
    if DestPath.exists() and any(DestPath.iterdir()):
        print(f"{RED}Destination '{dest}' already exists and is not empty.{RST}")
        e(1)

    print(f"{YLW}Cloning into '{dest}'...{RST}")
    try:
        Handler = CloneRepoHandler(url, dest, branch=branch)
        sha = Handler.clone()
    except CloneError as err:
        print(f"{RED}Clone failed: {err}{RST}")
        e(1)
    print(f"{CYN}Cloned repo at commit {sha[:10]}!{RST}")

    TomlPath = DestPath / "ppm.toml"
    LockPath = DestPath / "ppm.lock"
    if not TomlPath.is_file():
        print(f"{YLW}No ppm.toml found in cloned repo; skipping dependency setup.{RST}")
        return

    print(
        f"{YLW}Detected ppm.toml, building venv and installing locked dependencies...{RST}"
    )
    Cwd = Path.cwd()
    try:
        chdir(DestPath)
        build_venv(color=True, shush=True)
        if LockPath.is_file():
            DepHandler = DependsHandler()
            packages = DepHandler._read_lockfile()
            to_install = [p["name"] for p in packages if p.get("version") != "carted"]
            if to_install:
                DepHandler.depends = to_install
                DepHandler.InstallDepends()
            else:
                print(
                    f"{YLW}ppm.lock has no installed (non-carted) packages to set up.{RST}"
                )
        else:
            print(f"{YLW}No ppm.lock found; venv built but no packages installed.{RST}")
    finally:
        chdir(Cwd)
    print(f"{CYN}Project ready in '{dest}'!{RST}")


def InstallCommand(Depends: list, dry_run: bool = False):
    """Installs the given dependencies to the project."""
    Handler = DependsHandler(Depends)
    Handler.InstallDepends(dry_run=dry_run)


def UninstallCommand(Depends: list, dry_run: bool = False):
    """Uninstalls the given dependencies from the project."""
    Handler = DependsHandler()
    Handler.DeleteDepends(Depends, dry_run=dry_run)


def BuildVenvCommand():
    """Builds the virtual environment."""
    build_venv(color=True)


def RemoveVenvCommand():
    """Removes the virtual environment."""
    delete_venv(color=True)


def CheckCommand(File: str, fix=False):
    """Checks the project using ruff."""
    RuffCheck(File, fix=fix)


global YLW, RED, CYN, RST
YLW = "\033[33m"
RED = "\033[31m"
CYN = "\033[36m"
RST = "\033[0m"


def _Help():
    print(f"""
{YLW}ppm - Python Project Manager.{RST}
{YLW}Version: v1.3.1{RST}

{YLW}Commands are:{RST}

{CYN}new/n{RST} :: {YLW}Create a directory and initialize it{RST}
{CYN}init{RST} :: {YLW}Initialize a project{RST}
{CYN}deinit/di{RST} :: {YLW}Deinitialize a project{RST}
{CYN}clone/cl{RST} :: {YLW}Clone a git repo (no system git required) and set up its dependencies{RST}

{CYN}check/c{RST} :: {YLW}Check project using ruff.{RST}
{CYN}clear-rc/crc{RST} :: {YLW}Clear cache generated by ruff{RST}
{CYN}run/r{RST} :: {YLW}Run the project with the local venv python.{RST}
{CYN}build/b{RST} :: {YLW}Build a project with stable PyInstaller/Nuitka Backends.{RST}
{CYN}run-script/rs{RST} :: {YLW}Run a named command from ppm.toml's [scripts] table{RST}
{CYN}globalrun/gr{RST} :: {YLW}Use the system-global python to run the code.{RST}
{CYN}cart/ct{RST} :: {YLW}Cart a dependency to project{RST}
{CYN}decart/dct{RST} :: {YLW}Decart a dependency from project{RST}
{CYN}rm-venv/rvenv{RST} :: {YLW}Remove virtual environment {RST}{RED}(NOT RECOMMENDED){RST}
{CYN}build-venv/bvenv{RST} :: {YLW}Build virtual environment{RST}
{CYN}order/o{RST} :: {YLW}Order (or install) all carted packages.{RST}
{CYN}install/i{RST} :: {YLW}Install a dependency to project (supports --dry-run){RST}
{CYN}uninstall/u{RST} :: {YLW}Uninstall a dependency from project (supports --dry-run){RST}
{CYN}update/up{RST} :: {YLW}Update installed dependencies, all or specific (supports --dry-run){RST}
{CYN}list/l{RST} :: {YLW}List installed and carted dependencies{RST}
{CYN}status/s{RST} :: {YLW}Show project overview (venv, main file, dependency counts){RST}
{CYN}doctor/doc{RST} :: {YLW}Run a full consistency check across venv, toml, and lockfile (supports --fix){RST}
{CYN}scan-tree/st{RST} :: {YLW}Recursively print a tree of all Python files in a directory{RST}
{CYN}help/h{RST} :: {YLW}Print help and exit{RST}
{CYN}version/v{RST} :: {YLW}Print version and exit{RST}
""")


def _GetArgValue(Args: list, Flag: str) -> Optional[str]:
    """Helper to fetch the value following a flag in the CLI args, if present."""
    if Flag in Args:
        Idx = Args.index(Flag) + 1
        if Idx < len(Args):
            return Args[Idx]
    return None


def CLI():
    if len(argv) < 2:
        print(f"{RED}No arguments supplied! Use 'help' or 'h' for usage{RST}.")
        raise SystemExit
    Arg = argv[1]
    Args = argv[1:]
    if Args[0] == "init":
        projname = _GetArgValue(Args, "--projname")
        projver = _GetArgValue(Args, "--projver")
        mainfile = _GetArgValue(Args, "--main-file")
        yes = "--yes" in Args or "-y" in Args

        Just = [projname, projver, mainfile]
        Filtered = list(filter(None, Just))
        if not Filtered and not yes:
            InitProject()
        else:
            InitProject(projname, projver, mainfile, Yes=yes)
        e(0)
    if Args[0] == "new" or Args[0] == "n":
        dirname = _GetArgValue(Args, "--dirname")
        projname = _GetArgValue(Args, "--projname")
        projver = _GetArgValue(Args, "--projver")
        mainfile = _GetArgValue(Args, "--main-file")
        yes = "--yes" in Args or "-y" in Args
        NewProject(dirname, projname, projver, mainfile, Yes=yes)
        e(0)
    if Args[0] == "clone" or Args[0] == "cl":
        Positional = [a for a in Args[1:] if not a.startswith("--")]
        url = Positional[0] if Positional else _GetArgValue(Args, "--url")
        dest = Positional[1] if len(Positional) > 1 else _GetArgValue(Args, "--dir")
        branch = _GetArgValue(Args, "--branch")
        if url is None:
            print(f"{RED}No repository supplied! Use 'clone <url> [dest]'{RST}.")
            e(1)
        CloneCommand(url, dest, branch)
        e(0)
    match Arg:
        case "help" | "h":
            _Help()
            e(0)
        case "version" | "v":
            print(f"{CYN}PPM - Python Project Manager, v1.0.0{RST}")
            e(0)
        case "deinit" | "di":
            DeInitProject()
            e(0)
        case "check" | "c":
            File = _GetArgValue(Args, "--file") or (Args[1] if len(Args) > 1 else None)
            Fix = "--fix" in Args
            if File is None:
                print(
                    f"{RED}No file supplied! Use 'check <file>' or 'check --file <file>'{RST}."
                )
                e(1)
            CheckCommand(File, fix=Fix)
            e(0)
        case "clear-rc" | "crc":
            ClearRuffCache()
            e(0)
        case "run" | "r":
            MainFile = (
                _GetArgValue(Args, "--main-file")
                or (Args[1] if len(Args) > 1 else None)
                or _GetMainFileFromTOML()
            )
            if MainFile is None:
                MainFile = str(
                    input(
                        f"{YLW}Project main file (Full PATH from current directory): {RST}"
                    )
                )
            RunProject(MainFile, use_global=False)
            e(0)
        case "globalrun" | "gr":
            MainFile = (
                _GetArgValue(Args, "--main-file")
                or (Args[1] if len(Args) > 1 else None)
                or _GetMainFileFromTOML()
            )
            if MainFile is None:
                MainFile = str(
                    input(
                        f"{YLW}Project main file (Full PATH from current directory): {RST}"
                    )
                )
            RunProject(MainFile, use_global=True)
            e(0)
        case "run-script" | "rs":
            if len(Args) < 2:
                scripts = _GetScriptsFromTOML()
                available = ", ".join(scripts) if scripts else "(none defined)"
                print(
                    f"{RED}No script name supplied! Use 'run-script <name>'. Available: {available}{RST}"
                )
                e(1)
            Ok = RunScriptCommand(Args[1])
            e(0 if Ok else 1)
        case "cart" | "ct":
            Depends = Args[1:]
            if not Depends:
                print(f"{RED}No dependencies supplied! Use 'cart <pkg> [pkg...]'{RST}.")
                e(1)
            CartCommand(Depends)
            e(0)
        case "decart" | "dct":
            Depends = Args[1:]
            if not Depends:
                print(
                    f"{RED}No dependencies supplied! Use 'decart <pkg> [pkg...]'{RST}."
                )
                e(1)
            DecartCommand(Depends)
            e(0)
        case "rm-venv" | "rvenv":
            RemoveVenvCommand()
            e(0)
        case "build-venv" | "bvenv":
            BuildVenvCommand()
            e(0)
        case "order" | "o":
            OrderCommand()
            e(0)
        case "install" | "i":
            DryRun = "--dry-run" in Args
            Depends = [a for a in Args[1:] if a != "--dry-run"]
            if not Depends:
                print(
                    f"{RED}No dependencies supplied! Use 'install <pkg> [pkg...] [--dry-run]'{RST}."
                )
                e(1)
            InstallCommand(Depends, dry_run=DryRun)
            e(0)
        case "uninstall" | "u":
            DryRun = "--dry-run" in Args
            Depends = [a for a in Args[1:] if a != "--dry-run"]
            if not Depends:
                print(
                    f"{RED}No dependencies supplied! Use 'uninstall <pkg> [pkg...] [--dry-run]'{RST}."
                )
                e(1)
            UninstallCommand(Depends, dry_run=DryRun)
            e(0)
        case "list" | "l":
            ListCommand()
            e(0)
        case "status" | "s":
            StatusCommand()
            e(0)
        case "doctor" | "doc":
            DoctorCommand(fix="--fix" in Args)
            e(0)
        case "scan-tree" | "st":
            IncludeAll = "--all" in Args
            Positional = [a for a in Args[1:] if not a.startswith("--")]
            RootArg = (
                Positional[0] if Positional else (_GetArgValue(Args, "--dir") or ".")
            )
            ScanTreeCommand(RootArg, include_all=IncludeAll)
            e(0)
        case "build" | "b":
            Positional = _GetPositionalArgs(Args, {"--main-file", "--backend"})
            MainFileArg = (
                Positional[0] if Positional else _GetArgValue(Args, "--main-file")
            )
            BackendArg = _GetArgValue(Args, "--backend") or "pyinstaller"
            if BackendArg not in ("pyinstaller", "nuitka"):
                print(
                    f"{RED}Unknown backend '{BackendArg}'. Use 'pyinstaller' or 'nuitka'.{RST}"
                )
                e(1)
            NoInstall = "--no-install" in Args
            KeepJunk = "--keep-junk" in Args
            UseGlobal = "--global" in Args
            Ok = BuildCommand(
                MainFileArg,
                backend=BackendArg,
                install_if_missing=not NoInstall,
                keep_junk=KeepJunk,
                use_global=UseGlobal,
            )
            e(0 if Ok else 1)

        case "update" | "up":
            DryRun = "--dry-run" in Args
            Depends = [a for a in Args[1:] if a != "--dry-run"]
            UpdateCommand(Depends if Depends else None, dry_run=DryRun)
            e(0)
        case _:
            print(f"{RED}Unknown command: {Arg}. Use 'help' or 'h' for usage{RST}.")
            e(1)


if __name__ == "__main__":
    try:
        CLI()
    except KeyboardInterrupt:
        print("\n\033[33m^C: Control-C Exit!\033[0m")
