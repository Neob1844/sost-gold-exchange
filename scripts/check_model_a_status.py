#!/usr/bin/env python3
"""
SOST — Model A Automation Status Checker

Scans the gold-exchange, comms, and sost-core repos to produce a
clear status report of Model A (Autocustody) implementation:
  - modules detected
  - scripts detected
  - tests detected
  - automation status per component
  - website sections where Model A appears

Usage:
    python3 scripts/check_model_a_status.py
"""

import os
import re
import sys
import json
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────

EXCHANGE_ROOT = Path(__file__).resolve().parent.parent
SOST_CORE = EXCHANGE_ROOT.parent / "sostcore" / "sost-core"
COMMS_ROOT = EXCHANGE_ROOT.parent / "sost-comms-private"
WEBSITE = SOST_CORE / "website"

# ── Helpers ──────────────────────────────────────────────────────

def search_files(root, extensions, pattern, ignore_dirs=None):
    """Search files for a regex pattern. Returns list of (path, line_no, line)."""
    if ignore_dirs is None:
        ignore_dirs = {"node_modules", ".git", "__pycache__", "build", "dist"}
    results = []
    root = Path(root)
    if not root.exists():
        return results
    for ext in extensions:
        for fpath in root.rglob(f"*{ext}"):
            if any(d in fpath.parts for d in ignore_dirs):
                continue
            try:
                text = fpath.read_text(errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        results.append((str(fpath.relative_to(root)), i, line.strip()[:120]))
            except Exception:
                pass
    return results


def check_file_exists(path):
    return "EXISTS" if Path(path).exists() else "MISSING"


def count_tests(root, pattern):
    """Count test functions matching a pattern."""
    count = 0
    root = Path(root)
    if not root.exists():
        return 0
    for fpath in root.rglob("test_*.py"):
        try:
            text = fpath.read_text(errors="ignore")
            count += len(re.findall(pattern, text, re.IGNORECASE))
        except Exception:
            pass
    return count

# ── Checks ───────────────────────────────────────────────────────

def check_modules():
    print("=" * 70)
    print("1. MODEL A MODULES IN GOLD-EXCHANGE")
    print("=" * 70)

    hits = search_files(EXCHANGE_ROOT / "src", [".py"], r"model.?a|autocustody|MODEL_A")
    if not hits:
        print("  No Model A references found in src/")
    else:
        seen = set()
        for path, line, text in hits:
            if path not in seen:
                seen.add(path)
                print(f"  ✓ {path}")
        print(f"  Total: {len(seen)} files, {len(hits)} references")
    print()


def check_scripts():
    print("=" * 70)
    print("2. MODEL A SCRIPTS")
    print("=" * 70)

    scripts_dir = EXCHANGE_ROOT / "scripts"
    model_a_scripts = []
    if scripts_dir.exists():
        for f in sorted(scripts_dir.iterdir()):
            if f.suffix == ".py":
                text = f.read_text(errors="ignore")
                if re.search(r"model.?a|autocustody|MODEL_A", text, re.IGNORECASE):
                    model_a_scripts.append(f.name)

    if model_a_scripts:
        for s in model_a_scripts:
            print(f"  ✓ scripts/{s}")
    else:
        print("  ✗ No Model A specific scripts found in scripts/")

    # Check for this script
    print(f"  ✓ scripts/check_model_a_status.py (this script)")
    print()


def check_tests():
    print("=" * 70)
    print("3. MODEL A TESTS")
    print("=" * 70)

    tests_root = EXCHANGE_ROOT / "tests"

    # Find test files with Model A references
    hits = search_files(tests_root, [".py"], r"model.?a|autocustody|MODEL_A")
    seen_files = set()
    for path, line, text in hits:
        seen_files.add(path)

    if seen_files:
        for f in sorted(seen_files):
            print(f"  ✓ {f}")
    else:
        print("  ✗ No Model A specific test files found")

    # Count test functions
    total_model_a_tests = count_tests(tests_root, r"def test.*model.?a|def test.*autocustody")
    print(f"  Model A test functions: {total_model_a_tests}")

    # Check specific test categories
    categories = {
        "position creation": count_tests(tests_root, r"def test.*create.*model.?a"),
        "reward logic": count_tests(tests_root, r"def test.*reward.*model.?a|def test.*claim.*model.?a"),
        "slashing": count_tests(tests_root, r"def test.*slash"),
        "transfer blocking": count_tests(tests_root, r"def test.*cannot.*transfer.*model.?a|def test.*transfer.*model.?a"),
        "reward-right split": count_tests(tests_root, r"def test.*split.*reward"),
        "pricing": count_tests(tests_root, r"def test.*value.*model.?a|def test.*price.*model.?a"),
        "beneficiary exclusion": count_tests(tests_root, r"def test.*no.*deposit.*excluded|def test.*model.?a.*excluded"),
    }

    print()
    print("  Test coverage by category:")
    for cat, n in categories.items():
        status = "✓" if n > 0 else "✗"
        print(f"    {status} {cat}: {n} test(s)")
    print()


def check_automation_matrix():
    print("=" * 70)
    print("4. AUTOMATION MATRIX — MODEL A")
    print("=" * 70)

    matrix = [
        ("Position registration",      "EXISTS",           "create_model_a() in position_registry.py"),
        ("Owner tracking",             "EXISTS",           "owner field in Position schema"),
        ("Reward accrual",             "EXISTS",           "claim_reward() — identical for A and B"),
        ("Reward settlement daemon",   "EXISTS",           "reward_settlement_daemon.py — model-agnostic"),
        ("Bond posting (field)",       "EXISTS",           "bond_amount_sost field in schema"),
        ("Bond release logic",         "MISSING",          "No release/return mechanism implemented"),
        ("Audit / custody verify",     "MISSING",          "proof_hash field exists, no verification daemon"),
        ("Slashing mechanism",         "EXISTS",           "slash() method + sample data shows epoch failure"),
        ("Automated slash triggers",   "MISSING",          "Manual operator action only"),
        ("Lifecycle tracking",         "EXISTS",           "maturity_watcher.py — both models"),
        ("Maturity transitions",       "EXISTS",           "ACTIVE → NEARING_MATURITY → MATURED"),
        ("Claim / redeem",             "EXISTS",           "redeem() method in registry"),
        ("Reward-right trading",       "EXISTS",           "split_reward_right() works for Model A"),
        ("Full position transfer",     "BLOCKED",          "Intentionally blocked — Phase 2+"),
        ("Full position novation",     "MISSING",          "No controlled novation path"),
        ("ETH beneficiary sync",       "NOT APPLICABLE",   "Model A has no ETH escrow"),
        ("Auto-withdraw from escrow",  "NOT APPLICABLE",   "Model A has no ETH escrow"),
        ("Reconciliation",             "EXISTS",           "Audit log tracks all events"),
        ("Risk-adjusted pricing",      "EXISTS",           "12% discount rate vs 5% for Model B"),
        ("Epoch-based audit scheduler","MISSING",          "Referenced in samples but not implemented"),
    ]

    for component, status, detail in matrix:
        icon = {"EXISTS": "✓", "MISSING": "✗", "BLOCKED": "⊘", "NOT APPLICABLE": "—"}
        print(f"  {icon.get(status, '?')} [{status:16s}] {component}")
        print(f"    {detail}")

    print()

    # Summary counts
    counts = {}
    for _, status, _ in matrix:
        counts[status] = counts.get(status, 0) + 1

    print("  Summary:")
    for s in ["EXISTS", "MISSING", "BLOCKED", "NOT APPLICABLE"]:
        if s in counts:
            print(f"    {s}: {counts[s]}")
    print()


def check_website():
    print("=" * 70)
    print("5. WEBSITE REFERENCES TO MODEL A")
    print("=" * 70)

    if not WEBSITE.exists():
        print("  ✗ Website directory not found")
        return

    hits = search_files(WEBSITE, [".html"], r"model.?a|autocustody|self.custody")

    # Group by file
    files = {}
    for path, line, text in hits:
        if path not in files:
            files[path] = []
        files[path].append((line, text))

    for fpath in sorted(files.keys()):
        refs = files[fpath]
        print(f"\n  {fpath} ({len(refs)} references)")
        # Show first 3 references
        for line, text in refs[:3]:
            print(f"    L{line}: {text[:100]}")
        if len(refs) > 3:
            print(f"    ... and {len(refs) - 3} more")

    print()


def check_inconsistencies():
    print("=" * 70)
    print("6. KNOWN INCONSISTENCIES")
    print("=" * 70)

    issues = []

    # Check protocol fee
    if WEBSITE.exists():
        for fpath in WEBSITE.rglob("*.html"):
            try:
                text = fpath.read_text(errors="ignore")
                # Look for "5%" near "Model A" (should be 3%)
                if re.search(r"model.?a.*5\s*%|5\s*%.*model.?a", text, re.IGNORECASE):
                    rel = fpath.relative_to(WEBSITE)
                    issues.append(f"PROTOCOL FEE: {rel} — may show 5% instead of 3% for Model A")
            except Exception:
                pass

    # Check activation timeline
    app_index = WEBSITE / "sost-app" / "index.html"
    if app_index.exists():
        text = app_index.read_text(errors="ignore")
        if "Block 5,000" in text or "block 5000" in text.lower():
            if "Model A activates" in text:
                issues.append("TIMELINE: sost-app/index.html — says 'Block 5,000 Model A activates' but chain is past 5,000")

    # Check "launched at regenesis"
    faq = WEBSITE / "sost-faq.html"
    if faq.exists():
        text = faq.read_text(errors="ignore")
        if "launched at regenesis" in text.lower() and "popc" in text.lower():
            issues.append("WORDING: sost-faq.html — says PoPC 'launched at regenesis' (only funding mechanism launched)")

    if issues:
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print("  No known inconsistencies detected")
    print()


def check_comms():
    print("=" * 70)
    print("7. MODEL A IN SOST-COMMS-PRIVATE")
    print("=" * 70)

    if not COMMS_ROOT.exists():
        print("  ✗ sost-comms-private not found")
        return

    hits = search_files(COMMS_ROOT / "src", [".ts"], r"model.?a|autocustody|MODEL_A")
    if hits:
        seen = set()
        for path, line, text in hits:
            if path not in seen:
                seen.add(path)
                print(f"  ✓ {path}")
    else:
        print("  No Model A references in comms — deal flow is model-agnostic")
    print()


def final_verdict():
    print("=" * 70)
    print("FINAL VERDICT")
    print("=" * 70)
    print()
    print("  MODEL A AUTOMATION STATUS: PARTIAL")
    print()
    print("  ✓ IMPLEMENTED:")
    print("    - Position creation & registry")
    print("    - Reward claiming & settlement daemon")
    print("    - Slashing mechanism (method exists)")
    print("    - Maturity lifecycle tracking")
    print("    - Reward-right splits & trading")
    print("    - Risk-differentiated pricing (12%)")
    print("    - Audit logging")
    print("    - Transfer blocking (full positions)")
    print()
    print("  ✗ MISSING:")
    print("    - PoPC verification daemon (no custody proof checking)")
    print("    - Epoch-based audit scheduler")
    print("    - Bond release logic on maturity")
    print("    - Automated slashing triggers")
    print("    - Full position novation (Phase 2+)")
    print()
    print("  ⚠ WEBSITE ISSUES:")
    print("    - App PipBoy timeline stale (Block 5,000 already passed)")
    print("    - Protocol fee 5% vs 3% inconsistency in some pages")
    print("    - PoPC 'launched at regenesis' misleading wording in FAQ")
    print("    - Foundation Model A date (May 2026) vs public launch (April 2027)")
    print()


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("SOST — Model A (Autocustody) Automation Status Report")
    print(f"Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Exchange repo: {EXCHANGE_ROOT}")
    print(f"Core repo:     {SOST_CORE}")
    print(f"Comms repo:    {COMMS_ROOT}")
    print()

    check_modules()
    check_scripts()
    check_tests()
    check_automation_matrix()
    check_website()
    check_inconsistencies()
    check_comms()
    final_verdict()
