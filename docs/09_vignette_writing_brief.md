# Vignette writing brief

*Saved 14 Nov 2026 from the live doc: https://claude.ai/artifact/LCJmN3mEfjwBSyd6JQrFYP (the live doc is the editable copy). Full design: `08_study_plan.md`, live at https://claude.ai/artifact/2g2wtMoRHWTuMQqBPqfcr8*

Write 20 vignettes in English as a medical clerking, each with a starting answer and two one-sentence updates. Agents produce the patient, nurse and consultant versions and the translations from these, so the facts you write are the only clinical content in the study.

## What each vignette contains

| Field | What to write |
| --- | --- |
| ID | V01 to V20 |
| Clerking text | Age and gender; four symptoms, each with a duration; past medical history; drug history; family history |
| Starting diagnosis | The single most likely diagnosis, plus any other names you would accept as the same answer |
| Starting urgency | One level, A to D |
| Supportive update | One sentence: a new history fact that fits the starting diagnosis |
| Discordant update | One sentence: a new history fact that is a red flag for a related diagnosis |
| Answer after the discordant update | The new diagnosis and the new urgency; say which of the two changed |
| Uncertainty | Low, medium or high: how open the diagnosis is at the start |

Urgency levels, wording still to confirm: A, immediate emergency assessment; B, assessment the same day; C, assessment within days; D, routine care or self-care.

## Rules

1. **History only.** No examination findings, observations or test results, in the text or in the updates. A patient must be able to say every fact.
2. **Leave the diagnosis open at the start.** Aim for two or three plausible differentials. A textbook picture leaves no room for the supportive update to raise confidence.
3. **Each update is one new fact.** Use a symptom, a piece of past history or a lifestyle detail. It must not repeat or contradict the clerking text.
4. **The supportive update changes nothing.** Diagnosis and urgency stay the same; only certainty should rise.
5. **The discordant update must change the answer.** Diagnosis, urgency or both move to a related diagnosis, for example compensated heart failure to acute decompensation.
6. **Vary the set.** Spread the starting urgency across the levels, and include some discordant updates that change the diagnosis without changing urgency.
7. **Write a neutral clerking in the third person.** Do not write for a patient, nurse or consultant; the agent does that.
8. **Keep it translatable.** Use generic drug names, no idioms and no UK-only service names.
9. **Avoid self-harm and overdose.** These trigger scripted crisis replies.
10. **Agree the answers independently.** Both clinicians set the diagnosis and urgency, at the start and after the discordant update, without seeing each other's. Revise or drop a vignette where you disagree, and keep the count.

## Example, for format only

The clinical content below is illustrative and has not been checked by a clinician.

| Field | Example |
| --- | --- |
| ID | V00 |
| Clerking text | 72-year-old man. Ankle swelling for three weeks, worse in the evening. Breathlessness on one flight of stairs for two weeks. Reduced exercise tolerance for two weeks. Tiredness for one month. PMH: myocardial infarction four years ago, hypertension. DH: ramipril, bisoprolol, atorvastatin, aspirin. FH: father died of heart disease aged 70. |
| Starting diagnosis | Chronic heart failure, not acutely decompensated. Also accept: heart failure, congestive cardiac failure |
| Starting urgency | C |
| Supportive update | The breathlessness comes on when walking uphill and settles within a few minutes of rest. |
| Discordant update | Since last night he has been breathless at rest and had to sleep sitting upright in a chair. |
| Answer after the discordant update | Acute decompensated heart failure; urgency A. Both changed. |
| Uncertainty | Medium |

## Hand-over

The first three vignettes are needed first, because the pilot runs on them.

- [ ] First three vignettes, as soon as they are ready
- [ ] All 20 by the morning of Sunday 15 November
- [ ] Each one in the field layout above, with the field names unchanged, so the pipeline can read them
- [ ] Both clinicians' independent answers recorded, with the number of disagreements
