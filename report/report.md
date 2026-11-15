# Noise versus Evidence in Triage Conversations: Does a Model Move for the Right Reasons?

*Report draft, 15 Nov 2026. The full text is the live doc (the editable copy): https://claude.ai/artifact/5mMEY8Xjtk3KWyRMLKidfL. This file holds the abstract, the figure list and how to reproduce the numbers; it is not a copy of the body. Export the doc to Word or PDF from its menu to move it into the official template.*

## Abstract

When a user challenges a medical answer without giving a reason, should the model move? We test whether a model can tell an unfounded challenge from new clinical evidence. In ten clinician-written triage cases, Claude Haiku 5.5 gave a diagnosis and an urgency level, then received ten scripted follow-ups: challenges with no content, plus at most one new fact that was irrelevant, supportive, or should have changed the answer. Each conversation was run as a patient, a nurse and a consultant, in English, Chinese and Japanese: 11,718 conversations and 128,898 replies. The model largely separated noise from evidence: an irrelevant fact changed urgency in 37 of 2,158 conversations (1.7%), an alarming fact in 1,657 of 1,942 (85.3%). But content-free challenges still changed it in 504 of 5,396 replies (9.3%), twice as often for flat contradiction as for mild doubt, and almost always upward: 115 of 536 conversations ended more urgent than they began and 9 less. Speaker and language mattered only under flat contradiction, from 3.3% of replies for an English-speaking patient to 29.0% for a Japanese-speaking consultant. In three further cases, alarming evidence raised urgency in 95.7% of conversations while reassuring evidence lowered it in 29.0%, and two thirds of those reductions were undone by later noise. One model and ten cases limit these claims. The pattern is a ratchet: pressure, alarm and persistence push triage advice up, and little brings it down.

## Sections in the live doc

| Section | Contents |
| --- | --- |
| 1. Introduction | The question, why triage, the gap, three contributions |
| 2. Related work | Eight references, all opened on 15 Nov (`docs/02_literature.md`, section 8) |
| 3. Methods | One conversation; seven kinds of follow-up; position-locking; cases and factors; model and run; outcomes; reading the diagnoses; statistics |
| 4. Results | 4.1 noise against controls; 4.2 direct against non-direct; 4.3 upward drift; 4.4 speaker and language; 4.5 uptake; 4.6 up against down; 4.7 first answer against the key; 4.8 confidence and hedging |
| 5. Discussion | Two readings of each pattern and what the data separate |
| 6. Limitations and conclusion | Six main limits; conclusion |
| Appendix A | Limitations and Dual-Use / Ethical Considerations (mandatory); AI assistance statement, to be confirmed by the team |
| Appendix B | System prompt, questions, noise messages, case tables, one conversation in full |

## Figures

| Figure | File | Drawn by |
| --- | --- | --- |
| 1. The conversation design | `report/figures/fig01_design.png` | `report/make_figures.py` |
| 2. What moves the urgency level | `report/figures_final/report_fig2_what_moves_urgency.png` | `report/report_figures.py` |
| 3. Drift under noise alone | `report/figures_final/report_fig4_drift_direction.png` | `report/report_figures.py` |
| 4. Movement under noise by speaker and language | `report/figures_final/report_fig3_speaker_language.png` | `report/report_figures.py` |
| 5. The reversal cases | `report/figures/fig04_reversal_cases.png` | `report/make_figures.py` |

## Reproducing the numbers

```
python report/report_numbers.py results/main/scores/s2 report/report_numbers_final.json
python report/report_figures.py results/main/scores/s2 report/figures_final
```

- Every number in the report is in `report/report_numbers_final.json`, computed from `results/main/scores/s2/long_table.csv` (scored at 23:01 on 15 Nov, scoring id `f64663361112d027`).
- The ten main cases and the three reversal cases are reported separately. Intervals come from resampling the ten main cases 10,000 times.
- If the diagnoses are judged further and the run is rescored, run both commands again: urgency numbers will not change; the diagnosis and hedging numbers (sections 4.2, 4.5 and 4.8) may move slightly. At the time of this draft 2,588 of 128,898 replies had a diagnosis that was not read.

## Before submission

- [ ] Move the text into the official template and check the 8-page limit. Sections 4.7 and 4.8 and the discussion table are the first candidates for the appendix
- [ ] Add authors and tracks; keep the same title on resubmission
- [ ] Confirm section 3.4's description of who wrote the cases, and the AI assistance statement in Appendix A
- [ ] A clinician looks at the answer key, the reassuring facts and a sample of the diagnosis readings
- [ ] A native speaker reads the Chinese and Japanese direct noise messages, or the report keeps saying none did
- [ ] Delete the note to the team at the top of the doc
