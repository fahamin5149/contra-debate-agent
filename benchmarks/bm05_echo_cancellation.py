"""BM-05: evaluate manually captured browser AEC and double-talk trials.

Acoustic trials require the target room, laptop speakers, microphone, and a
human speaker. This harness validates a JSON record so the result cannot be
declared from memory or from a synthetic loopback.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.metrics import word_error_rate

TRIALS = 20


def evaluate(record: dict[str, Any]) -> dict[str, Any]:
    trials = record.get("double_talk_trials")
    if not isinstance(trials, list) or len(trials) != TRIALS:
        raise ValueError(f"double_talk_trials must contain exactly {TRIALS} trials")
    wers = [word_error_rate(str(row["reference"]), str(row["hypothesis"])) for row in trials]
    preserved = sum(value <= 0.20 for value in wers)
    mean_wer = sum(wers) / len(wers)
    typical = int(record["self_triggers_typical"])
    rtt_ms = float(record["webrtc_rtt_ms"])
    passed = typical == 0 and preserved >= 18 and mean_wer <= 0.20 and rtt_ms <= 60
    return {
        "self_triggers_typical": typical,
        "self_triggers_high": int(record["self_triggers_high"]),
        "preserved_trials": preserved,
        "trial_count": TRIALS,
        "mean_wer": mean_wer,
        "webrtc_rtt_ms": rtt_ms,
        "verdict": "PASS" if passed else "FAIL",
    }


def template() -> dict[str, Any]:
    phrases = [
        "That is not the point I was making",
        "Stop and address the cost to renters",
        "You are assuming the conclusion",
        "Let me finish the argument first",
        "That evidence does not support your claim",
    ]
    return {
        "date": "YYYY-MM-DD",
        "room": "describe distance, volume, and devices",
        "aec_settings": {
            "echoCancellation": True,
            "noiseSuppression": True,
            "autoGainControl": True,
        },
        "self_triggers_typical": None,
        "self_triggers_high": None,
        "webrtc_rtt_ms": None,
        "double_talk_trials": [
            {"reference": phrases[index % len(phrases)], "hypothesis": ""}
            for index in range(TRIALS)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", nargs="?", type=Path)
    parser.add_argument("--write-template", type=Path)
    args = parser.parse_args()
    if args.write_template:
        args.write_template.write_text(json.dumps(template(), indent=2) + "\n", encoding="utf-8")
        return 0
    if args.record is None:
        parser.error("provide a trial record or --write-template PATH")
    result = evaluate(json.loads(args.record.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
