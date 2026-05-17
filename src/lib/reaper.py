"""Orphaned-browser reaper.

A safety net for Chromium / Playwright-driver processes that survive a job
(hung ``browser.close()`` under memory pressure, killed worker, etc.). Pure
stdlib, Linux ``/proc`` based — no extra dependency.

Conservative by design: a process is only killed when BOTH hold:
  * its cmdline clearly belongs to a Playwright-launched browser
    (``playwright_chromiumdev_profile`` user-data-dir or the ms-playwright
    chromium binary), and
  * it is older than ``REAPER_MAX_AGE_SECONDS`` (default 900s, comfortably
    longer than the 600s arq ``job_timeout``), so no live job can own it.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_BROWSER_MARKERS = (
    "playwright_chromiumdev_profile",
    "ms-playwright",
)
_TMP_PROFILE_GLOBS = (
    "playwright_chromiumdev_profile-*",
    ".org.chromium.Chromium.*",
)

_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def _uptime_seconds() -> float | None:
    try:
        with open("/proc/uptime", encoding="ascii") as fh:
            return float(fh.read().split()[0])
    except (OSError, ValueError):
        return None


def _proc_age_seconds(pid: str, uptime: float) -> float | None:
    """Process age from /proc/<pid>/stat field 22 (starttime, clock ticks)."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as fh:
            data = fh.read()
        # comm may contain ')'; split on the last ')' to stay correct.
        after = data[data.rfind(")") + 2 :].split()
        starttime_ticks = float(after[19])  # field 22 -> index 19 post-comm
    except (OSError, ValueError, IndexError):
        return None
    return uptime - (starttime_ticks / _CLK_TCK)


def _cmdline(pid: str) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return fh.read().replace(b"\x00", b" ").decode("utf-8", "replace")
    except OSError:
        return ""


def reap_orphan_browsers(max_age_seconds: int) -> dict[str, int]:
    """Kill stale Playwright browsers and clean leftover temp profiles.

    Returns counts for observability/logging. Safe to call when /proc is
    unavailable (non-Linux / restricted): it simply no-ops.
    """
    killed = 0
    scanned = 0
    proc_root = Path("/proc")
    uptime = _uptime_seconds()
    if uptime is not None and proc_root.is_dir():
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            pid = entry.name
            if pid == str(os.getpid()):
                continue
            cmd = _cmdline(pid)
            if "chrome" not in cmd and "chromium" not in cmd:
                continue
            if not any(marker in cmd for marker in _BROWSER_MARKERS):
                continue
            scanned += 1
            age = _proc_age_seconds(pid, uptime)
            if age is None or age < max_age_seconds:
                continue
            try:
                os.kill(int(pid), signal.SIGKILL)
                killed += 1
                logger.warning("reaper killed orphan browser pid=%s age=%ds", pid, int(age))
            except (OSError, ValueError) as exc:
                logger.debug("reaper could not kill pid=%s: %s", pid, exc)

    cleaned = _clean_tmp_profiles(max_age_seconds)
    if killed or cleaned:
        logger.info(
            "reaper sweep: scanned=%d killed=%d tmp_dirs_removed=%d", scanned, killed, cleaned
        )
    return {"scanned": scanned, "killed": killed, "tmp_removed": cleaned}


def _clean_tmp_profiles(max_age_seconds: int) -> int:
    removed = 0
    tmp = Path("/tmp")
    now = time.time()
    if not tmp.is_dir():
        return 0
    for pattern in _TMP_PROFILE_GLOBS:
        for path in tmp.glob(pattern):
            try:
                if now - path.stat().st_mtime < max_age_seconds:
                    continue
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
    return removed
