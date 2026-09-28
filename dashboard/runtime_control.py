"""Local, single-process JEV runtime control for the dashboard and CLI."""

from __future__ import annotations

import msvcrt
import hashlib
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRACE = PROJECT_ROOT / ".log" / "jev-dashboard.jsonl"
LOCK_FILE = Path(tempfile.gettempdir()) / (
    "jev-pvz-" + hashlib.sha256(str(PROJECT_ROOT).casefold().encode("utf-8")).hexdigest()[:16] + ".lock"
)
PROCESS_LOG = PROJECT_ROOT / ".log" / "jev-dashboard-process.log"


class RuntimeProcessLock:
    """An OS byte-range lock held by the actual JEV Loop process."""

    def __init__(self, path: Path = LOCK_FILE):
        self.path = path
        self._stream = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        try:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            stream.close()
            return False
        self._stream = stream
        return True

    def release(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.seek(0)
            msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._stream.close()
            self._stream = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("another JEV Loop is already running")
        return self

    def __exit__(self, *_exc):
        self.release()

    @classmethod
    def occupied(cls) -> bool:
        probe = cls()
        if not probe.acquire():
            return True
        probe.release()
        return False


class RuntimeController:
    """Own only the child started by this dashboard instance."""

    def __init__(
        self,
        trace_file: str | Path,
        state_reader: Callable[[], dict[str, Any]],
        *,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
    ):
        self.trace_file = Path(trace_file).resolve()
        self.state_reader = state_reader
        self.process_factory = process_factory
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._stopped_by_user = False
        self._error: str | None = None

    def _readiness(self) -> tuple[bool, str]:
        state = self.state_reader()
        game = state.get("game") or {}
        if state.get("status") != "ok" or state.get("valid") is not True:
            return False, "等待有效的游戏采样"
        if game.get("paused") is True:
            return False, "游戏已暂停；恢复后可启动"
        if game.get("phase") != "playing" or game.get("paused") is not False:
            return False, "等待游戏进入进行中"
        return True, "游戏进行中，可以启动"

    def status(self) -> dict[str, Any]:
        with self._lock:
            ready, readiness_message = self._readiness()
            process = self._process
            code = process.poll() if process is not None else None
            running = process is not None and code is None
            external = not running and RuntimeProcessLock.occupied()
            if running:
                state = "running"
                message = "JEV 正在运行"
            elif external:
                state = "occupied"
                message = "已有 JEV 进程正在运行"
            elif process is None:
                state = "idle"
                message = readiness_message
            elif self._stopped_by_user:
                state = "stopped"
                message = "已由 STOP 结束"
            elif code == 0:
                state = "stopped"
                message = "JEV 已自动结束"
            else:
                state = "failed"
                message = self._error or "JEV 启动失败或异常退出；请查看运行日志"
            return {
                "state": state,
                "message": message,
                "pid": process.pid if process is not None else None,
                "exit_code": code,
                "game_ready": ready,
                "can_start": ready and not running and not external,
                "can_stop": running,
                "trace_file": str(self.trace_file),
            }

    def start(self) -> tuple[int, dict[str, Any]]:
        with self._lock:
            current = self.status()
            if not current["can_start"]:
                return 409, current
            self.trace_file.parent.mkdir(parents=True, exist_ok=True)
            PROCESS_LOG.parent.mkdir(parents=True, exist_ok=True)
            command = [sys.executable, str(PROJECT_ROOT / "main.py"), "jev-loop", "--trace-file", str(self.trace_file)]
            try:
                with PROCESS_LOG.open("ab") as output:
                    process = self.process_factory(
                        command,
                        cwd=str(PROJECT_ROOT),
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
            except OSError as exc:
                self._error = f"无法启动 JEV：{type(exc).__name__}"
                return 500, self.status() | {"message": self._error}
            self._process = process
            self._stopped_by_user = False
            self._error = None
            return 202, self.status()

    def stop(self) -> tuple[int, dict[str, Any]]:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                return 409, self.status()
            try:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired) as exc:
                self._error = f"STOP 未能确认进程退出：{type(exc).__name__}"
                return 500, self.status() | {"message": self._error}
            self._stopped_by_user = True
            return 200, self.status()

    def close(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self.stop()
