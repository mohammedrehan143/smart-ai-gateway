"""Full Terminal and Cross-Platform Process Execution Engine for Smart AI Gateway.

Provides genuine terminal execution capabilities:
- Execute shell commands across Windows and POSIX.
- Capture stdout, stderr, exit code, and execution latency.
- Handle command timeouts safely.
- Background process management (start, stop, status, logs, list).
- Parallel command execution.
- Script execution for Python, Node, TypeScript, Shell, etc.
- Dependency installation (pip, npm, yarn, pnpm, cargo).
- Executable discovery and free port finding for dev servers.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ProcessManager:
    """Manages synchronous and asynchronous/background system processes."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()
        self.log_dir = self.workspace_root / ".smartai" / "process_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._background_processes: Dict[str, Dict[str, Any]] = {}

    @property
    def is_windows(self) -> bool:
        return platform.system() == "Windows"

    def run_command(
        self,
        command: str,
        timeout_seconds: int = 60,
        cwd: Optional[Path | str] = None,
        env: Optional[Dict[str, str]] = None,
        shell: Optional[str] = None,
    ) -> Tuple[bool, str, int]:
        """Executes a command synchronously in the specified directory.

        Returns: (success: bool, combined_output: str, exit_code: int)
        """
        start_time = time.time()
        work_dir = Path(cwd).resolve() if cwd else self.workspace_root

        merged_env = os.environ.copy()
        merged_env["PYTHONUNBUFFERED"] = "1"
        if env:
            merged_env.update(env)

        # Allow explicit shell invocation
        cmd_to_run = command
        executable = shell
        if shell and shell.lower() in ("powershell", "pwsh"):
            cmd_to_run = f'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "{command}"'
            executable = None

        try:
            proc = subprocess.run(
                cmd_to_run,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=str(work_dir),
                env=merged_env,
                executable=executable,
            )
            elapsed = time.time() - start_time
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()

            sections = []
            if out:
                sections.append(f"STDOUT:\n{out}")
            if err:
                sections.append(f"STDERR:\n{err}")
            sections.append(f"Exit Code: {proc.returncode} (duration: {elapsed:.2f}s)")

            output_str = "\n\n".join(sections)
            return (proc.returncode == 0, output_str, proc.returncode)

        except subprocess.TimeoutExpired as exc:
            elapsed = time.time() - start_time
            out = (exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")).strip()
            err = (exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")).strip()
            msg = f"Command timed out after {timeout_seconds} seconds (elapsed: {elapsed:.2f}s)."
            if out:
                msg += f"\nPartial STDOUT:\n{out}"
            if err:
                msg += f"\nPartial STDERR:\n{err}"
            return (False, msg, -1)

        except Exception as exc:
            return (False, f"Command execution failed: {exc}", -1)

    def run_script(
        self,
        script_path: str,
        interpreter: Optional[str] = None,
        args: Optional[List[str]] = None,
        timeout_seconds: int = 60,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str, int]:
        """Runs a script using an interpreter (e.g. python, node, bash)."""
        resolved_script = (Path(cwd).resolve() if cwd else self.workspace_root) / script_path
        if not resolved_script.is_file():
            return False, f"Script not found: '{script_path}'", -1

        ext = resolved_script.suffix.lower()
        cmd_prefix = interpreter
        if not cmd_prefix:
            if ext in (".py", ".pyw"):
                cmd_prefix = f'"{sys.executable}"'
            elif ext in (".js", ".mjs", ".cjs"):
                cmd_prefix = "node"
            elif ext in (".ts", ".mts"):
                cmd_prefix = "npx ts-node"
            elif ext in (".sh",):
                cmd_prefix = "bash"
            elif ext in (".ps1",):
                cmd_prefix = "powershell -File"
            elif ext in (".bat", ".cmd"):
                cmd_prefix = "cmd /c"
            else:
                cmd_prefix = ""

        arg_str = " ".join(f'"{a}"' for a in (args or []))
        full_command = f'{cmd_prefix} "{resolved_script}" {arg_str}'.strip()
        return self.run_command(full_command, timeout_seconds=timeout_seconds, cwd=cwd)

    def start_background_process(
        self,
        command: str,
        process_name: Optional[str] = None,
        cwd: Optional[Path | str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, str]:
        """Launches a long-running process in the background.

        Returns: (success: bool, message: str, process_id: str)
        """
        proc_id = process_name or f"proc_{int(time.time() * 1000)}"
        if proc_id in self._background_processes:
            existing = self._background_processes[proc_id]
            if existing["popen"].poll() is None:
                return False, f"Process '{proc_id}' is already running (PID: {existing['pid']}).", proc_id

        work_dir = Path(cwd).resolve() if cwd else self.workspace_root
        log_file = self.log_dir / f"{proc_id}.log"

        merged_env = os.environ.copy()
        merged_env["PYTHONUNBUFFERED"] = "1"
        if env:
            merged_env.update(env)

        try:
            log_handle = open(log_file, "a+", encoding="utf-8")
            popen = subprocess.Popen(
                command,
                shell=True,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                cwd=str(work_dir),
                env=merged_env,
            )

            self._background_processes[proc_id] = {
                "id": proc_id,
                "command": command,
                "pid": popen.pid,
                "start_time": time.time(),
                "popen": popen,
                "log_file": str(log_file),
                "log_handle": log_handle,
                "cwd": str(work_dir),
            }

            return (
                True,
                f"Started background process '{proc_id}' (PID: {popen.pid}). Logs at '{log_file.name}'.",
                proc_id,
            )
        except Exception as exc:
            return False, f"Failed to start background process '{proc_id}': {exc}", proc_id

    def stop_background_process(self, process_id: str) -> Tuple[bool, str]:
        """Gracefully stops or terminates a background process."""
        proc_info = self._background_processes.get(process_id)
        if not proc_info:
            return False, f"Process '{process_id}' not found in active registry."

        popen: subprocess.Popen = proc_info["popen"]
        ret_code = popen.poll()

        if ret_code is None:
            try:
                if self.is_windows:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc_info["pid"])],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    try:
                        popen.wait(timeout=2)
                    except Exception:
                        pass
                else:
                    popen.terminate()
                    try:
                        popen.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        popen.kill()
                        popen.wait(timeout=2)
            except Exception as exc:
                return False, f"Failed to stop process '{process_id}': {exc}"

        if "log_handle" in proc_info and proc_info["log_handle"] and not proc_info["log_handle"].closed:
            try:
                proc_info["log_handle"].flush()
                proc_info["log_handle"].close()
            except Exception:
                pass

        return True, f"Successfully stopped process '{process_id}' (PID: {proc_info['pid']})."

    def stop_all(self) -> None:
        """Stops all running background processes and closes handles."""
        for pid in list(self._background_processes.keys()):
            try:
                self.stop_background_process(pid)
            except Exception:
                pass

    def get_process_status(self, process_id: str, tail_lines: int = 30) -> Tuple[bool, Dict[str, Any]]:
        """Returns the status and recent logs of a background process."""
        proc_info = self._background_processes.get(process_id)
        if not proc_info:
            return False, {"error": f"Process '{process_id}' not found."}

        popen: subprocess.Popen = proc_info["popen"]
        ret_code = popen.poll()
        is_running = ret_code is None
        elapsed = time.time() - proc_info["start_time"]

        logs = ""
        log_path = Path(proc_info["log_file"])
        if "log_handle" in proc_info and proc_info["log_handle"] and not proc_info["log_handle"].closed:
            try:
                proc_info["log_handle"].flush()
            except Exception:
                pass

        if log_path.exists():
            try:
                raw_logs = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                logs = "\n".join(raw_logs[-tail_lines:])
            except Exception:
                logs = "(could not read log file)"

        status = {
            "id": process_id,
            "pid": proc_info["pid"],
            "command": proc_info["command"],
            "is_running": is_running,
            "exit_code": ret_code,
            "uptime_seconds": round(elapsed, 2),
            "recent_logs": logs,
        }
        return True, status

    def list_background_processes(self) -> List[Dict[str, Any]]:
        """Lists all registered background processes and their current state."""
        results = []
        for pid in list(self._background_processes.keys()):
            ok, status = self.get_process_status(pid, tail_lines=5)
            if ok:
                results.append(status)
        return results

    def run_parallel_commands(
        self,
        commands: List[str],
        timeout_seconds: int = 60,
        cwd: Optional[Path | str] = None,
        max_workers: int = 4,
    ) -> List[Dict[str, Any]]:
        """Executes a list of commands in parallel using a thread pool."""
        results: List[Dict[str, Any]] = []

        with ThreadPoolExecutor(max_workers=min(max_workers, len(commands) or 1)) as executor:
            futures = {executor.submit(self.run_command, cmd, timeout_seconds, cwd): cmd for cmd in commands}
            for future in as_completed(futures):
                cmd = futures[future]
                try:
                    success, output, code = future.result()
                    results.append(
                        {
                            "command": cmd,
                            "success": success,
                            "exit_code": code,
                            "output": output,
                        }
                    )
                except Exception as exc:
                    results.append(
                        {
                            "command": cmd,
                            "success": False,
                            "exit_code": -1,
                            "output": f"Exception: {exc}",
                        }
                    )
        return results

    def install_dependencies(
        self,
        package_manager: str,
        packages: Optional[List[str]] = None,
        cwd: Optional[Path | str] = None,
    ) -> Tuple[bool, str]:
        """Installs dependencies using pip, npm, yarn, pnpm, or cargo."""
        pm = package_manager.lower().strip()
        pkg_str = " ".join(packages or [])

        if pm == "pip":
            executable = f'"{sys.executable}"' if sys.executable else "python"
            cmd = (
                f"{executable} -m pip install {pkg_str}"
                if pkg_str
                else f"{executable} -m pip install -r requirements.txt"
            )
        elif pm == "npm":
            cmd = f"npm install {pkg_str}" if pkg_str else "npm install"
        elif pm == "yarn":
            cmd = f"yarn add {pkg_str}" if pkg_str else "yarn install"
        elif pm == "pnpm":
            cmd = f"pnpm add {pkg_str}" if pkg_str else "pnpm install"
        elif pm == "cargo":
            cmd = f"cargo add {pkg_str}" if pkg_str else "cargo build"
        else:
            return False, f"Unsupported package manager: '{package_manager}'"

        success, out, code = self.run_command(cmd, timeout_seconds=180, cwd=cwd)
        return success, f"[{pm.upper()} install result - Exit Code {code}]:\n{out}"

    def discover_executables(self, executables: Optional[List[str]] = None) -> Dict[str, Optional[str]]:
        """Checks for presence and path of common engineering tools in system PATH."""
        targets = executables or [
            "git",
            "python",
            "node",
            "npm",
            "yarn",
            "pnpm",
            "docker",
            "docker-compose",
            "cargo",
            "rustc",
            "go",
            "java",
            "javac",
            "gcc",
            "g++",
            "make",
            "powershell",
            "bash",
        ]
        results = {}
        for exe in targets:
            results[exe] = shutil.which(exe)
        return results

    def find_available_port(self, start_port: int = 3000, max_tries: int = 100) -> Optional[int]:
        """Finds an available TCP port starting from start_port."""
        for port in range(start_port, start_port + max_tries):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.2)
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        return None


default_process_manager = ProcessManager()
