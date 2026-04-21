import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.doctor import Doctor
from src.events import EventEmitter


def test_doctor_env():
    emitter = EventEmitter(Path("logs/test"), env="test")
    doc = Doctor(emitter)

    os.environ["TEST_KEY_1"] = "val1"
    r = doc.check_env(["TEST_KEY_1", "MISSING_KEY_999"])
    assert r.ok is False
    assert r.severity == "critical"
    emitter.close()
    print("test_doctor_env PASS")


def test_doctor_disk():
    emitter = EventEmitter(Path("logs/test"), env="test")
    doc = Doctor(emitter)

    r = doc.check_disk(min_gb=0.001)
    assert r.ok is True
    emitter.close()
    print("test_doctor_disk PASS")


def test_doctor_report():
    emitter = EventEmitter(Path("logs/test"), env="test")
    doc = Doctor(emitter)
    report = doc.run({
        "required_env": ["TEST_KEY_1"],
        "apis": [],
        "check_branch": False,
        "check_cron": False,
    })
    assert report.overall in ("ok", "degraded", "critical")
    print("test_doctor_report PASS")
    emitter.close()


if __name__ == "__main__":
    test_doctor_env()
    test_doctor_disk()
    test_doctor_report()
