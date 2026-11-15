#!/usr/bin/env python3
"""Build the Raman Simulation Studio and assemble deploy/ (Windows, macOS, Linux).

    python build.py              build everything and assemble deploy/
    python build.py --test       the same, then run every test suite (10 to 20 minutes)
    python build.py --no-window  leave out the controller window (laser_test); the Studio needs only
                                 the headless runner

Needs Python 3.11 or newer (run this script with the Python you want the data layer to use), Qt 6
with the Qt Charts module, CMake and Ninja (both come with Qt's online installer), the .NET 9 SDK,
and on Windows Visual Studio 2022 or its Build Tools with the "Desktop development with C++"
workload. Node.js 18 or newer is optional: it runs the Studio page's own tests.

Everything this script writes stays inside this folder: .venv/ (the data layer's packages, from
PyPI), build/ and deploy/. Data a run left in deploy/ (scan_sessions/, dark_measurements/,
data_catalog/) is kept when the script runs again.
"""

from __future__ import annotations

import argparse
import glob
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEPLOY = ROOT / "deploy"
BUILD = ROOT / "build"
VENV = ROOT / ".venv"
WINDOWS = os.name == "nt"
MACOS = sys.platform == "darwin"
EXE = ".exe" if WINDOWS else ""


class BuildError(Exception):
    pass


def say(text: str) -> None:
    print(text, flush=True)


def run(command, cwd=None, env=None, quiet=False) -> None:
    """Run a command; on failure show its output (when quiet) and stop the build."""
    shown = " ".join(str(part) for part in command)
    result = subprocess.run([str(part) for part in command], cwd=cwd, env=env,
                            stdout=subprocess.PIPE if quiet else None, stderr=subprocess.STDOUT if quiet else None,
                            text=True, errors="replace")
    if result.returncode != 0:
        if quiet and result.stdout:
            print(result.stdout[-6000:])
        raise BuildError("this command failed (exit %d): %s" % (result.returncode, shown))


# ---------------------------------------------------------------------- finding the tools


def qt_kit(explicit: str | None) -> Path:
    """The Qt 6 kit folder (the one with bin/ and lib/cmake/Qt6/)."""
    named = [explicit, os.environ.get("QT_DIR"), os.environ.get("QT_ROOT_DIR")]
    if os.environ.get("Qt6_DIR"):
        named.append(str(Path(os.environ["Qt6_DIR"]).parents[2]))   # <kit>/lib/cmake/Qt6
    for candidate in filter(None, named):
        if (Path(candidate) / "lib" / "cmake" / "Qt6").is_dir():
            return Path(candidate).resolve()
        if explicit and candidate == explicit:
            raise BuildError("%s is not a Qt 6 kit folder (it has no lib/cmake/Qt6). Pass the folder that "
                             "holds bin/ and lib/, for example C:\\Qt\\6.8.3\\msvc2022_64 or ~/Qt/6.8.3/macos." % candidate)
    roots = [Path.home() / "Qt", Path("C:/Qt"), Path("/opt/Qt")]
    if WINDOWS:
        arm = platform.machine().upper() == "ARM64"
        kits = (["msvc2022_arm64"] if arm else []) + ["msvc2022_64", "msvc2019_64", "mingw_64", "llvm-mingw_64"]
    elif MACOS:
        kits = ["macos", "clang_64"]
    else:
        kits = ["gcc_64", "linux_gcc_64"]
    versions = []
    for root in roots:
        for folder in root.glob("6.*"):
            if re.fullmatch(r"6\.\d+(\.\d+)?", folder.name):
                versions.append((tuple(int(x) for x in folder.name.split(".")), folder))
    for _version, folder in sorted(versions, reverse=True):
        for kit in kits:
            if (folder / kit / "lib" / "cmake" / "Qt6").is_dir():
                return folder / kit
    raise BuildError("No Qt 6 kit found. Install Qt 6 with Qt Charts (Qt online installer), or pass "
                     "--qt <kit folder>, or set QT_DIR.")


def qt_tools(kit: Path) -> Path:
    """Qt's Tools folder (CMake, Ninja, MinGW) next to the versions, when there is one."""
    return kit.parent.parent / "Tools"


def find_program(name: str, *candidates) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for pattern in candidates:
        for path in sorted(glob.glob(str(pattern)), reverse=True):
            if os.path.isfile(path):
                return path
    return None


