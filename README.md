# Raman Simulation Studio

A web page that shows a portable Raman spectrometer at work, and a simulated instrument stack behind
it that runs on **Windows and macOS**. The instrument is a Hamamatsu C13560 Raman module on three
Thorlabs KDC101 motor stages, driven by a Qt controller; the Studio shows the stage moving over a
sample plate, each spectrum as it is captured, and the data pipeline that registers, classifies and
queues each spectrum for review (a local catalog, or DataFed with Globus and an ARC cluster job).

Nothing here talks to an instrument. Every spectrum is simulated, built from real measured spectra of
R6G, methylene blue and adenine on a virtual 25 mm × 25 mm plate.

There are two ways to use it:

| | What you need | What you get |
|---|---|---|
| **DEMO** | a web browser | Open `studio/index.html`. A re-enactment with example data, built into the page. Nothing to install. |
| **LIVE** | a one-time build (below) | The page served by a small local server. **Play** runs the real controller code (without its window) against the simulated spectrometer and stages; the data layer registers, classifies and queues what it captures. |

## Contents

1. [DEMO: open the page](#1-demo-open-the-page)
2. [LIVE on Windows](#2-live-on-windows)
3. [LIVE on macOS](#3-live-on-macos)
4. [Using the Studio](#4-using-the-studio)
5. [The controller window](#5-the-controller-window)
6. [Tests](#6-tests)
7. [What is in this repository](#7-what-is-in-this-repository)
8. [Troubleshooting](#8-troubleshooting)

## 1. DEMO: open the page

Download or clone this repository and double-click `studio/index.html`. It opens in your browser in
DEMO mode (the badge at the top says so). Press Play. Everything happens inside the page; its
classifier is a stand-in and the page says so.

## 2. LIVE on Windows

### What to install (once)

1. **Python 3.11 to 3.14** from <https://www.python.org/downloads/windows/> (the data layer's
   pinned numpy and scikit-learn have no builds for newer ones). In the installer, tick
   **Add python.exe to PATH**.
2. **Visual Studio Community** 2022 or newer (free) from
   <https://visualstudio.microsoft.com/vs/community/>, or just its Build Tools. In the Visual Studio
   Installer, tick the workload **Desktop development with C++**. This gives the C++ compiler, and CMake and Ninja with it.
3. **Qt 6** (6.10 or newer) with **Qt Charts**, from the Qt Online Installer
   (<https://www.qt.io/download-qt-installer-oss>; a free Qt account is needed). Install into the
   default folder `C:\Qt`. On the **Select Components** page:
   - open **Qt** › **Qt 6.10.x** (or newer) and tick **MSVC 2022 64-bit**;
   - in the same version, open **Additional Libraries** and tick **Qt Charts**.
4. **.NET 9 SDK** from <https://dotnet.microsoft.com/download/dotnet/9.0> (the x64 SDK installer).
5. Optional: **Git** (<https://git-scm.com/download/win>) to clone, and **Node.js** 18 or newer
   (<https://nodejs.org>) to run the page's own tests.

### Build (once, and again after you change code)

Open **PowerShell** or **Command Prompt** and run:

```powershell
git clone https://github.com/adharshjai/raman-simulation-studio.git
cd raman-simulation-studio
py build.py
```

(Without Git: download the ZIP from GitHub, unpack it, and run `py build.py` in that folder.)

`build.py` finds Qt in `C:\Qt` and sets up the Visual Studio compiler by itself; you do not need a
Developer Command Prompt. If Qt is somewhere else, name the kit folder:
`py build.py --qt D:\Qt\6.10.1\msvc2022_64`. The first build downloads the data layer's Python
packages (about 215 MB) into `.venv\`, and takes a few minutes. It ends with:

```
== 5/5 assemble ...\raman-simulation-studio\deploy ==
   start the Studio with: ...\raman-simulation-studio\deploy\studio.cmd
```

### Start the Studio

```powershell
deploy\studio.cmd
```

(In PowerShell from the repository folder: `.\deploy\studio.cmd`. Or double-click `studio.cmd` in
the `deploy` folder.) It prints its address, normally <http://127.0.0.1:8765/>, and opens the page in
your default browser, in LIVE mode. The server listens on this computer only. Press **Ctrl+C** in
its window to stop it (answer **Y** if Windows asks "Terminate batch job?").

Options: `deploy\studio.cmd --no-open` (do not open a browser), `--port 8800` (another port).

## 3. LIVE on macOS

### What to install (once)

1. **Python 3.11 to 3.14**: from <https://www.python.org/downloads/macos/>, Homebrew
   (`brew install python@3.13`) or Anaconda.
2. **Xcode Command Line Tools**: `xcode-select --install`.
3. **Qt 6** (6.10 or newer) with **Qt Charts**, from the Qt Online Installer, into the default folder
   `~/Qt`. On **Select Components**: **Qt** › **Qt 6.10.x** › tick **macOS** and, under
   **Additional Libraries**, **Qt Charts**; under **Build Tools** (or **Developer and Designer
   Tools**), tick **CMake** and **Ninja**.
4. **.NET 9 SDK** from <https://dotnet.microsoft.com/download/dotnet/9.0> (Arm64 installer on Apple
   silicon, x64 on Intel).

### Build and start

```bash
git clone https://github.com/adharshjai/raman-simulation-studio.git
cd raman-simulation-studio
python3 build.py
./deploy/studio.sh
```

`build.py` finds Qt in `~/Qt`; otherwise `python3 build.py --qt ~/Qt/6.10.1/macos`. The Studio
prints its address (normally <http://127.0.0.1:8765/>) and opens your browser. **Ctrl-C** stops it.

## 4. Using the Studio

The badge at the top says **DEMO** or **LIVE**. LIVE starts by itself when the page was served by
`studio.cmd` / `studio.sh`; the **Demo** button switches back.

- **Play** starts one simulated run of the controller: Laser ON, a dark spectrum, then a 1D scan
  (13 points), a Z scan followed by a 2D scan, or a single capture; then Laser OFF. Fill in Sample
  ID, Operator and Location first, and choose the scan type and the laser power. **Stop** ends the
  run the way the controller's Stop button does, and switches the simulated laser off.
- **Instrument** (first panel): a top view of the stage travel with the virtual sample, the planned
  path, the captured points and the probe; the stage height against the focus plane; the newest
  spectrum on a Raman-shift axis; and a ticker of what the controller is doing. Ground truth splits
  each point into the plate's material (left) and the classifier's prediction (right).
- **Data pipeline** (second panel): each square is one spectrum on its way from the laptop through
  the catalog (and, with DataFed, Globus) to the classifier and the reviewer. Select one to see its
  record and where its prediction came from. Here are **Sync now**, **Run classifier**, the
  **Offline** switch, and **Confirm / Reject / Relabel** for predictions that need review.
- **The bigger picture** (third panel): the loop of an automated experiment (plan, move and acquire,
  transfer, record, analyse, decide), and what it looks like **Without DataFed and Globus**.

By default the data layer uses a **local demo catalog** in `deploy/data_catalog/`: nothing leaves
the computer. DataFed mode needs your own DataFed and Globus accounts and is not set up by the
build; see `data_layer/PROTOCOL.md` and `data_layer/arc/README.md`. It has not been run against a
live DataFed server.

Every scan is kept in `deploy/scan_sessions/` (one folder per scan, one JSON file per spectrum) and
every dark spectrum in `deploy/dark_measurements/`. A rebuild keeps them.

## 5. The controller window

The Qt controller with its window, also running against the simulators:

- Windows: `deploy\run_simulated.cmd`
- macOS: `./deploy/run_simulated.sh`

Its **Open Simulation Studio** button starts the Studio for the same folder. A run started with the
Studio's Play does not start while the window is open (both take the same lock); the page says so.
The build leaves the window out with `--no-window`; the Studio does not need it.

## 6. Tests

```
py build.py --test        (Windows)
python3 build.py --test   (macOS)
```

builds everything, then runs every suite: the data layer, the Studio page (with Node.js), the
motor program, the capture backend and its safety stop, the controller's own test programs, the
headless runner, an end-to-end simulated scan, and the Studio in LIVE mode (Play, then Stop, through
the server). Each suite's output is in `build/test-logs/`. GitHub Actions runs the same command on
Windows and macOS for every push (`.github/workflows/build-and-test.yml`).

## 7. What is in this repository

```
build.py                 builds everything and assembles deploy/ (Windows, macOS, Linux)
studio/                  the Studio page (index.html, one self-contained file) and its tests
data_layer/              Python package raman_datafed: catalogs, ledger, classifier, review queue,
                         sync, the Studio server; PROTOCOL.md is the contract between all parts
laser_test/              the Qt controller (main.cpp) and its test programs
native/sim_runner/       raman_sim_runner: the controller without a window, always simulated,
                         started by the Studio's Play
native/backend/          the capture backend (.NET): the spectrometer simulator and its safety stop
native/motor/            the motor program (Python) with its KDC101 stage simulator
native/e2e/              an end-to-end test of the controller with both simulators
virtual_sample/          the simulated plate and the measured reference spectra it is built from
models/                  the PCA + SVM classifier the data layer runs
```

`build.py` makes `.venv/` (the data layer's Python packages), `build/` and `deploy/`, all ignored by
git. `deploy/` holds `raman_sim_runner` and `laser_test` (with the Qt libraries on Windows),
`handshake_v2/` (the two helper programs), the data layer, the model, the virtual sample, the page,
and the launchers.

**Simulation only.** The real capture backend runs Hamamatsu's `wrrusb2a.dll`, which is proprietary
and not part of this repository; the backend here contains the simulator only and refuses to start
unless the simulator is selected (`RAMAN_BACKEND_SIMULATE=1`, which the runner and
`run_simulated` set). The few plain data types the
simulator shares with that library are declared in `native/backend/SampleApl/VendorTypes.cs`.

## 8. Troubleshooting

- **"No Qt 6 kit found"**: pass the kit folder, the one that holds `bin` and `lib`:
  `py build.py --qt C:\Qt\6.10.1\msvc2022_64` (Windows) or `python3 build.py --qt ~/Qt/6.10.1/macos`.
- **"The Qt kit ... has no Qt Charts"**: open Qt's Maintenance Tool (in `C:\Qt` or `~/Qt`), choose
  **Add or remove components**, and tick **Additional Libraries › Qt Charts** for your Qt version.
- **"Visual Studio was not found" / "has no C++ compiler"** (Windows): install the **Desktop
  development with C++** workload in the Visual Studio Installer.
- **"The .NET SDK was not found"**: install the .NET 9 SDK, then open a new terminal.
- **`py` is not recognised** (Windows): use `python build.py`, or reinstall Python with
  **Add python.exe to PATH** ticked.
- **Port 8765 is in use**: the Studio takes the next free port up to 8784 and prints the one it
  uses. `--port N` starts the search elsewhere.
- **Play says the controller lock is held**: the controller window, or another run, is open in the
  same `deploy` folder. Close it first.
- **The page shows DEMO although the server runs**: open the address the server printed, not the
  file `studio/index.html`.
- **A build error after you moved the folder**: `build.py` starts the CMake builds afresh by itself;
  if anything else is stale, delete `build/` and run it again.
