# Apart AI x Epistemics sprint (13–15 Nov 2026)

**Status (Sat 14 Nov, later): the working direction is "Triage under sustained pushback" (`docs/07_triage_under_pushback.md`).** The design is still exploratory: fourteen factors are listed and none has been cut, sizes are not set, and nothing has been run yet. Earlier directions are kept in `docs/01_directions.md`, `05` and `06`.

**Deadline: Mon 16 Nov, 11:59 GMT** (Sun 23:59 Anywhere on Earth). Resubmitting under the same title replaces the earlier version until then.

## Where things are

| Path | What it holds |
|---|---|
| `docs/00_sprint_brief.md` | Sprint facts, rubric, tracks, judges, what has won before, submission checklist |
| `docs/01_directions.md` | Every direction explored, prior work, arguments for and against, how they combine |
| `docs/02_literature.md` | Papers and projects by theme, with links and how closely each has been checked |
| `docs/03_pilot_log.md` | Hand-run pilot observations so far, plus a template for logging more |
| `docs/04_decisions.md` | Open questions, criteria for choosing, decisions as they are made |
| `docs/05_false_blame_true_record.md` | Design, labels, 20-scenario grid and run plan for the "False blame, true record" study (saved 14 Nov from the live doc) |
| `docs/06_referral_under_pushback.md` | Brief for the "Referral under pushback" study, kept as fallback or follow-up; cases not yet chosen |
| `docs/07_triage_under_pushback.md` | **Start here.** Brief for the "Triage under sustained pushback" study, the working direction from 14 Nov: set-up, three arms, fourteen factors, outcomes, open decisions. Factors still wide, size not set |
| `notes/` | Raw material: discussion transcripts, the chapter the team read, pilot chat exports |
| `scenarios/` | Scenario files, once a direction is chosen |
| `src/` | Code, once a direction is chosen |
| `results/` | Model outputs, labels and figures |
| `report/` | Official template and the write-up |

## Live documents (editable copies)

| Document | Link |
|---|---|
| Brief: Triage under sustained pushback | https://claude.ai/artifact/Kv9Svkp4SMSLMkUZzdmFyM |
| Whiteboard: study map for the triage design | https://claude.ai/artifact/Gs3y3Tg6mGP3baiMpERrg4 |
| False blame, true record: design and scenario grid | https://claude.ai/artifact/KAkwjmJLk5EzddTj8dxVUU |
| Referral under pushback: brief | https://claude.ai/artifact/D7ge4jP9JqrNZF8H8cyYnp |

The markdown files in `docs/` are snapshots of these. If a live document has been edited since, it is the newer version.

## Two cautions that apply to everything here

1. **Paper details are second-hand.** They come from abstracts, search excerpts and machine summaries of pages, not from reading papers in full. `docs/02_literature.md` marks each one. The sprint can disqualify for fabricated references, so check each paper against the original before it goes in the report.
2. **"Novel" means "nothing found in our searches".** It is not a guarantee that no one has done it.

## Setup still to do

- [ ] `git init` and a first commit (optional public GitHub repo is allowed by the sprint)
- [ ] Copy `.env.example` to `.env` and add API keys; set a spending cap with each provider
- [ ] Download the official report template into `report/`
- [ ] Drop the discussion transcript and the chapter into `notes/`
- [ ] Decide whether to build in Inspect (it appears on the sprint's Track 1 reading list) or plain scripts

## Declarations to carry into the final README and report

The sprint allows prior work and AI tools if they are declared. Undeclared prior work can disqualify.

- [ ] **Prior work:** background reading and direction scoping began on 11 Nov 2026, before the sprint opened. List anything else written before Fri 13 Nov (scenarios, pilot code).
- [ ] **AI assistance:** literature search, direction scoping and this folder's documents were produced with Claude. List any other tools used for code or writing.
- [ ] **Team members and roles**
