from __future__ import annotations

import asyncio
import shlex
from dataclasses import dataclass
from pathlib import Path

from .config import LOCAL

CACHE_DIR = Path.home() / ".cache" / "ccm"


@dataclass
class Result:
    rc: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.rc == 0

    @property
    def message(self) -> str:
        lines = (self.err.strip() or self.out.strip()).splitlines()
        return lines[-1] if lines else f"exit {self.rc}"


def ssh_opts(batch: bool = True) -> list[str]:
    """Shared connection options; one multiplexed connection per host."""
    CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    opts = ["-o", "ControlMaster=auto", "-o", f"ControlPath={CACHE_DIR}/cm-%C",
            "-o", "ControlPersist=10m", "-o", "ConnectTimeout=8"]
    if batch:
        opts += ["-o", "BatchMode=yes"]
    return opts


def argv_for(host: str, script: str) -> list[str]:
    if host == LOCAL:
        return ["sh", "-c", script]
    # sh -c so the script does not depend on the remote login shell's syntax
    return ["ssh", *ssh_opts(), "--", host, "sh -c " + shlex.quote(script)]


async def run(host: str, script: str, stdin: bytes = b"", timeout: float = 20) -> Result:
    """Run a POSIX sh script on the host, feeding it stdin."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv_for(host, script), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    except OSError as e:
        return Result(127, "", str(e))
    try:
        out, err = await asyncio.wait_for(proc.communicate(stdin), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return Result(124, "", "timed out")
    return Result(proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace"))
