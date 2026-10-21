"""Human-readable number formatting shared by run_all.py and the README conventions."""


def inr(value: float) -> str:
    """Format an amount as 'INR 2,998,668.80' (comma thousands, two decimals; never a currency symbol)."""
    return f"INR {float(value):,.2f}"


def part_summary(part: str, report: dict) -> str:
    """One-line result summary of a part's report, printed by run_all.py."""
    if part == "A":
        o = report["orders_clean"]
        return (f"Part A: {o['rows']:,} clean orders ({o['completed']:,} completed), "
                f"completed revenue {inr(o['completed_revenue_inr'])}, SQL Q1-Q7 run")
    if part == "B":
        seg, lapse = report["segments"], report["lapse"]
        best = lapse["test"][lapse["selected_model"]]
        return (f"Part B: {seg['rfm']['customers']:,} customers in K={seg['chosen_k']} segments, "
                f"lapse rate {lapse['cohort']['lapsed_pct']}%, {lapse['selected_model']} test F1 {best['f1']:.3f}")
    if part == "C":
        final = report["final"]
        return (f"Part C: {report['tickets']} tickets triaged, zero-shot {report['zero_shot']['accuracy_pct']}% vs "
                f"few-shot {report['few_shot']['accuracy_pct']}%, {final['route_counts'].get('human_review', 0)} "
                f"sent to human review")
    if part == "D":
        passed = sum(s["status"].startswith(s["expected_outcome"]) for s in report["scenarios"])
        resume = report["demos"]["crash_resume"]
        return (f"Part D: {report['chunks']['total']} policy chunks, {passed}/{len(report['scenarios'])} agent "
                f"scenarios as expected, crash+resume {resume['status']} {inr(resume['refund_inr'])}")
    raise ValueError(f"unknown part {part}")
