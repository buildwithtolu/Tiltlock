# Bitget AI Hackathon S2 notes

Track: AI Trading Desk (Track 3)  
Sub-theme: Review & Self-Evolution

## Target user & product value

Discretionary crypto and tokenized US stock (rToken) day traders on Bitget Agentic sub-accounts, typically $5,000-$50,000, running 10+ intraday trades. They often have a workable technical edge but lose money to revenge trading, size escalation after losses, and stop-loss cancellation. Journals only explain the damage after the fact. TiltLock detects the pattern in real time, pauses the account, and updates a personal rule checklist.

## Role of the LLM

Default `--demo` builds the review from the session’s own telemetry. It may attach a fail-open `bitget-signal` Fear & Greed snapshot. `--live-llm` calls Qwen only when an API key is set; otherwise the local review is used. Live production trading is disabled. See `docs/SUBMISSION.md` for form wording.
