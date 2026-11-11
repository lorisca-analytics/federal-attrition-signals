"""Check the clean CSVs against contract/tables.v1.json.

Usage:
    python -m fas.contract data/clean      # exit 1 and a list of problems if anything breaks
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "contract" / "tables.v1.json"

PARTS = ["quits", "retirements", "early_outs", "reductions_in_force",
         "transfers", "terminations_or_expired", "other"]


def parse(value: str, kind: str):
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "bool":
        if value not in ("true", "false"):
            raise ValueError(f"not a bool: {value!r}")
        return value == "true"
    if value == "":
        raise ValueError("empty")
    return value


def check_table(name: str, spec: dict, path: Path) -> list[str]:
    errs: list[str] = []
    if not path.exists():
        return [f"{name}: file missing ({path.name})"]
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        expected = list(spec["columns"])
        # Contract columns must come first and in order. Extra columns after them are allowed.
        if header[: len(expected)] != expected:
            missing = [c for c in expected if c not in header]
            errs.append(f"{name}: columns do not match contract"
                        + (f", missing {missing}" if missing else ", order changed"))
            return errs
        seen = set()
        for i, row in enumerate(reader, start=2):
            vals = {}
            for col, rule in spec["columns"].items():
                if rule.get("nullable") and row[col] == "":
                    continue
                try:
                    v = parse(row[col], rule["type"])
                except (ValueError, TypeError) as e:
                    errs.append(f"{name} line {i}: {col} {e}")
                    continue
                if "min" in rule and v < rule["min"]:
                    errs.append(f"{name} line {i}: {col}={v} below {rule['min']}")
                if "max" in rule and v > rule["max"]:
                    errs.append(f"{name} line {i}: {col}={v} above {rule['max']}")
                if "pattern" in rule and not re.match(rule["pattern"], v):
                    errs.append(f"{name} line {i}: {col}={v!r} does not match {rule['pattern']}")
                vals[col] = v
            key = tuple(row[k] for k in spec["key"])
            if key in seen:
                errs.append(f"{name} line {i}: duplicate key {key}")
            seen.add(key)
            if "parts_add_up" in spec["checks"] and all(p in vals for p in PARTS + ["separations"]):
                if sum(vals[p] for p in PARTS) != vals["separations"]:
                    errs.append(f"{name} line {i}: reasons do not add up to separations")
        if "rate_needs_flags" in spec["checks"]:
            if not any(c in header for c in ("provisional", "incomplete")):
                errs.append(f"{name}: has a rate but no trust flag")
    return errs


def validate(folder: Path, contract: Path = CONTRACT) -> list[str]:
    spec = json.loads(contract.read_text())
    errs = []
    for name, t in spec["tables"].items():
        errs += check_table(name, t, folder / f"{name}.csv")
    return errs


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    folder = Path(argv[0]) if argv else ROOT / "data" / "clean"
    errs = validate(folder)
    for e in errs[:50]:
        print(e)
    if errs:
        print(f"{len(errs)} problem(s)")
        return 1
    print(f"contract {json.loads(CONTRACT.read_text())['version']}: all tables pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
