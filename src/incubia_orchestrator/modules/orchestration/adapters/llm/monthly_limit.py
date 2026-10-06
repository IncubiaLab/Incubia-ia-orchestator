"""Conservative, process-shared allowance for local API smoke tests."""
import fcntl
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from incubia_orchestrator.modules.orchestration.ports.llm import GenerationFailure


class MonthlyCallLimiter:
    def __init__(self, path: Path, *, max_calls: int = 6, min_interval_seconds: int = 10,
                 clock: Callable[[], float] = time.time):
        self.path = path
        self.max_calls = max_calls
        self.min_interval_seconds = min_interval_seconds
        self.clock = clock

    def reserve(self) -> None:
        """Count the attempt before sending it; failed calls are counted too."""
        try:
            self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
            with os.fdopen(fd, "r+", encoding="utf-8") as state_file:
                fcntl.flock(state_file, fcntl.LOCK_EX)
                os.fchmod(state_file.fileno(), 0o600)
                raw = state_file.read()
                state = json.loads(raw) if raw else {}
                now = self.clock()
                month = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m")
                if state.get("month") != month:
                    state = {"month": month, "calls": 0, "last_call_epoch": 0}
                if state["calls"] >= self.max_calls:
                    raise GenerationFailure("LOCAL_MONTHLY_LIMIT")
                if now - state["last_call_epoch"] < self.min_interval_seconds:
                    raise GenerationFailure("LOCAL_COOLDOWN")
                state["calls"] += 1
                state["last_call_epoch"] = now
                state_file.seek(0)
                json.dump(state, state_file)
                state_file.truncate()
                state_file.flush()
                os.fsync(state_file.fileno())
        except GenerationFailure:
            raise
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            raise GenerationFailure("LOCAL_LIMIT_UNAVAILABLE") from None
