# Phase XV --- Backend Export Tools, Fee Documentation, and Alpha Policy

Phase XV adds the backend export pipeline for deals and alpha status, documents the fee structure and trading flows, and establishes the limited alpha UI policy.

---

## What Was Added

### Export Scripts
- **scripts/export_deals_live_json.py** -- Exports all deals from `data/deals.json` to web API format (`deals_live.json`). Formats each deal with ID, type, status, maker/taker, amounts, and timestamps.
- **scripts/export_alpha_status_json.py** -- Comprehensive alpha status export. Reads positions, deals, and config to produce `alpha_live_status.json` with mode, counts, gold locked, test counts, and e2e status.
- **scripts/export_otc_requests_json.py** -- OTC request export (placeholder). Reads from `data/otc_requests.json` if present; defaults to empty with "coming soon" note.

### Systemd Services
- **ops/systemd/sost-alpha-deals-export.service + .timer** -- Exports deals every 5 minutes
- **ops/systemd/sost-alpha-status-export.service + .timer** -- Exports alpha status every 5 minutes

### Documentation
- **docs/ALPHA_FEES.md** -- Fee structure: 1% position trades, 1% reward-right trades, 0.01 SOST minimum, OTC disclosed per trade
- **docs/POSITION_DESK_FLOW.md** -- Step-by-step position desk flow for both full position and reward-right trades
- **docs/OTC_ALPHA_FLOW.md** -- OTC flow: Request, Quote, Confirm, Execute with fee disclosure
- **docs/LIMITED_ALPHA_UI_POLICY.md** -- Alpha restrictions: allowlisted participants, max concurrent deals, max position sizes, operator approval, disclaimers

### Tests
- **tests/integration/test_deals_export.py** -- 4 integration tests for the deals export pipeline

---

## Export Pipeline

The export scripts follow the same pattern as the existing `export_positions_json.py`:
- Load data from JSON files in `data/`
- Format into web API structure with generated timestamps and aggregates
- Write atomically via temp file to configurable output path
- Default to stdout for piping and debugging

### Enable the timers

```bash
sudo cp ops/systemd/sost-alpha-deals-export.* /etc/systemd/system/
sudo cp ops/systemd/sost-alpha-status-export.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sost-alpha-deals-export.timer
sudo systemctl enable --now sost-alpha-status-export.timer
```

### Manual export

```bash
python3 scripts/export_deals_live_json.py --output /opt/sost/website/api/deals_live.json
python3 scripts/export_alpha_status_json.py --output /opt/sost/website/api/alpha_live_status.json
python3 scripts/export_otc_requests_json.py --output /opt/sost/website/api/otc_requests.json
```

---

## Fee Summary

| Trade Type | Fee | Paid By |
|------------|-----|---------|
| Full position trade | 1% of trade value | Seller |
| Reward-right trade | 1% of reward value | Seller |
| OTC execution | Disclosed per trade | Per agreement |
| Viewing / creating / cancelling | Free | -- |

Minimum fee: 0.01 SOST per trade. No hidden spreads. No yield promises.

---

## Alpha Restrictions

- Allowlisted participants only (operator approval required)
- Max 3 concurrent deals per participant
- Deal expiry: 1 hour if not fully locked
- All settlements operator-assisted
- Testnet gold tokens only (Sepolia MockERC20)

---

## Test Commands

```bash
# Run deal export tests
python3 -m pytest tests/integration/test_deals_export.py -v

# Run all integration tests
python3 -m pytest tests/integration/ -q

# Run full test suite
python3 -m pytest tests/ -q
```

---

## What Follows

- OTC request submission interface
- Automated fee collection on settlement
- Multi-operator consensus for settlements
- Public alpha with broader participant access
- Mainnet gold token integration
