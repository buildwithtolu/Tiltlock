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

## Try It Yourself

### Prerequisites
- Python 3.10+
- (Optional, paper mode only) Node.js 20+, Bitget Demo API key, and `bgc`

### Fast path: offline demo (no Bitget account needed)
```bash
git clone https://github.com/buildwithtolu/Tiltlock.git
cd Tiltlock
python -m pip install pydantic pyyaml rich requests
```

**Windows PowerShell**
```powershell
$env:PYTHONPATH="src"
python -m tiltlock.cli run --demo --yes
python -m tiltlock.cli status
python -m tiltlock.cli unlock
python -m unittest discover tests
```

**macOS / Linux**
```bash
export PYTHONPATH=src
python -m tiltlock.cli run --demo --yes
python -m tiltlock.cli status
python -m tiltlock.cli unlock
python -m unittest discover tests
```

This is the judge recording path: zero network, deterministic Detect → Diagnose → Enforce → Evolve.

Optional:
```bash
python -m tiltlock.cli run --demo --yes --aggressive
```

### Paper mode (optional, needs Bitget + `bgc`)
1. Install the Bitget Agent Hub CLI:
   ```bash
   npm install -g @bitget-ai/bitget-agent-cli
   bgc --version
   ```
2. Create a **Demo** API key on Bitget with:
   - Spot trading
   - Futures order
   - Futures holdings
   - Leave IP bind blank
   - No withdraw permission
3. Set credentials in your shell (do not commit these):

**Windows PowerShell**
```powershell
$env:BITGET_API_KEY="your_demo_api_key"
$env:BITGET_SECRET_KEY="your_demo_secret"
$env:BITGET_PASSPHRASE="your_passphrase"
$env:PYTHONPATH="src"
```

**macOS / Linux**
```bash
export BITGET_API_KEY="your_demo_api_key"
export BITGET_SECRET_KEY="your_demo_secret"
export BITGET_PASSPHRASE="your_passphrase"
export PYTHONPATH=src
```

4. Verify Bitget paper access:
   ```bash
   bgc discover --paper-trading
   ```
5. Run TiltLock paper paths:
   ```bash
   # Fixture replay through real bgc adapter
   python -m tiltlock.cli run --paper --fixture --yes

   # Live polling loop
   python -m tiltlock.cli run --paper --yes
   ```

#### Mode differences
- `--demo`: Zero-network recording demo using `MockBitgetClient`. Deterministic, <60s, exit 0.
- `--paper --fixture`: Replays fixtures through real `BgcCliBitgetClient` / `bgc --paper-trading`.
- `--paper`: Live fill/order polling via `bgc` using intervals in `config.yaml`.

If `bgc` is missing or unauthenticated, paper mode exits `1` with setup instructions. It never fakes success.

### Useful commands
```bash
python -m tiltlock.cli status
python -m tiltlock.cli unlock
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
