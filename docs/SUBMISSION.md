# Submission packet (Track 3 · Review & Self-Evolution)

Paste these into the Bitget Google Form. GitHub cannot replace the form fields.

## 1. Thesis

Revenge trading, not a missing indicator, is what blows many discretionary Bitget accounts. Journals only explain the damage after the fact. TiltLock watches fills and cancels for tilt signatures (fast re-entry after a stop, size escalation, stop-loss cancellation), writes a session review, pauses new entries, and asks the trader to accept one new personal rule. The human still decides whether that rule becomes policy.

## 2. Target user and product value

Discretionary crypto and tokenized US stock (rToken) day traders on Bitget Agentic sub-accounts, roughly $5,000–$50,000, 10+ intraday trades, who already have a setup but repeatedly break stops and size up after red trades. Not “all traders.” Value: a review plus a hard cooling-off gate, instead of a post-hoc journal.

## 3. Validation data and key metrics

Observed (this repo):
- `python -m tiltlock.cli run --demo --yes` completes offline with Detect → Review → Enforce → Evolve.
- Unit tests: `python -m unittest discover tests`.
- Paper path: `bgc --paper-trading` adapter was run against Bitget Demo Trading on a developer machine.

Estimated / targeted (label as targets, not observed users):
- Aim: 50 discretionary Bitget users try `--demo` in month one.
- Aim: 10 Demo-trading users complete one paper lock cycle.

No live Sharpe/AUM is claimed. This is a risk tool, not a strategy.

## 4. Progress

Built: detector, trigger-based review, local cooldown gateway, checklist evolver, `bgc` paper adapter, fail-open `bitget-signal` sentiment snapshot, `tiltlock ask`.
Not built: hosted web UI, production live trading, full 5-skill research desk.
Next: optional live Qwen when a key is present (`--live-llm`).

## 5. Deliverables

- GitHub: https://github.com/buildwithtolu/Tiltlock
- Demo command: `python -m tiltlock.cli run --demo --yes`
- Optional paper proof: `python -m tiltlock.cli run --paper --fixture --yes`
- NL: `python -m tiltlock.cli ask "why did I get locked?"`
- Screen recording: attach URL here after you record the demo

## 6. Role of the LLM (standalone form field)

Default `--demo` does **not** call a remote model. The review is generated from the session’s own fills, size ratio, stop-tamper flag, and optional `bitget-signal` Fear & Greed snapshot.

`--live-llm` calls Qwen (`qwen3.8-max` at the hackathon endpoint) only when `BITGET_QWEN_API_KEY` or `QWEN_API_KEY` is set. If the call fails, TiltLock uses the same local review. Do not describe the default demo as a live Qwen run.

## X post (draft)

Record the demo first, then post:

TiltLock is a Bitget Agent Hub cooldown for revenge trading.

It detects fast re-entry, size-up, and stop cancellation, reviews the session, blocks new orders, and adds a personal rule you accept.

Clone: https://github.com/buildwithtolu/Tiltlock
Run: python -m tiltlock.cli run --demo --yes

#BitgetHackathon @Bitget_AI

Quote: https://x.com/Bitget_AI/status/2100519318824055159

## Judge recording script (90s)

1. `python -m tiltlock.cli run --demo --yes`
2. Point at Detect signatures, Review (session numbers + bitget-signal line or unavailable), Enforce lock, blocked order, R03.
3. Optional 20s: `python -m tiltlock.cli run --paper --fixture --yes`
4. Optional: `python -m tiltlock.cli ask "why did I get locked?"`
