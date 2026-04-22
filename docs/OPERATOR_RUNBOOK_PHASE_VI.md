# Operator Runbook — Phase VI

Operational guide for running the SOST settlement alpha. This covers daily operations, troubleshooting, and emergency procedures.

## Daily Operations

### Check deal states

```bash
python3 scripts/operator_list_deals.py
```

Review the output for:
- Deals stuck in `AWAITING_ETH_LOCK` or `AWAITING_SOST_LOCK` for more than 1 hour
- Deals in `BOTH_LOCKED` awaiting operator settlement confirmation
- Any deals in `DISPUTED` state requiring manual intervention

### Monitor watchers

Both watchers should be polling continuously. Check their status:

```bash
# Dashboard health endpoint
curl http://localhost:8080/health

# Check watcher logs
tail -50 data/logs/eth-watcher.log
tail -50 data/logs/sost-watcher.log
```

Healthy watcher output shows periodic poll entries with block numbers advancing.

### Review audit log

```bash
# Full audit trail
python3 scripts/operator_show_audit.py

# Audit for a specific deal
python3 scripts/operator_show_audit.py --deal-id <deal_id>

# Raw audit file
cat data/audit/audit.jsonl | python3 -m json.tool --no-ensure-ascii
```

Look for:
- `unmatched_eth_deposit` events (deposits not correlated to any deal)
- Gaps in state transitions (e.g., a deal went from AWAITING_ETH_LOCK directly to EXPIRED without a lock event)
- Failed settlement attempts

## How to Inspect a Stuck Deal

A deal is "stuck" if it has been in a non-terminal state for longer than expected.

```bash
# 1. Get deal details
python3 scripts/operator_show_deal.py --deal-id <deal_id>

# 2. Check the deal's audit history
python3 scripts/operator_show_audit.py --deal-id <deal_id>

# 3. Check if ETH deposit exists on chain
cast call $ESCROW_ADDRESS "deposits(uint256)" $DEPOSIT_ID --rpc-url $SEPOLIA_RPC_URL

# 4. Check SOST balance at the maker address
curl -s -u $SOST_RPC_USER:$SOST_RPC_PASS \
  --data-binary '{"jsonrpc":"1.0","method":"getbalance","params":["'$MAKER_ADDR'"]}' \
  http://127.0.0.1:18232
```

Common causes:
- **ETH deposit not detected**: watcher was down when the deposit TX was mined. Restart the watcher; it will re-poll from the last known block.
- **SOST balance not confirmed**: SOST node was unreachable. Verify the node is running and RPC is accessible.
- **Deal expired before both locks**: check `expires_at` timestamp vs lock event timestamps. If the deal expired legitimately, proceed to refund.

## How to Trigger Manual Refund

When a deal is in `EXPIRED` or `REFUND_PENDING` state and has locked funds:

```bash
# 1. Verify deal state
python3 scripts/operator_show_deal.py --deal-id <deal_id>

# 2. For ETH-side refund:
# The depositor must call withdraw() on the escrow after the unlock time.
# Check unlock time:
cast call $ESCROW_ADDRESS "deposits(uint256)" $DEPOSIT_ID --rpc-url $SEPOLIA_RPC_URL

# If unlock time has passed, the depositor can withdraw:
cast send $ESCROW_ADDRESS "withdraw(uint256)" $DEPOSIT_ID \
  --rpc-url $SEPOLIA_RPC_URL --private-key $DEPOSITOR_KEY

# 3. For SOST-side refund:
# In alpha, SOST locks are balance-based. The operator confirms that the
# SOST side is free to move funds. No on-chain unlock transaction needed
# until Phase VII adds atomic SOST lock/unlock.
```

## How to Restart Watchers

If a watcher has stopped or is not responding:

```bash
# Check if the daemon process is running
ps aux | grep settlement_daemon
ps aux | grep dashboard_api

# Restart the full daemon (which starts both watchers)
# Kill existing process first
pkill -f settlement_daemon.py
python3 scripts/settlement_daemon.py &

# Or restart individual components via the dashboard
curl -X POST http://localhost:8080/admin/restart-eth-watcher
curl -X POST http://localhost:8080/admin/restart-sost-watcher
```

After restarting, verify watchers are polling:
```bash
# Wait 30 seconds, then check health
curl http://localhost:8080/health
```

The ETH watcher resumes from the last processed block number. The SOST watcher resumes from the last known block height. No events should be lost, but there may be a detection delay proportional to downtime.

## How to Check Dashboard Health

```bash
# Basic health check
curl -s http://localhost:8080/health | python3 -m json.tool

# Expected response:
# {
#   "status": "ok",
#   "eth_watcher": "polling",
#   "sost_watcher": "polling",
#   "active_deals": 0,
#   "last_eth_block": 19500000,
#   "last_sost_block": 5500
# }
```

If the dashboard is not responding:
```bash
# Check if port 8080 is in use
ss -tlnp | grep 8080

# Restart dashboard
pkill -f dashboard_api.py
python3 scripts/dashboard_api.py &
```

## Emergency Procedures

### Watcher producing incorrect events

1. Stop the daemon immediately: `pkill -f settlement_daemon`
2. Do NOT execute any pending settlements
3. Review the audit log for the last 30 minutes of events
4. Compare with on-chain data (use `cast` to query Sepolia, `curl` to query SOST RPC)
5. If events are incorrect, identify the root cause before restarting

### Deal settled incorrectly

1. This is the most critical failure mode in alpha
2. Record the deal_id, all audit entries, and on-chain state
3. Check if ETH escrow funds have been released (query the escrow contract)
4. Check if SOST transfer occurred (query SOST node)
5. If funds were transferred incorrectly, this requires manual intervention on both chains

### SOST node unreachable

1. Check if the node process is running on the host
2. If using SSH tunnel, verify the tunnel is active: `ssh -O check host`
3. Re-establish tunnel if needed: `ssh -L 18232:127.0.0.1:18232 host`
4. The SOST watcher will resume polling once connectivity is restored

### Sepolia RPC unavailable

1. Switch to an alternative RPC endpoint in the config:
   - `https://rpc.sepolia.org`
   - `https://1rpc.io/sepolia`
   - `https://sepolia.infura.io/v3/$PROJECT_ID`
2. Update `configs/live_alpha.local.json` with the new RPC URL
3. Restart the daemon

### All else fails

1. Stop the daemon
2. Export full audit log: `cp data/audit/audit.jsonl data/audit/audit_backup_$(date +%s).jsonl`
3. Save deal store state: `cp data/deals.json data/deals_backup_$(date +%s).json`
4. Do not delete any data
5. Review logs and on-chain state before restarting

## Contact and Escalation

| Role | Responsibility |
|------|---------------|
| Operator | Daily monitoring, settlement confirmation, refund triggering |
| Developer | Watcher bugs, daemon issues, contract questions |
| Security | Key management, RPC credential rotation, incident response |

Escalation path:
1. Operator detects issue via dashboard or CLI tools
2. If operational (watcher restart, config change): operator resolves directly
3. If software bug (incorrect state transitions, missed events): escalate to developer
4. If security concern (key compromise, unauthorized access): escalate to security immediately
