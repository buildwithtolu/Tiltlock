# Bitget AI Hackathon S2 notes

Track: AI Trading Desk (Track 3)  
Sub-theme: Review & Self-Evolution

## Target user & product value

Discretionary crypto and tokenized US stock (rToken) day traders on Bitget Agentic sub-accounts, typically $5,000-$50,000, running 10+ intraday trades. They often have a workable technical edge but lose money to revenge trading, size escalation after losses, and stop-loss cancellation. Journals only explain the damage after the fact. TiltLock detects the pattern in real time, pauses the account, and updates a personal rule checklist.

## Role of the LLM

Qwen (`qwen3.8-max`) is the trade-review engine. It reads fills, timing, size changes, and checklist context, then names the behavioral pattern, estimates session cost, recommends cooldown length, and proposes one concrete rule update. Offline `--demo` uses a fixed high-quality review so recordings stay reliable. Paper/live calls Qwen when configured and falls back to a deterministic review if the model is unavailable.
