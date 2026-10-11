# Copyright Olivenda (Oliver Petz) 2026
"""Auto-updater: at start the game asks git in the background whether the repository on GitHub has new commits;
the main menu then offers the update, which is a plain `git pull` followed by a restart of the game.

Nothing of this may get in the way: no git, no network, no repository, a password prompt - the check just ends
quietly and the game runs as it is."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FETCH_TIMEOUT = 25.0
PULL_TIMEOUT = 120.0
# never wait for a prompt: no credentials dialog, no "trust this host?" question
GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=10"}


def _git(*args: str, timeout: float = FETCH_TIMEOUT) -> tuple[int, str]:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0     # no console flashing up
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, env=GIT_ENV, capture_output=True, text=True,
                             timeout=timeout, creationflags=flags)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return out.returncode, (out.stdout + out.stderr).strip()


class Updater:
    """state: "idle", "checking", "none" (up to date / no check possible), "available", "updating", "done",
    "failed"."""

    def __init__(self) -> None:
        self.state = "idle"
        self.branch = ""
        self.behind = 0
        self.commits: list[str] = []        # the new commits' subjects, newest first
        self.error = ""
        self.dismissed = False              # "later": not asked again until the next start

    @property
    def offer(self) -> bool:
        """The main menu shows the question (or the progress of the update)."""
        return self.state in ("updating", "done", "failed") or (self.state == "available" and not self.dismissed)

    def start_check(self) -> None:
        if self.state != "idle" or not (ROOT / ".git").exists():
            self.state = "none" if self.state == "idle" else self.state
            return
        self.state = "checking"
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self) -> None:
        code, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
        if code != 0 or branch == "HEAD":
            self.state = "none"             # no git, or a detached checkout: nothing to update to
            return
        code, _ = _git("fetch", "--quiet", "origin", branch)
        if code != 0:
            self.state = "none"             # offline / no access
            return
        code, count = _git("rev-list", "--count", f"HEAD..origin/{branch}")
        if code != 0 or not count.isdigit() or int(count) == 0:
            self.state = "none"
            return
        _, log = _git("log", "--format=%s", "-6", f"HEAD..origin/{branch}")
        self.branch = branch
        self.behind = int(count)
        self.commits = [line for line in log.splitlines() if line.strip()]
        self.state = "available"

    def start_update(self) -> None:
        if self.state != "available":
            return
        self.state = "updating"
        threading.Thread(target=self._update, daemon=True).start()

    def _update(self) -> None:
        # only fast-forward (never a merge of its own); local changes (e.g. freshly trained brains) are put aside
        # and back on top
        code, out = _git("pull", "--ff-only", "--autostash", "origin", self.branch, timeout=PULL_TIMEOUT)
        if code == 0:
            self.state = "done"
        else:
            self.error = out.splitlines()[-1] if out else "git pull fehlgeschlagen"
            self.state = "failed"

    def dismiss(self) -> None:
        if self.state == "available":
            self.dismissed = True
        elif self.state == "failed":
            self.state = "none"


def restart() -> None:
    """Start the game again in this process (the new code is loaded from scratch)."""
    import pygame
    pygame.quit()
    os.execv(sys.executable, [sys.executable, *sys.argv])
