#!/usr/bin/env python3
"""
SOST Gold Exchange — Verify Mainnet Prerequisites

Pre-flight check script for Model B mainnet operations.
Checks all prerequisites and returns exit code 0 only if ALL pass.

Usage:
  python3 scripts/verify_mainnet_prereqs.py
  python3 scripts/verify_mainnet_prereqs.py --config configs/mainnet_model_b.example.json
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── ANSI colors ──
R = "\033[91m"
G = "\033[92m"
C = "\033[96m"
Y = "\033[93m"
O = "\033[38;5;208m"
W = "\033[97m"
D = "\033[90m"
B = "\033[1m"
X = "\033[0m"

PASS = f"{G}PASS{X}"
FAIL = f"{R}FAIL{X}"
WARN = f"{Y}WARN{X}"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_config_exists(config_path):
    """Check that the config file exists and is valid JSON."""
    if not os.path.exists(config_path):
        return False, f"Config file not found: {config_path}"
    try:
        with open(config_path) as f:
            json.load(f)
        return True, "Config loaded"
    except (json.JSONDecodeError, IOError) as e:
        return False, f"Invalid config: {e}"


def check_ethereum_rpc(rpc_url):
    """Check that Ethereum RPC is reachable."""
    if "YOUR_KEY" in rpc_url:
        return False, "RPC URL contains placeholder YOUR_KEY"
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_chainId",
        "params": [],
        "id": 1,
    }).encode()
    try:
        req = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            chain_id = int(data.get("result", "0x0"), 16)
            return True, f"Chain ID: {chain_id}"
    except Exception as e:
        return False, f"RPC unreachable: {e}"


def check_escrow_deployed(rpc_url, escrow_address):
    """Check that the escrow contract has code deployed."""
    if "TBD" in escrow_address or escrow_address == "0x":
        return False, "Escrow address is placeholder"
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "eth_getCode",
        "params": [escrow_address, "latest"],
        "id": 1,
    }).encode()
    try:
        req = urllib.request.Request(
            rpc_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            code = data.get("result", "0x")
            if code == "0x" or code == "0x0":
                return False, "No code at escrow address"
            return True, f"Contract deployed ({len(code) // 2 - 1} bytes)"
    except Exception as e:
        return False, f"Could not check escrow: {e}"


def check_position_registry(data_dir):
    """Check that the position registry is accessible."""
    registry_path = os.path.join(data_dir, "positions.json")
    data_exists = os.path.isdir(data_dir)
    if not data_exists:
        # Try to create it
        try:
            os.makedirs(data_dir, exist_ok=True)
            return True, f"Data dir created: {data_dir}"
        except OSError as e:
            return False, f"Cannot create data dir: {e}"
    if os.path.exists(registry_path):
        try:
            with open(registry_path) as f:
                json.load(f)
            return True, "Registry exists and is valid JSON"
        except (json.JSONDecodeError, IOError) as e:
            return False, f"Registry corrupt: {e}"
    return True, "Data dir exists, registry will be created on first use"


def check_audit_log(data_dir):
    """Check that the audit log directory is writable."""
    audit_dir = os.path.join(data_dir, "audit")
    try:
        os.makedirs(audit_dir, exist_ok=True)
        test_file = os.path.join(audit_dir, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True, f"Audit dir writable: {audit_dir}"
    except OSError as e:
        return False, f"Audit dir not writable: {e}"


def check_sost_node():
    """Check that the SOST node is reachable (basic localhost RPC check)."""
    payload = json.dumps({
        "jsonrpc": "1.0",
        "method": "getblockchaininfo",
        "params": [],
        "id": 1,
    }).encode()
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8332/",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Basic c29zdDpzb3N0",  # sost:sost default
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            if "result" in data:
                info = data["result"]
                blocks = info.get("blocks", "?")
                return True, f"SOST node synced, height={blocks}"
            return False, "Unexpected RPC response"
    except urllib.error.URLError:
        return False, "SOST node not reachable at 127.0.0.1:8332"
    except Exception as e:
        return False, f"SOST RPC error: {e}"


def check_sepolia_lifecycle(data_dir):
    """Check that position registry has at least 1 completed Sepolia lifecycle."""
    registry_path = os.path.join(data_dir, "positions.json")
    if not os.path.exists(registry_path):
        return False, "No positions.json found — no lifecycle completed"
    try:
        with open(registry_path) as f:
            data = json.load(f)
        positions = data if isinstance(data, list) else data.get("positions", [])
        redeemed = [p for p in positions if p.get("status") in ("REDEEMED", "redeemed")]
        if len(redeemed) == 0:
            return False, f"0 REDEEMED positions found ({len(positions)} total)"
        return True, f"{len(redeemed)} completed lifecycle(s) in registry"
    except (json.JSONDecodeError, IOError, KeyError) as e:
        return False, f"Cannot parse registry: {e}"


def check_tests_passing():
    """Check that Python test suite passes."""
    test_dir = os.path.join(PROJECT_ROOT, "tests")
    if not os.path.isdir(test_dir):
        return False, "tests/ directory not found"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_dir, "-q", "--tb=no"],
            capture_output=True, text=True, timeout=120,
            cwd=PROJECT_ROOT,
        )
        # Extract summary line (e.g. "26 passed")
        last_lines = result.stdout.strip().split("\n")[-2:]
        summary = " | ".join(ln.strip() for ln in last_lines if ln.strip())
        if result.returncode == 0:
            return True, f"All tests passed: {summary}"
        return False, f"Tests failed (exit {result.returncode}): {summary}"
    except subprocess.TimeoutExpired:
        return False, "Test suite timed out (>120s)"
    except FileNotFoundError:
        return False, "pytest not found — install with: pip install pytest"


def check_mainnet_config_exists():
    """Check that configs/mainnet_model_b.example.json exists."""
    config_path = os.path.join(PROJECT_ROOT, "configs", "mainnet_model_b.example.json")
    if os.path.exists(config_path):
        return True, f"Found: {config_path}"
    return False, "configs/mainnet_model_b.example.json not found"


def check_go_no_go_document():
    """Check that the Go/No-Go decision document exists."""
    doc_path = os.path.join(PROJECT_ROOT, "docs", "GO_NO_GO_MODEL_B_MAINNET.md")
    if os.path.exists(doc_path):
        return True, f"Found: {doc_path}"
    return False, "docs/GO_NO_GO_MODEL_B_MAINNET.md not found"


def main():
    parser = argparse.ArgumentParser(description="SOST — Verify Mainnet Prerequisites")
    parser.add_argument("--config",
                        default=os.path.join(PROJECT_ROOT, "configs", "mainnet_model_b.example.json"),
                        help="Path to mainnet config")
    args = parser.parse_args()

    print(f"\n{O}{B}  SOST GOLD EXCHANGE — MAINNET PRE-FLIGHT CHECK{X}\n")

    all_pass = True
    results = []
    not_ready_reasons = []

    # 1. Config
    ok, msg = check_config_exists(args.config)
    results.append(("Config file", ok, msg))

    config = {}
    if ok:
        with open(args.config) as f:
            config = json.load(f)

    eth = config.get("ethereum", {})
    rpc_url = eth.get("rpc_url", "")

    # 2. Ethereum RPC
    ok, msg = check_ethereum_rpc(rpc_url)
    results.append(("Ethereum RPC", ok, msg))

    # 3. Escrow contract
    escrow_addr = eth.get("escrow_address", "0x")
    ok, msg = check_escrow_deployed(rpc_url, escrow_addr)
    results.append(("Escrow contract", ok, msg))

    # 4. SOST node
    ok, msg = check_sost_node()
    results.append(("SOST node", ok, msg))

    # 5. Position registry
    data_dir = os.path.join(PROJECT_ROOT, "data")
    ok, msg = check_position_registry(data_dir)
    results.append(("Position registry", ok, msg))

    # 6. Audit log
    ok, msg = check_audit_log(data_dir)
    results.append(("Audit log", ok, msg))

    # 7. Sepolia lifecycle completion
    ok, msg = check_sepolia_lifecycle(data_dir)
    results.append(("Sepolia lifecycle", ok, msg))

    # 8. Test suites
    ok, msg = check_tests_passing()
    results.append(("Test suites", ok, msg))

    # 9. Mainnet config template
    ok, msg = check_mainnet_config_exists()
    results.append(("Mainnet config", ok, msg))

    # 10. Go/No-Go document
    ok, msg = check_go_no_go_document()
    results.append(("Go/No-Go doc", ok, msg))

    # Print results
    print(f"  {C}{'Check':<22s}{'Result':<8s}{'Details'}{X}")
    print(f"  {D}{'-' * 70}{X}")
    for name, ok, msg in results:
        status = PASS if ok else FAIL
        if not ok:
            all_pass = False
            not_ready_reasons.append(f"{name}: {msg}")
        print(f"  {status}  {W}{name:20s}{X}  {D}{msg}{X}")

    print()
    if all_pass:
        print(f"  {G}{B}READY{X} — all {len(results)} checks passed, ready for mainnet operations\n")
        sys.exit(0)
    else:
        passed = sum(1 for _, ok, _ in results if ok)
        failed = sum(1 for _, ok, _ in results if not ok)
        print(f"  {R}{B}NOT READY{X} — {passed} passed, {failed} failed\n")
        print(f"  {Y}Reasons:{X}")
        for reason in not_ready_reasons:
            print(f"    {R}-{X} {reason}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
