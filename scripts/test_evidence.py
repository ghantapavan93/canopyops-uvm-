#!/usr/bin/env python3
"""Generate / verify the test counts shown on the Engineering Evidence screen.

WHY THIS EXISTS
---------------
That screen's entire value is "every number here is real and reproducible". The
counts used to be hand-typed into the template — and they drifted: the screen
claimed 136 backend tests and 17 Cypress specs while the suites had moved to 144
and 18. A reviewer who clones the repo, runs pytest, and sees a different number
than the screen has no reason to believe anything else on it.

So: the numbers are GENERATED from a real run, stamped with the commit and time
they came from, and `--check` re-runs the suites in CI and fails on any
disagreement. The screen cannot silently drift from reality again.

Usage
-----
    python scripts/test_evidence.py --update            # run all local suites, rewrite the JSON
    python scripts/test_evidence.py --update --suite pytest
    python scripts/test_evidence.py --check --suite pytest   # CI: fail on mismatch

`cypress` needs the stack up (docker compose up -d); `pytest` and `jest` don't.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
EVIDENCE = FRONTEND / "src" / "assets" / "test-evidence.json"


def _run(cmd: list[str] | str, cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd, cwd=cwd, shell=isinstance(cmd, str),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _pytest() -> dict:
    """Backend suite. Parses pytest's own summary line — the authoritative count."""
    py = BACKEND / ".venv" / "Scripts" / "python.exe"
    exe = str(py) if py.exists() else sys.executable
    # NB: no -q — under this runner it suppresses the final "N passed" summary
    # line, which is exactly what we need to parse.
    code, out = _run([exe, "-m", "pytest", "-p", "no:randomly", "--tb=no"], BACKEND)
    passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", out)) else 0
    failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
    if not passed and not failed:
        raise SystemExit(f"could not parse pytest output:\n{out[-2000:]}")
    return {
        "key": "pytest", "label": "backend pytest", "passed": passed, "failed": failed,
        "command": "cd backend && pytest", "exitCode": code,
    }


def _jest() -> dict:
    """Frontend unit suite. --json gives machine-readable totals."""
    code, out = _run("npm test -- --ci --json --silent", FRONTEND)
    # Jest prints the JSON blob among other noise; take the last {...} block.
    start = out.rfind('{"numFailedTest')
    if start == -1:
        start = out.find('{"numFailed')
    if start == -1:
        raise SystemExit(f"could not parse jest output:\n{out[-2000:]}")
    data = json.loads(out[start: out.rindex("}") + 1])
    return {
        "key": "jest", "label": "frontend Jest", "passed": data["numPassedTests"],
        "failed": data["numFailedTests"], "command": "cd frontend && npm test", "exitCode": code,
    }


def _cypress() -> dict:
    """E2E suite. Requires the stack on :8080 (docker compose up -d)."""
    code, out = _run("npx cypress run", FRONTEND)
    # Cypress' final summary row, e.g.
    #   "All specs passed!        00:20   18   18    -    -    -"
    #   "1 of 12 failed (8%)      00:30   18   17    1    -    -"
    # NB the failed/pending/skipped columns render as "-" (not 0) when empty, so
    # they must not be matched as \d+.
    m = re.search(
        r"(?:All specs passed!|\d+ of \d+ failed \(\d+%\))\s+[\d:]+\s+(\d+)\s+(\d+)\s+(\S+)",
        out,
    )
    if not m:
        raise SystemExit(f"could not parse cypress output:\n{out[-3000:]}")
    total, passed = int(m.group(1)), int(m.group(2))
    failed_col = m.group(3)
    failed = 0 if failed_col.strip("-|") == "" else int(failed_col)
    return {
        "key": "cypress", "label": "Cypress e2e", "passed": passed,
        "failed": failed if failed else max(0, total - passed),
        "command": "cd frontend && npx cypress run", "exitCode": code,
    }


RUNNERS = {"pytest": _pytest, "jest": _jest, "cypress": _cypress}


def _commit() -> str:
    code, out = _run(["git", "rev-parse", "--short", "HEAD"], ROOT)
    return out.strip() if code == 0 else "unknown"


def _load() -> dict:
    if EVIDENCE.exists():
        return json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return {"generatedAt": None, "commit": None, "suites": []}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--suite", choices=sorted(RUNNERS), action="append")
    args = ap.parse_args()
    if not (args.update or args.check):
        ap.error("pass --update or --check")

    suites = args.suite or sorted(RUNNERS)
    doc = _load()
    by_key = {s["key"]: s for s in doc.get("suites", [])}
    failures: list[str] = []

    for key in suites:
        print(f"[test-evidence] running {key} ...", flush=True)
        fresh = RUNNERS[key]()
        if fresh["failed"]:
            failures.append(f"{key}: suite itself is failing ({fresh['failed']} failed)")
        if args.check:
            claimed = by_key.get(key)
            if claimed is None:
                failures.append(f"{key}: no committed evidence — run --update")
            elif claimed["passed"] != fresh["passed"]:
                failures.append(
                    f"{key}: the Engineering Evidence screen claims {claimed['passed']} passing "
                    f"but a real run produced {fresh['passed']}. Run: "
                    f"python scripts/test_evidence.py --update --suite {key}"
                )
            else:
                print(f"[test-evidence] {key}: {fresh['passed']} passing — matches the screen")
        else:
            by_key[key] = fresh
            print(f"[test-evidence] {key}: {fresh['passed']} passing")

    if args.update:
        doc["suites"] = [by_key[k] for k in sorted(by_key)]
        doc["commit"] = _commit()
        doc["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        print(f"[test-evidence] wrote {EVIDENCE.relative_to(ROOT)} @ {doc['commit']}")

    if failures:
        print("\n[test-evidence] FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
