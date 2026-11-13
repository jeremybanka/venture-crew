"""Read native Codex quota without opening a model conversation or reading tokens.

NativeClient adapted from Jeremy's CS16ND factory observer (read-only source).
No model turn is created; no credential file is read.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading
import time


class NativeClient:
    def __init__(self, executable="codex", cwd=None):
        self.proc = subprocess.Popen(
            [executable, "-c", "features.plugins=false", "-c", "features.apps=false", "app-server"],
            cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True,
        )
        self.inbox = queue.Queue(maxsize=2048)
        self.sequence = 0
        self.notifications = deque(maxlen=1000)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.request("initialize", {"clientInfo": {"name": "wayforge-quota", "version": "1.0"},
                                        "capabilities": {"experimentalApi": True}})
            self.send({"method": "initialized"})
        except BaseException:
            self.close()
            raise

    def _read(self):
        try:
            for line in self.proc.stdout:
                if len(line) > 2_000_000:
                    raise ValueError("oversized native response")
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                self.inbox.put(value, timeout=1)
        except Exception:
            pass
        finally:
            try:
                self.inbox.put(None, timeout=1)
            except queue.Full:
                pass

    def send(self, message):
        self.proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None, timeout=45):
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native quota request timed out")
            try:
                value = self.inbox.get(timeout=remaining)
            except queue.Empty as error:
                raise TimeoutError("native quota request timed out") from error
            if value is None:
                raise RuntimeError("native app-server closed")
            if value.get("id") != request_id or "method" in value:
                if "method" in value:
                    self.notifications.append(value)
                continue
            if "error" in value:
                # Do not copy arbitrary backend text, which can include account data.
                raise RuntimeError("native request failed: " + method)
            return value.get("result")

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGTERM)
                try:
                    self.proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                    self.proc.wait(timeout=2)
        self.proc.stdout.close()
