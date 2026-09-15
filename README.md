# TiltLock

Stop revenge trading before it blows the account.

TiltLock watches your Bitget trading activity for tilt patterns (fast re-entries after losses, size escalation, stop-loss cancellation), pauses the account, explains what went wrong, and adds a concrete rule to your personal checklist.

Built for Bitget Agent Hub / Agentic sub-accounts.

## What it does

1. **Detect** revenge-trading signals from fills and cancels  
2. **Review** the sequence and name the behavioral pattern  
3. **Enforce** cooldown: cancel orders, drop leverage to 1x, block new entries  
4. **Evolve** your checklist with one new rule you accept or reject  

## Try it in 60 seconds (no Bitget account)

```bash
git clone https://github.com/buildwithtolu/Tiltlock.git
cd Tiltlock
python -m pip install -e .
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="src"
python -m tiltlock.cli run --demo --yes
python -m tiltlock.cli status
python -m tiltlock.cli unlock
```

macOS / Linux:

```bash
export PYTHONPATH=src
python -m tiltlock.cli run --demo --yes
python -m tiltlock.cli status
python -m tiltlock.cli unlock
```

You should see a demo loss streak, a review, a cooldown lock, a blocked re-entry, and a new checklist rule.

## Paper mode (optional)

Needs Node.js 20+, `bgc`, and a Bitget **Demo** API key.

```bash
npm install -g @bitget-ai/bitget-agent-cli
```

Create a Demo key with:
- Spot trading
- Futures order
- Futures holdings
- No withdraw
- Leave IP bind blank

Set credentials in your shell (never commit them):

```powershell
$env:BITGET_API_KEY="..."
$env:BITGET_SECRET_KEY="..."
$env:BITGET_PASSPHRASE="..."
$env:PYTHONPATH="src"
```

```bash
bgc discover --paper-trading
python -m tiltlock.cli run --paper --fixture --yes
python -m tiltlock.cli run --paper --yes
```

| Mode | What it is |
|------|------------|
| `--demo` | Offline scenario. No network. Best first run. |
| `--paper --fixture` | Same scenario, but enforcement goes through real `bgc --paper-trading`. |
| `--paper` | Watches live Demo Trading fills until a tilt pattern appears. |

If `bgc` is missing or auth fails, paper mode exits with setup help. It does not pretend to succeed.

## Commands

```bash
python -m tiltlock.cli run --demo --yes
python -m tiltlock.cli run --demo --yes --aggressive
python -m tiltlock.cli run --paper --fixture --yes
python -m tiltlock.cli run --paper --yes
python -m tiltlock.cli status
python -m tiltlock.cli unlock
python -m unittest discover tests
```

`--aggressive` also flattens open positions when locking.

## Bitget actions used

| Protection | Agent Hub call |
|------------|----------------|
| Cancel open orders | `order --action cancelAll --confirm` |
| Cancel stops/triggers | `strategy_order --action open`, then cancel by id |
| Reduce leverage | `position --action setLeverage --leverage 1` |
| Flatten (optional) | `position --action close --confirm` |
| Block new entries | Local cooldown gateway before `order --action place` |

## Project layout

```text
tiltlock/
├── config.yaml
├── fixtures/tilt_sequence.json
├── src/tiltlock/
│   ├── detector.py
│   ├── diagnostician.py
│   ├── enforcer.py
│   ├── evolver.py
│   ├── demo_runner.py
│   ├── paper_runner.py
│   └── cli.py
└── tests/
```

## License

MIT
