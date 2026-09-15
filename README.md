# TiltLock: Autonomous Trade Review & Self-Evolution System

> **Bitget AI Base Camp Hackathon S2**  
> **Track:** Track 3 · AI Trading Desk  
> **Named Sub-theme:** *Review & Self-Evolution* (500 USDT Theme Prize)  

TiltLock is a trade review and self-evolution system with a live enforcement layer for discretionary crypto and tokenized US stock (rToken) day traders on Bitget. It detects empirical behavioral tilt signatures, diagnoses cognitive pathology using Qwen-3.8, enforces a mechanical sub-account cooldown via real Bitget Agent Hub actions, and evolves a personal, persistent rule checklist that tightens after each incident.

---

## The 4-Stage Stack

```
1. DETECT    --> Empirical tilt signatures from live order fills & cancel telemetry
2. DIAGNOSE  --> Cognitive bias classification & sequence audit via Qwen-3.8
3. ENFORCE   --> Real Bitget Agent Hub actions on Agentic Sub-Account + local gate
4. EVOLVE    --> Human-in-the-loop gate updating persistent personal rule checklist
```

---

## Real Bitget Agent Hub Action Mapping

TiltLock interacts with Bitget accounts through authentic Agent Hub intent verbs and actions (no imaginary verbs or fake API revocation):

| Action | Real Agent Hub Surface | TiltLock Adapter Method | Behavior |
| :--- | :--- | :--- | :--- |
| **Cancel Open Orders** | `order --action cancelAll --confirm` | `client.cancel_all_orders()` | Cancels all active limit/market resting orders |
| **Cancel Trigger/SLs** | `strategy_order --action open` -> `strategy_order --action cancel --orderId <id> --confirm` | `client.cancel_strategy_orders()` | Queries open trigger/plan orders and purges them individually |
| **Reset Leverage** | `position --action setLeverage --symbol <sym> --leverage 1` | `client.set_leverage()` | Enforces 1x baseline leverage on tilted contract |
| **Close Positions** | `position --action close --symbol <sym> --confirm` | `client.close_position()` | Emergency flatten (optional, gated by `--aggressive`) |
| **Order Gateway Gate** | Pre-flight check before `order --action place` | `client.place_order()` | Intercepts order entries and raises `PERMISSION_DENIED_COOLDOWN_ACTIVE` if cooldown is active |

---

## Quickstart

### 1. Repository Setup
```powershell
# Navigate to repository root
cd C:\Projects\Tiltlock

# Set PYTHONPATH
$env:PYTHONPATH="src"
```

### 2. Run the Deterministic Demo (Zero-Network)
```powershell
# 90-second deterministic demo running in ~2s with exit code 0
python -m tiltlock.cli run --demo --yes

# With aggressive flatten enabled
python -m tiltlock.cli run --demo --yes --aggressive
```

### 3. Bitget Agent Hub CLI (`bgc`) Setup & Paper Mode

#### How to install & authenticate `bgc`:
1. Clone the Bitget Agent Hub repository:
   ```bash
   git clone https://github.com/BitgetLimited/agent_hub
   ```
2. Follow the setup guide:
   [https://www.bitget.careers/support/articles/12560603894122](https://www.bitget.careers/support/articles/12560603894122)
3. Authorize your paper trading session:
   ```bash
   bgc --paper-trading
   ```
4. Verify readiness probe:
   ```bash
   bgc discover --paper-trading
   ```

#### Mode differences:
- `python -m tiltlock.cli run --demo`: Zero-network recording demo using `MockBitgetClient`. Guaranteed deterministic, <60s, exit code 0.
- `python -m tiltlock.cli run --paper`: Live fill and order polling loop via `bgc` CLI on intervals configured in `config.yaml`. Requires authenticated `bgc` binary on PATH.
- `python -m tiltlock.cli run --paper --fixture`: Deterministic paper adapter test that replays telemetry sequences through `BgcCliBitgetClient` to verify live command construction without requiring an active market session.

> **Honest Dependency Notice:** If `bgc` is not installed on PATH or the paper session is unauthenticated, TiltLock fails probe immediately with exit code 1 and prints exact setup instructions. It never fakes successful live polling.

```powershell
# Run paper mode (fails honestly with exit 1 if bgc is missing)
python -m tiltlock.cli run --paper --yes

# Run paper mode fixture replay (useful for testing paper adapter)
python -m tiltlock.cli run --paper --fixture --yes
```

### 4. Check Account & Lock Status
```powershell
python -m tiltlock.cli status
```

### 5. Emergency Lock Reset
```powershell
python -m tiltlock.cli unlock
```

### 6. Run Full Unit Test Suite
```powershell
python -m unittest discover tests
```

---

## Submission Form Copy (Ready for Google Form)

### Target User & Product Value (Part 2 of Project Description)
> *Discretionary crypto and tokenized US stock (rToken) day traders operating with a $5,000 – $50,000 capital base on Bitget Agentic sub-accounts, executing ≥10 intraday trades. These traders possess working technical edge but suffer from known behavioral tilt: revenge trading, averaging down after stop-outs, and stop-loss tampering during rapid market moves. Existing trade journals only audit past failure; TiltLock pairs real-time diagnostic review with immediate sub-account cooldown enforcement and an evolving, adaptive rule checklist.*

### Role of the LLM (Standalone Form Field)
> *Qwen-3.8 (`qwen3.8-max`) serves as the cognitive diagnostics engine. Rather than relying on simple boolean alerts, the model analyzes the raw telemetry of fills, timing deltas, and market regime context to classify trader pathology (e.g. Sunk Cost Escalation, Revenge Re-entry), quantify session cost, determine psychological cooldown duration, and synthesize a concrete new rule proposal for the trader's evolving checklist.*

---

## Architecture

```
tiltlock/
├── config.yaml                     # Policy thresholds, cooldown boundaries, and polling intervals
├── pyproject.toml                  # Python package configuration
├── README.md                       # Documentation & Quickstart
├── fixtures/
│   └── tilt_sequence.json          # Deterministic 10-trade telemetry with tilt escalation
├── state/
│   ├── checklist.json              # Persistent evolving rules (v1: R01, R02 -> v2: +R03)
│   ├── lock_state.json             # Cooldown gate lockfile (timestamps, reason, cost)
│   └── proposed_rules.log          # Audit log of synthesized rules
├── src/tiltlock/
│   ├── __init__.py
│   ├── models.py                   # Pydantic models for fills, events, diagnoses, and rules
│   ├── config.py                   # Configuration loader with repo-root discovery
│   ├── detector.py                 # Deterministic heuristic tilt signature detector
│   ├── diagnostician.py            # Qwen-3.8 behavioral analysis engine with fallback
│   ├── enforcer.py                 # Shared order gateway & BgcCliBitgetClient adapter
│   ├── evolver.py                  # Human-in-the-loop rule synthesis & checklist evolver
│   ├── demo_runner.py              # Zero-network deterministic recording runner
│   ├── paper_runner.py             # Live polling loop & fixture replay paper runner
│   └── cli.py                      # CLI entrypoint (run, status, unlock)
└── tests/
    ├── test_detector.py            # Heuristic detection unit tests
    ├── test_diagnostician.py       # Diagnosis & fallback unit tests
    ├── test_enforcer.py            # Action mappings & gateway freeze unit tests
    ├── test_evolver.py             # Checklist mutation unit tests
    ├── test_demo.py                # Zero-network demo lifecycle unit test
    └── test_paper.py               # bgc probe, polling loop, and gateway unit tests
```