def windows_compiler_environment(kit: Path) -> dict:
    """The environment of a Visual Studio developer prompt (vcvars), unless cl.exe is already on PATH."""
    environment = dict(os.environ)
    if "mingw" in kit.name:
        for tools_bin in sorted(qt_tools(kit).glob("mingw*/bin"), reverse=True):
            environment["PATH"] = str(tools_bin) + os.pathsep + environment["PATH"]
            break
        return environment
    if shutil.which("cl"):
        return environment
    vswhere = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.is_file():
        raise BuildError("Visual Studio was not found. Install Visual Studio 2022 (or its Build Tools) with the "
                         "\"Desktop development with C++\" workload, or run this script from a Developer Command Prompt.")
    install = subprocess.run([str(vswhere), "-latest", "-products", "*", "-requires",
                              "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
                             capture_output=True, text=True).stdout.strip().splitlines()
    if not install:
        raise BuildError("Visual Studio has no C++ compiler. Add the \"Desktop development with C++\" workload in the "
                         "Visual Studio Installer.")
    script = Path(install[0]) / "VC" / "Auxiliary" / "Build" / ("vcvarsarm64.bat" if "arm64" in kit.name else "vcvars64.bat")
    output = subprocess.run('cmd /d /s /c ""%s" >nul 2>&1 && set"' % script, capture_output=True, text=True,
                            errors="replace").stdout
    for line in output.splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            environment[key] = value
    if not shutil.which("cl", path=environment.get("PATH")):
        raise BuildError("The Visual Studio C++ compiler could not be set up from %s" % script)
    return environment


def dotnet_program() -> str:
    found = find_program("dotnet", Path.home() / ".dotnet" / ("dotnet" + EXE),
                         Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "dotnet" / "dotnet.exe",
                         "/usr/local/share/dotnet/dotnet")
    if not found:
        raise BuildError("The .NET SDK was not found. Install the .NET 9 SDK from https://dotnet.microsoft.com/download")
    return found


# ---------------------------------------------------------------------- the pieces


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if WINDOWS else "bin/python")


def make_venv() -> Path:
    if sys.version_info < (3, 11):
        raise BuildError("Python 3.11 or newer is needed (this is %s). Run build.py with a newer Python."
                         % platform.python_version())
    python = venv_python()
    if not python.is_file():
        say("   creating .venv with %s" % sys.executable)
        run([sys.executable, "-m", "venv", VENV])
    run([python, "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "-r",
         ROOT / "data_layer" / "requirements.txt"])
    return python


def fresh_if_moved(build_dir: Path) -> None:
    """A CMake build folder cannot be reused after the checkout moved: discard its cache."""
    cache = build_dir / "CMakeCache.txt"
    if cache.is_file() and ("CMAKE_CACHEFILE_DIR:INTERNAL=%s" % build_dir.as_posix()) not in cache.read_text(errors="replace"):
        say("   (the checkout moved: discarding the stale CMake cache in %s)" % build_dir)
        cache.unlink()
        shutil.rmtree(build_dir / "CMakeFiles", ignore_errors=True)


class Toolchain:
    def __init__(self, kit: Path):
        self.kit = kit
        tools = qt_tools(kit)
        self.environment = windows_compiler_environment(kit) if WINDOWS else dict(os.environ)
        path = self.environment.get("PATH")
        self.cmake = (shutil.which("cmake", path=path)
                      or find_program("cmake", tools / "CMake_64" / "bin" / "cmake.exe", tools / "CMake" / "bin" / "cmake",
                                      tools / "CMake" / "CMake.app" / "Contents" / "bin" / "cmake"))
        self.ninja = shutil.which("ninja", path=path) or find_program("ninja", tools / "Ninja" / ("ninja" + EXE))
        if not self.cmake:
            raise BuildError("CMake was not found. It comes with Qt's online installer (Developer and Designer Tools) "
                             "and with Visual Studio; or install it from https://cmake.org")
        if not self.ninja:
            raise BuildError("Ninja was not found. It comes with Qt's online installer (Developer and Designer Tools) "
                             "and with Visual Studio; or install it from https://ninja-build.org")

    def build(self, name: str, source: Path, *definitions: str) -> Path:
        build_dir = BUILD / name
        fresh_if_moved(build_dir)
        run([self.cmake, "-S", source, "-B", build_dir, "-G", "Ninja", "-DCMAKE_MAKE_PROGRAM=%s" % self.ninja,
             "-DCMAKE_PREFIX_PATH=%s" % self.kit, "-DCMAKE_BUILD_TYPE=Release", *definitions],
            env=self.environment, quiet=True)
        run([self.cmake, "--build", build_dir], env=self.environment, quiet=True)
        return build_dir

    def runtime_environment(self) -> dict:
        """For the programs built here when they run from their build folders: Windows finds the Qt
        libraries on PATH (macOS and Linux have them in the programs' rpath)."""
        environment = dict(os.environ)
        if WINDOWS:
            environment["PATH"] = str(self.kit / "bin") + os.pathsep + environment.get("PATH", "")
        return environment

    def deploy_qt(self, program: Path) -> None:
        """Windows: put the Qt libraries and plugins next to a program in deploy/."""
        if not WINDOWS:
            return
        windeployqt = self.kit / "bin" / "windeployqt.exe"
        if not windeployqt.is_file():
            windeployqt = self.kit / "bin" / "windeployqt6.exe"
        run([windeployqt, "--release", "--no-translations", "--no-compiler-runtime", "--dir", DEPLOY, program],
            env=self.environment, quiet=True)
        # The runner draws its window off screen (QT_QPA_PLATFORM=offscreen), a plugin windeployqt leaves out.
        offscreen = self.kit / "plugins" / "platforms" / "qoffscreen.dll"
        if offscreen.is_file():
            (DEPLOY / "platforms").mkdir(exist_ok=True)
            shutil.copy2(offscreen, DEPLOY / "platforms" / offscreen.name)


