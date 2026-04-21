"""
/doctor health check — claw-code inspired preflight diagnostics.
Run before every trading session. Machine-readable JSON output.
Checks: env vars, API reachability, branch freshness, disk space, cron status.
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import requests

from src.events import EventEmitter, EventKind


@dataclass
class CheckResult:
    name: str
    ok: bool
    severity: str  # info | warn | critical
    detail: str
    fix_hint: str = ""
    latency_ms: Optional[float] = None


@dataclass
class DoctorReport:
    overall: str  # ok | degraded | critical
    checks: list[CheckResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    version: str = "1.0.0"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


class Doctor:
    """Preflight diagnostic suite for the trading bot."""

    def __init__(self, emitter: EventEmitter):
        self.emitter = emitter
        self.checks: list[CheckResult] = []

    def _add(self, r: CheckResult) -> CheckResult:
        self.checks.append(r)
        kind = EventKind.DOCTOR_OK if r.ok else EventKind.DOCTOR_FAIL
        self.emitter.emit(
            kind,
            check=r.name,
            ok=r.ok,
            severity=r.severity,
            detail=r.detail,
            latency_ms=r.latency_ms,
        )
        return r

    def check_env(self, required: list[str]) -> CheckResult:
        missing = [k for k in required if not os.getenv(k)]
        ok = len(missing) == 0
        return self._add(CheckResult(
            name="env_vars",
            ok=ok,
            severity="critical" if not ok else "info",
            detail=f"missing: {missing}" if missing else "all present",
            fix_hint=f"export {' '.join(missing)}" if missing else "",
        ))

    def check_api(self, name: str, url: str, timeout: float = 5.0, headers: Optional[dict] = None) -> CheckResult:
        t0 = time.time()
        try:
            resp = requests.get(url, timeout=timeout, headers=headers or {})
            latency = (time.time() - t0) * 1000
            ok = resp.status_code < 500
            return self._add(CheckResult(
                name=f"api_{name}",
                ok=ok,
                severity="warn" if not ok else "info",
                detail=f"status={resp.status_code} latency={latency:.0f}ms",
                latency_ms=round(latency, 2),
                fix_hint="check API key / network" if not ok else "",
            ))
        except Exception as e:
            latency = (time.time() - t0) * 1000
            return self._add(CheckResult(
                name=f"api_{name}",
                ok=False,
                severity="critical",
                detail=str(e),
                latency_ms=round(latency, 2),
                fix_hint="check network / VPN / DNS",
            ))

    def check_disk(self, path: str = ".", min_gb: float = 1.0) -> CheckResult:
        st = os.statvfs(path)
        free_gb = st.f_frsize * st.f_bavail / (1024 ** 3)
        ok = free_gb >= min_gb
        return self._add(CheckResult(
            name="disk_space",
            ok=ok,
            severity="critical" if not ok else "info",
            detail=f"{free_gb:.2f}GB free (min {min_gb}GB)",
            fix_hint="free up disk space" if not ok else "",
        ))

    def check_branch_fresh(self, base: str = "main") -> CheckResult:
        try:
            # fetch latest base
            subprocess.run(["git", "fetch", "origin", base], capture_output=True, check=False)
            local = subprocess.run(["git", "rev-parse", base], capture_output=True, text=True, check=True).stdout.strip()
            remote = subprocess.run(["git", "rev-parse", f"origin/{base}"], capture_output=True, text=True, check=True).stdout.strip()
            ok = local == remote
            return self._add(CheckResult(
                name="branch_fresh",
                ok=ok,
                severity="warn" if not ok else "info",
                detail=f"local={local[:8]} remote={remote[:8]}",
                fix_hint=f"git pull origin {base}" if not ok else "",
            ))
        except Exception as e:
            return self._add(CheckResult(
                name="branch_fresh",
                ok=False,
                severity="warn",
                detail=str(e),
                fix_hint="not a git repo or no remote",
            ))

    def check_cron(self, pattern: str = "trading_bot") -> CheckResult:
        try:
            out = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=True).stdout
            ok = pattern in out
            return self._add(CheckResult(
                name="cron_active",
                ok=ok,
                severity="warn" if not ok else "info",
                detail="cron entry found" if ok else "no cron entry",
                fix_hint="add crontab entry" if not ok else "",
            ))
        except Exception as e:
            return self._add(CheckResult(
                name="cron_active",
                ok=False,
                severity="warn",
                detail=str(e),
                fix_hint="crontab not available",
            ))

    def run(self, config: dict) -> DoctorReport:
        self.emitter.emit(EventKind.DOCTOR_RUN)

        # 1. Env vars
        self.check_env(config.get("required_env", []))

        # 2. APIs
        for api in config.get("apis", []):
            self.check_api(api["name"], api["url"], headers=api.get("headers"))

        # 3. Disk
        self.check_disk(min_gb=config.get("min_disk_gb", 1.0))

        # 4. Git branch freshness
        if config.get("check_branch", True):
            self.check_branch_fresh(config.get("base_branch", "main"))

        # 5. Cron
        if config.get("check_cron", True):
            self.check_cron(config.get("cron_pattern", "trading_bot"))

        # Overall verdict
        criticals = [c for c in self.checks if not c.ok and c.severity == "critical"]
        warns = [c for c in self.checks if not c.ok and c.severity == "warn"]
        overall = "critical" if criticals else "degraded" if warns else "ok"

        report = DoctorReport(overall=overall, checks=self.checks)
        self.emitter.emit(
            EventKind.DOCTOR_OK if overall == "ok" else EventKind.DOCTOR_FAIL,
            overall=overall,
            critical_count=len(criticals),
            warn_count=len(warns),
        )
        return report


def main() -> None:
    """CLI entrypoint: ./doctor.py --config config.json"""
    import argparse
    parser = argparse.ArgumentParser(description="Trading bot preflight doctor")
    parser.add_argument("--config", default="config.json", help="config file path")
    parser.add_argument("--log-dir", default="logs", help="event log directory")
    args = parser.parse_args()

    emitter = EventEmitter(Path(args.log_dir), env="doctor")
    doctor = Doctor(emitter)

    cfg = {}
    if Path(args.config).exists():
        with open(args.config) as f:
            cfg = json.load(f)

    report = doctor.run(cfg)
    print(report.to_json())
    sys.exit(0 if report.overall == "ok" else 1)


if __name__ == "__main__":
    main()
