import argparse
import math
import re
import statistics
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class EvalRun:
    passed: int
    failed: int
    avg_latency_s: float
    per_test_latencies_s: List[float]
    raw_output: str


def _quantile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    pos = q * (len(v) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return v[lo]
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def _parse_summary(output: str) -> Tuple[int, int, float]:
    m_pass = re.search(r"Passed:\s+(\d+)", output)
    m_fail = re.search(r"Failed:\s+(\d+)", output)
    m_avg = re.search(r"Avg Latency:\s+([0-9]+(?:\.[0-9]+)?)\s+seconds", output)
    if not (m_pass and m_fail and m_avg):
        raise ValueError("Could not parse evaluation summary from output.")
    return int(m_pass.group(1)), int(m_fail.group(1)), float(m_avg.group(1))


def _parse_latencies(output: str) -> List[float]:
    return [float(x) for x in re.findall(r"Latency:\s+([0-9]+(?:\.[0-9]+)?)\s+seconds", output)]


def _parse_failures(output: str) -> Dict[int, Dict[str, int]]:
    """
    Returns: { test_number: { reason: count } }
    """
    failures: Dict[int, Dict[str, int]] = {}
    # Match each test block and capture status + optional failure reason line.
    pattern = re.compile(
        r"Test\s+(\d+)/10:.*?\n"
        r"\s+Latency:.*?\n"
        r"\s+Reply:.*?\n"
        r"\s+Cart:.*?\n"
        r"\s+Confirmed:.*?\n"
        r"\s+Status:\s+(PASS|FAIL)"
        r"(?:\n\s+Failures:\s+([^\n]+))?",
        re.S,
    )
    for m in pattern.finditer(output):
        test_num = int(m.group(1))
        status = m.group(2)
        reason = (m.group(3) or "").strip() or "Unknown"
        if status == "FAIL":
            failures.setdefault(test_num, {})
            failures[test_num][reason] = failures[test_num].get(reason, 0) + 1
    return failures


def run_once(cwd: str) -> EvalRun:
    output = subprocess.check_output(
        ["python", "-m", "backend.evaluate"],
        cwd=cwd,
        text=True,
        stderr=subprocess.STDOUT,
    )
    passed, failed, avg = _parse_summary(output)
    lats = _parse_latencies(output)
    return EvalRun(passed=passed, failed=failed, avg_latency_s=avg, per_test_latencies_s=lats, raw_output=output)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run backend.evaluate N times and aggregate metrics.")
    ap.add_argument("-n", "--runs", type=int, default=5, help="Number of evaluation runs (default: 5)")
    ap.add_argument("--cwd", default=".", help="Working directory where backend module is available (default: .)")
    args = ap.parse_args()

    runs: List[EvalRun] = []
    failures_agg: Dict[int, Dict[str, int]] = {}
    all_latencies: List[float] = []

    for _ in range(args.runs):
        r = run_once(args.cwd)
        runs.append(r)
        all_latencies.extend(r.per_test_latencies_s)
        f = _parse_failures(r.raw_output)
        for t, reasons in f.items():
            failures_agg.setdefault(t, {})
            for reason, count in reasons.items():
                failures_agg[t][reason] = failures_agg[t].get(reason, 0) + count

    pass_rates = [r.passed / 10.0 for r in runs]
    avg_latencies = [r.avg_latency_s for r in runs]

    result = {
        "runs": args.runs,
        "pass_rate_mean": statistics.mean(pass_rates),
        "pass_rate_min": min(pass_rates),
        "pass_rate_max": max(pass_rates),
        "avg_latency_mean_s": statistics.mean(avg_latencies),
        "avg_latency_std_s": statistics.pstdev(avg_latencies) if len(avg_latencies) > 1 else 0.0,
        "latency_p50_s": _quantile(all_latencies, 0.50),
        "latency_p95_s": _quantile(all_latencies, 0.95),
        "latency_p99_s": _quantile(all_latencies, 0.99),
        "latency_min_s": min(all_latencies) if all_latencies else None,
        "latency_max_s": max(all_latencies) if all_latencies else None,
        "failures_by_test": failures_agg,
    }

    # Print a compact, copy-pasteable text block (no JSON dependency).
    print("MULTI-RUN EVALUATION SUMMARY")
    print(f"Runs: {result['runs']}")
    print(f"Pass rate (mean): {result['pass_rate_mean']:.0%}  (min={result['pass_rate_min']:.0%}, max={result['pass_rate_max']:.0%})")
    print(f"Avg latency (mean ± std): {result['avg_latency_mean_s']:.2f}s ± {result['avg_latency_std_s']:.2f}s")
    print(
        "Latency quantiles (all tests across all runs): "
        f"p50={result['latency_p50_s']:.2f}s, p95={result['latency_p95_s']:.2f}s, p99={result['latency_p99_s']:.2f}s "
        f"(min={result['latency_min_s']:.2f}s, max={result['latency_max_s']:.2f}s)"
    )
    print("Failures by test number:")
    if not failures_agg:
        print("  (none)")
    else:
        for t in sorted(failures_agg.keys()):
            parts = [f"{reason} x{count}" for reason, count in sorted(failures_agg[t].items(), key=lambda kv: (-kv[1], kv[0]))]
            print(f"  Test {t}: " + ", ".join(parts))


if __name__ == "__main__":
    main()