def copy_tree(source: Path, target: Path) -> None:
    """Replace target with a copy of source (without caches)."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


def write_launcher(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\r\n" if path.suffix == ".cmd" else "\n")
    if not WINDOWS:
        path.chmod(0o755)


STUDIO_CMD = r"""@echo off
rem Start the Simulation Studio for this folder: a local web page (its address is printed first)
rem that shows the scans and the data pipeline of this folder and starts simulated runs.
rem Ctrl+C ends it. Options: --port N, --no-open (do not open the browser), --idle-exit SECONDS.
setlocal
cd /d "%~dp0"
set "PY=%RAMAN_DATAFED_PYTHON%"
if not defined PY set /p PY=<datafed_python.txt
if not exist "%PY%" (
  echo No data-layer interpreter: set RAMAN_DATAFED_PYTHON or name one in datafed_python.txt 1>&2
  exit /b 1
)
set "PYTHONPATH=%CD%\data_layer;%PYTHONPATH%"
set PYTHONUTF8=1
"%PY%" -m raman_datafed --home "%CD%" studio %*
"""

STUDIO_SH = """#!/bin/bash
# Start the Simulation Studio for this folder: a local web page (its address is printed first) that
# shows the scans and the data pipeline of this folder and starts simulated runs (raman_sim_runner).
# Ctrl-C ends it. Options: --port N, --no-open (do not open the browser), --idle-exit SECONDS.
cd "$(dirname "$0")"
PY="${RAMAN_DATAFED_PYTHON:-$(head -n 1 datafed_python.txt 2>/dev/null)}"
command -v "$PY" > /dev/null 2>&1 || { echo "No data-layer interpreter: set RAMAN_DATAFED_PYTHON or name one in datafed_python.txt" >&2; exit 1; }
PYTHONPATH="$PWD/data_layer${PYTHONPATH:+:$PYTHONPATH}" exec "$PY" -m raman_datafed --home "$PWD" studio "$@"
"""

WINDOW_CMD = r"""@echo off
rem The controller window with both helper programs simulated: no instrument is used.
cd /d "%~dp0"
set RAMAN_BACKEND_SIMULATE=1
set RAMAN_MOTOR_SIMULATE=1
start "" "%~dp0laser_test.exe"
"""

WINDOW_SH = """#!/bin/bash
# The controller window with both helper programs simulated: no instrument is used.
cd "$(dirname "$0")"
RAMAN_BACKEND_SIMULATE=1 RAMAN_MOTOR_SIMULATE=1 exec ./laser_test "$@"
"""


def assemble(tools: Toolchain, python: Path, dotnet: str, runner: Path, window: Path | None) -> None:
    DEPLOY.mkdir(exist_ok=True)
    for folder in ("scan_sessions", "dark_measurements"):
        (DEPLOY / folder).mkdir(exist_ok=True)
    # The two programs, with the Qt libraries next to them on Windows.
    for program in filter(None, (runner, window)):
        shutil.copy2(program, DEPLOY / program.name)
        tools.deploy_qt(DEPLOY / program.name)
    # The capture backend: the published .NET program (SampleApl.exe on Windows, a launcher elsewhere).
    backend = DEPLOY / "handshake_v2" / "backend"
    copy_tree(ROOT / "native" / "backend" / "SampleApl" / "bin" / "publish", backend)
    if not WINDOWS:
        launcher = (ROOT / "native" / "backend" / "SampleApl" / "SampleApl").read_text(encoding="utf-8")
        write_launcher(backend / "SampleApl", launcher.replace("@DOTNET@", dotnet))
    # The motor program (Python): the controller runs raman_autofocus.py itself on Windows.
    motor = DEPLOY / "handshake_v2" / "motor"
    if motor.exists():
        shutil.rmtree(motor)
    motor.mkdir(parents=True)
    for source in list((ROOT / "native" / "motor").glob("*.py")) + [ROOT / "native" / "motor" / "motor_config.json"]:
        shutil.copy2(source, motor / source.name)
    if not WINDOWS:
        launcher = (ROOT / "native" / "motor" / "RamanAutofocus").read_text(encoding="utf-8")
        write_launcher(motor / "RamanAutofocus", launcher.replace("@PYTHON@", str(python)))
    # The data layer, the classifier model, the virtual sample and the Studio page.
    (DEPLOY / "data_layer").mkdir(exist_ok=True)
    copy_tree(ROOT / "data_layer" / "raman_datafed", DEPLOY / "data_layer" / "raman_datafed")
    copy_tree(ROOT / "data_layer" / "arc", DEPLOY / "data_layer" / "arc")
    shutil.copy2(ROOT / "data_layer" / "requirements.txt", DEPLOY / "data_layer" / "requirements.txt")
    for folder in ("models", "virtual_sample", "studio"):
        copy_tree(ROOT / folder, DEPLOY / folder)
    for name in ("raman_python.txt", "datafed_python.txt"):
        (DEPLOY / name).write_text(str(python) + "\n", encoding="utf-8")
    if WINDOWS:
        write_launcher(DEPLOY / "studio.cmd", STUDIO_CMD)
        if window:
            write_launcher(DEPLOY / "run_simulated.cmd", WINDOW_CMD)
    else:
        write_launcher(DEPLOY / "studio.sh", STUDIO_SH)
        if window:
            write_launcher(DEPLOY / "run_simulated.sh", WINDOW_SH)


# ---------------------------------------------------------------------- the tests


class Suites:
    def __init__(self, tools: Toolchain, python: Path):
        self.tools = tools
        self.python = python
        self.logs = BUILD / "test-logs"
        shutil.rmtree(self.logs, ignore_errors=True)
        self.logs.mkdir(parents=True)
        self.failed = []
        # Every helper program a suite starts runs its simulator; Python reads and writes UTF-8.
        self.environment = tools.runtime_environment()
        self.environment.update(RAMAN_BACKEND_SIMULATE="1", RAMAN_MOTOR_SIMULATE="1", PYTHONDONTWRITEBYTECODE="1",
                                PYTHONUTF8="1", DOTNET_CLI_TELEMETRY_OPTOUT="1")

    def suite(self, name: str, command, cwd: Path = ROOT, **extra) -> None:
        started = time.monotonic()
        log = self.logs / (name + ".log")
        environment = dict(self.environment, **extra)
        with open(log, "w", encoding="utf-8", errors="replace") as handle:
            code = subprocess.run([str(part) for part in command], cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
                                  stdout=handle, stderr=subprocess.STDOUT).returncode
        text = log.read_text(encoding="utf-8", errors="replace")
        seconds = time.monotonic() - started
        if code == 0:
            ran = re.findall(r"^Ran \d+ tests? in .*$", text, re.M)
            summary = ran[-1] if ran else "%d PASS lines" % len(re.findall(r"^PASS", text, re.M))
            say("   PASS  %s (%.0f s): %s" % (name, seconds, summary))
        else:
            say("   FAIL  %s (%.0f s), end of %s:" % (name, seconds, log))
            for line in text.splitlines()[-15:]:
                say("         " + line)
            self.failed.append(name)

    def run_all(self, deploy_has_window: bool) -> None:
        python = self.python
        self.suite("data_layer", [python, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT / "data_layer")
        self.suite("studio_embedded", [python, ROOT / "studio" / "embed_assets.py", "--check"])
        node = shutil.which("node")
        if node:
            self.suite("studio_engine", [node, ROOT / "studio" / "test_engine.mjs"])
            self.suite("studio_page", [node, ROOT / "studio" / "test_page.mjs"])
        else:
            say("   SKIP  studio_engine, studio_page: Node.js is not installed")
        self.suite("motor", [python, "-m", "unittest", "discover", "-s", ROOT / "native" / "motor" / "tests", "-v"])
        self.suite("backend", [python, "-m", "unittest", "-v", "tests.test_backend_protocol", "tests.test_backend_watchdog",
                               "tests.test_backend_virtual_sample", "tests.test_virtual_sample_model"], cwd=ROOT / "native" / "backend")
        self.suite("sim_runner", [python, "-m", "unittest", "-v", "test_sim_runner"], cwd=ROOT / "native" / "sim_runner",
                   RAMAN_DEPLOY_DIR=str(DEPLOY))
        self.suite("studio_live", [python, "-m", "unittest", "-v", "test_studio_live"], cwd=ROOT / "native" / "sim_runner",
                   RAMAN_DEPLOY_DIR=str(DEPLOY))
        tests = self.tools.build("controller-tests", ROOT / "laser_test" / "tests", "-DPython3_EXECUTABLE=%s" % python)
        self.suite("handshake_tests", [tests / ("handshake_tests" + EXE)], cwd=tests)
        self.suite("settings_tests", [tests / ("settings_tests" + EXE)], cwd=tests)
        self.suite("ui_tests", [tests / "ui_home" / ("ui_tests" + EXE)], cwd=tests / "ui_home")
        e2e = self.tools.build("e2e", ROOT / "native" / "e2e")
        copy_tree(DEPLOY / "handshake_v2", e2e / "handshake_v2")
        (e2e / "raman_python.txt").write_text(str(python) + "\n", encoding="utf-8")
        self.suite("e2e_simulated", [e2e / ("e2e_simulated_test" + EXE)], cwd=e2e)


# ---------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--test", action="store_true", help="run every test suite after the build")
    parser.add_argument("--no-window", action="store_true", help="do not build the controller window (laser_test)")
    parser.add_argument("--qt", metavar="KIT", help="Qt 6 kit folder, e.g. C:\\Qt\\6.8.3\\msvc2022_64 or ~/Qt/6.8.3/macos")
    args = parser.parse_args()
    started = time.monotonic()
    try:
        kit = qt_kit(os.path.expanduser(args.qt) if args.qt else None)
        if not (kit / "lib" / "cmake" / "Qt6Charts").is_dir():
            raise BuildError("The Qt kit %s has no Qt Charts. Add it with Qt's Maintenance Tool "
                             "(Qt > %s > Additional Libraries > Qt Charts)." % (kit, kit.parent.name))
        tools = Toolchain(kit)
        dotnet = dotnet_program()
        say("== settings: Qt %s | CMake %s | Ninja %s | .NET %s | Python %s" % (kit, tools.cmake, tools.ninja, dotnet, sys.executable))
        say("== 1/5 Python environment for the data layer (.venv) ==")
        python = make_venv()
        say("== 2/5 capture backend (.NET, simulator) ==")
        dotnet_environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
        run([dotnet, "publish", "-c", "Release", "-o", "bin/publish", "-nologo", "-v", "q"],
            cwd=ROOT / "native" / "backend" / "SampleApl", env=dotnet_environment, quiet=True)
        say("== 3/5 simulated runner (the controller without a window, for the Studio) ==")
        runner = tools.build("runner", ROOT / "native" / "sim_runner") / ("raman_sim_runner" + EXE)
        window = None
        if args.no_window:
            say("== 4/5 controller window: left out (--no-window) ==")
        else:
            say("== 4/5 controller window (laser_test) ==")
            window = tools.build("window", ROOT / "laser_test", "-DRAMAN_FLAT_LAYOUT=ON") / ("laser_test" + EXE)
        say("== 5/5 assemble %s ==" % DEPLOY)
        assemble(tools, python, dotnet, runner, window)
        say("   start the Studio with: %s" % (DEPLOY / ("studio.cmd" if WINDOWS else "studio.sh")))
        if not args.test:
            say("== done in %.0f s (add --test to run the test suites) ==" % (time.monotonic() - started))
            return 0
        say("== tests (logs in %s) ==" % (BUILD / "test-logs"))
        suites = Suites(tools, python)
        suites.run_all(window is not None)
        if suites.failed:
            say("!! %d suite(s) FAILED: %s" % (len(suites.failed), ", ".join(suites.failed)))
            return 1
        say("== every suite passed in %.0f s ==" % (time.monotonic() - started))
        return 0
    except BuildError as error:
        say("ERROR: %s" % error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
