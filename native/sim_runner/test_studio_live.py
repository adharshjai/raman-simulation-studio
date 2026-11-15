#!/usr/bin/env python3
"""The Simulation Studio in LIVE mode, end to end: the Studio server of the data layer, started as
studio.sh / studio.cmd start it, plays and stops simulated runs of the real raman_sim_runner with
the real helper programs (all simulated), in a copy of the deploy folder.

    python3 -m unittest native/sim_runner/test_studio_live.py

Env RAMAN_DEPLOY_DIR names the deploy folder to copy (default: deploy/ of this checkout, made by
build.py). Standard library only. Runs on macOS, Linux and Windows: on Windows the server stops a
run with its stop file and is itself ended with Ctrl+Break.
"""
import http.client
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = Path(os.environ.get("RAMAN_DEPLOY_DIR") or ROOT / "deploy").resolve()
WINDOWS = os.name == "nt"
RUNNER = "raman_sim_runner.exe" if WINDOWS else "raman_sim_runner"
RUN = {"power": "HIGH", "sample_id": "STUDIO-LIVE-TEST", "operator": "studio tests", "location": "test bench"}


class StudioLiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for part in (RUNNER, "handshake_v2", "virtual_sample", "data_layer", "studio", "datafed_python.txt"):
            if not (DEPLOY / part).exists():
                raise AssertionError("%s is missing: build the deploy folder first (python build.py)" % (DEPLOY / part))

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="raman_studio_live_")).resolve()
        self.addCleanup(shutil.rmtree, self.home, True)
        shutil.copy2(DEPLOY / RUNNER, self.home)
        for folder in ("handshake_v2", "virtual_sample", "data_layer", "models", "studio"):
            shutil.copytree(DEPLOY / folder, self.home / folder)
        for name in ("raman_python.txt", "datafed_python.txt"):
            shutil.copy2(DEPLOY / name, self.home / name)
        (self.home / "scan_sessions").mkdir()
        python = (DEPLOY / "datafed_python.txt").read_text(encoding="utf-8").splitlines()[0].strip()
        environment = dict(os.environ, PYTHONPATH=str(self.home / "data_layer"), PYTHONUTF8="1")
        if WINDOWS:
            # The copied runner finds the Qt libraries and plugins windeployqt put in the deploy folder.
            environment["PATH"] = str(DEPLOY) + os.pathsep + environment.get("PATH", "")
            environment["QT_PLUGIN_PATH"] = str(DEPLOY)
            options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        else:
            options = {"start_new_session": True}
        self.server = subprocess.Popen([python, "-m", "raman_datafed", "--home", str(self.home), "studio", "--no-open", "--port", "0"],
                                       cwd=self.home, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, **options)
        self.addCleanup(self.kill_server)
        first = self.server.stdout.readline().decode("utf-8", "replace")
        answer = json.loads(first)
        self.assertTrue(answer.get("ok"), first)
        self.url = answer["url"]
        self.port = int(self.url.rstrip("/").rsplit(":", 1)[1])
        self.origin = "http://127.0.0.1:%d" % self.port

    def kill_server(self):
        if self.server.poll() is None:
            self.server.kill()
            self.server.wait(10)
        self.server.stdout.close()

    def request(self, method, path, fields=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            headers = {"Content-Type": "application/json", "Origin": self.origin} if method == "POST" else {}
            connection.request(method, path, body=json.dumps(fields or {}) if method == "POST" else None, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def scan(self):
        return self.request("GET", "/api/scan")[1]

    def wait_for(self, condition, what, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.scan()
            if condition(state):
                return state
            time.sleep(0.25)
        self.fail("timed out waiting for %s; log:\n%s" % (what, "\n".join(self.scan().get("log_tail", []))))

    def helpers_left(self):
        if WINDOWS:
            listing = subprocess.run(["powershell", "-NoProfile", "-Command",
                                      "Get-CimInstance Win32_Process | ForEach-Object { $_.CommandLine }"],
                                     capture_output=True, text=True, check=True).stdout
        else:
            listing = subprocess.run(["/bin/ps", "-axo", "command="], capture_output=True, text=True, check=True).stdout
        # Qt passes some paths with forward slashes on Windows: look for both spellings of HOME.
        spellings = {str(self.home), self.home.as_posix()}
        return [line for line in listing.splitlines()
                if any(text in line for text in spellings) and "raman_datafed" not in line]

    def test_play_a_capture_then_stop_a_scan_then_end_the_server(self):
        status, ping = self.request("GET", "/api/ping")
        self.assertEqual(status, 200, ping)
        self.assertTrue(ping["simulated_stack_available"], ping)

        # Play: a single capture runs to its end.
        status, answer = self.request("POST", "/api/run", dict(RUN, mode="single"))
        self.assertEqual((status, answer["ok"], answer["simulated"]), (200, True, True), answer)
        state = self.wait_for(lambda s: s["run"] and not s["run"]["running"], "the single capture to end", 180)
        log = "\n".join(state["log_tail"])
        self.assertEqual(state["run"]["exit_code"], 0, log)
        self.assertIn("[runner] Laser OFF confirmed", log)
        self.assertIn("[runner] Done", log)
        self.assertEqual(len(list(self.home.glob("scan_sessions/single_*/point_0001.json"))), 1)

        # Play a 1D scan, then Stop: the run stops as the Stop button does and switches the laser off.
        status, answer = self.request("POST", "/api/run", dict(RUN, mode="1d-x"))
        self.assertEqual((status, answer["ok"]), (200, True), answer)
        self.wait_for(lambda s: any("Point 2 of 13 saved" in line for line in s["log_tail"]), "the scan's second point", 240)
        status, answer = self.request("POST", "/api/stop")
        self.assertEqual((status, answer["ok"], answer["forced"]), (200, True, False), answer)
        self.assertEqual(answer["exit_code"], 128 + signal.SIGTERM, answer)
        state = self.wait_for(lambda s: s["log_tail"][-1].startswith("[studio] simulated run ended"), "the end in the log", 30)
        log = "\n".join(state["log_tail"])
        self.assertIn("Stop requested: stopping the scan as the Stop button does", log)
        self.assertIn("[runner] Laser OFF confirmed", log)
        self.assertIn("[runner] Stopped on request (SIGTERM)", log)
        saved = list(self.home.glob("scan_sessions/1d_x_scan_*/point_*.json"))
        self.assertTrue(2 <= len(saved) < 13, saved)
        time.sleep(1.0)
        self.assertEqual(self.helpers_left(), [], "a helper program outlived its run")

        # The scans are in the data the page shows.
        self.assertTrue(self.scan()["session"], "the newest session is shown")

        # Ending the server: Ctrl+Break on Windows, SIGTERM elsewhere.
        self.server.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)
        self.assertEqual(self.server.wait(30), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
