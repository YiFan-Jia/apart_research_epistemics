# Evaluation pipeline: how to run it, and decisions taken while building it

*Written 14 Nov 2026 by the build session, following `docs/10_build_spec.md`. Nothing has called a real model yet.*

## Setup on the laptop

Python is Anaconda's, at `C:\Users\jyf08\anaconda3\python.exe` (Python 3.14); it is not on PATH, so either use the full path or run from an Anaconda Prompt. The `anthropic` package (2.8.0) was installed into the Anaconda base environment for this build; the other requirements were already there. See `requirements.txt`.

Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`. The runner reads it from there and never prints it.

## Commands, in order

| Step | Command | Calls a model? |
| --- | --- | --- |
| Check a delivery | `python -m src.assets` | No |
| Build scripts | `python -m src.scripts` (or `--stage 1`) | No |
| Mock run, zero spend | `python -m src.runner run --run mock1 --stage pilot --models haiku sonnet --mock` | No |
| Smoke test, one real conversation | `python -m src.runner run --run smoke-haiku --stage pilot --models haiku --limit 1` then `python -m src.runner inspect --run smoke-haiku` | **Yes, ~$0.01** |
| Pilot | `python -m src.runner run --run pilot1 --stage pilot --models haiku` | **Yes** |
| Resume after a crash, sleep or kill | `python -m src.runner run --run pilot1` | Yes |
| Progress and spend | `python -m src.runner status --run pilot1` | No |
| Score | `python -m src.score --run pilot1` (add `--judge` to map unmatched diagnoses with Haiku) | Only with `--judge` |
| Tests | `python -m pytest` | No |

Each run lives in `results/<run>/`: `run.sqlite` (the store of record), `config.json` (frozen copy), `manifest.json`, `transcripts/<model>.jsonl`, and after scoring `extractions.jsonl`, `judge_cache.sqlite` and `scores/` (long table, conversation table, outcomes, contrasts, by-reply tables, the two figures, `summary.json`). Exit codes: 0 done, 1 some conversations left incomplete after retries (run again), 3 halted (fatal error or circuit breaker; the reason is printed), 4 spend cap reached, 5 refused (the reason is printed).

## Before the first real call

- [ ] Set `stated_location` in `config.json`. The script builder refuses to build scripts without it.
- [ ] Clinicians sign off the drafted noise bank, asks and system prompt (`scenarios/noise_bank.json`, `scenarios/prompts.json`), then set their status to `approved`.
- [ ] Set real spend caps in `config.json` (placeholders: $5 Haiku, $20 Sonnet), with headroom for the conversations in flight.
- [ ] Check the Console's rate limits and balance.
- [ ] Run the smoke test on each model and read `inspect`: no thinking blocks, text-only replies, cache reads from reply 2. The `between_tools` setting for Sonnet 5.5 comes from the 14 Nov docs reading and is accepted by the SDK, but only a real call shows it behaves as described.

## Decisions taken where the spec left room

| Topic | Decision |
| --- | --- |
| V00 fixture accepted names | Bare "heart failure" was dropped from the starting accepted names so the two sets are mutually exclusive, as spec 6.6 asks the clinicians to do |
| Level B wording | "urgent: assessment within 24 hours" (the spec's default); the four levels are in `config.json` |
| Stage membership | A vignette joins a stage only when all of its units for that stage are ready, so every stage stays fully crossed |
| Asset-change check | On resume the runner rebuilds the run's own scripts from the current files and refuses if any differs. Changes to assets the run does not use are ignored. A changed config, or switching between mock and real, is also refused |
| Repeat blocks | Models run side by side, each with its own pool; a repeat block starts on any model only after the earlier blocks have finished on every model (`sync_blocks_across_models`). A model stopped by its spend cap drops out of that gate |
| Reply status | `answered` or `malformed` depends on urgency alone (the primary field). Diagnosis and confidence validity are carried by their own source fields |
| Ambiguous diagnosis match | Not scored as correct or incorrect; it counts as missing for correctness, and is still used for identity (movement) |
| Uninterrupted retention | Among conversations that gave the post-update answer at some reply from the update on: never left it after first giving it |
| Missing as failure | Movement: a missing pair counts as a move. Uptake: a missing update reply counts as no uptake; adoption's denominator then includes conversations whose previous reply is missing |
| Extractor fallback | Not built, as the spec says, until the pilot shows more than about 1% of replies need it. Until then such fields are missing |
| Judge | Exact matches need no model. Other texts are `unjudged` unless `score --judge` is given; the judge is shown the vignette's canonical names so far |
| Primary contrast | The first row of `contrasts.csv`: direct minus non-direct noise on movement in the no-update control, within vignette, bootstrapped over vignettes |
| `scripts.jsonl` and `results/` | Gitignored. Each run freezes its scripts in its database, so the record of what ran is there. Copy each finished `results/<run>/` to a second place |

## What was verified, and what was not

Verified by the 62 tests in `tests/` (all passing) and by mock runs on the fixture: every item in spec section 7 except the last, which needs a real call per model. That covers: stage-by-stage building, 162 scripts per vignette and 3,240 for 20; one-factor differences; turn layout; no gold or later turn in any request; a killed process resumes with no duplicated or missing replies; duplicate replies are rejected; empty replies end the conversation; the spend cap; fatal errors stop the run; retries and the circuit breaker; every fixed test conversation scores exactly; the scorer recovers the mock's flip, uptake and baseline rates; per-field extraction, full-width characters and translated labels; Chinese and Japanese round trips; the validator on the fixture and broken copies; the real client's error mapping and response handling, with the network replaced.

Not verified: any real API behaviour (thinking off, cache reads, the actual reply format, refusal patterns), the judge prompt on real diagnosis text, and throughput under real rate limits. The pilot measures these.
