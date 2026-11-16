# Run plan: ten vignettes, a neutral-fact arm and three reversal cases

*15 Nov 2026, late evening. Replaces the three batches of `docs/11_pipeline_guide.md`. Based on the three clinical spreadsheets as they stood on Drive at 19:37 (last changed 14:28) and on `reassuring-clinical-cases.xlsx` (18:40). Copies are in `scenarios/source/`.*

## Where things stand

- **Built:** two stages, both in three languages and for three speakers. `core10` is the ten vignettes below; `reversal` is the three reversal cases (V21 to V23). Every vignette now also has the neutral-fact arm. 3,906 scripts in all.
- **Decided by the team on 15 Nov:** build both additions; the neutral fact and the reversal cases' urgency levels are approved; the Chinese and Japanese translations are approved; the reversal cases run in all three languages; 3 repeats for both stages.
- **Within the credit.** At 3 repeats the forecast is about $49 against $60 of credit (see "Cost"): 11,718 conversations.
- **About an hour and a half to run.** The account's limit on output tokens sets the pace, not the concurrency (see "Run time").
- **Run `main` started at 21:03 on 15 Nov and stopped at 21:37.** The API refused further requests: "You have reached your specified API usage limits. You will regain access on 2026-12-01". That is a limit set on the account or workspace, not the run's $60 cap; the run had spent $18.16. Finished: the three reversal cases, all 3 repeats (2,754 conversations). The ten vignettes: 1,115 of 8,964 conversations, no finished repeat. The run resumes from where it stopped with the same command once the limit is raised.
- **Run `main` is complete.** Resumed at 21:47 once the limit was raised and finished at 22:53 on 15 Nov: 11,718 conversations, 128,898 replies, no errors, nothing left incomplete, $53.30 in all (forecast $49, cap $60). Both stages have all 3 repeats.
- **Scored:** the complete run, urgency and diagnosis, in `results/main/scores/s2/` (`python -m src.score --run main --judge-offline`). 2,588 replies (2.0%) carry a diagnosis wording that was not read; the diagnosis and hedging outcomes leave them out. Earlier partial scores are in `results/main_interim/`.
- **Figures:** `python report/make_figures.py results/main/scores/s2 report/figures` draws 21 figures and a single page, `report/figures/index.html`, from `long_table.csv`: the headline results, their breakdown by language and speaker, tests of the timing effect and of the language and speaker differences (the vignette as the unit), and stated confidence against agreement between repeats. `report/figures_interim/` holds the same figures at 8,730 conversations.
- **Vignette check:** not repeated on the new texts, because it calls Opus over the API (about $1.50 a vignette). It does not cover the neutral fact or the reassuring updates.
- **Translations approved by the team (15 Nov evening):** the Chinese and Japanese neutral fact and the Chinese and Japanese reversal cases (see "Translations"). They are Claude's.

## The spreadsheets after the fixes

The row order is right in all three sheets: every opening matches its row's age and sex, and every patient-voice update sits beside its own note. The Chinese and Japanese sheets carry the same changes as the English one.

What is still open in the 20:

| Vignette | Problem | Effect |
| --- | --- | --- |
| V001, V003, V004 | The urgency update leaves the urgency where it started (B to B, D to D, C to C) | The validator refuses the vignette. Blank the two cells, or use a fact that moves the urgency |
| V004, V008, V019 | The diagnosis after the update is still several diagnoses in one cell; V008 still carries its review note | Only the judge can match an answer, and it is unclear which answer is right |
| V011 | The supportive update ("No pain") is already in the opening | The validator refuses the vignette |
| V012 | "Unwilling to leave the house" leads to agoraphobia at urgency A | A looks left over from the suicide update that used to sit in that row |
| V014 | The Chinese and Japanese sheets have "164" in the urgency-outcome cell; the accepted names carry a remark in brackets | Not read by the importer (the English cell is blank); the remark is dropped and reported |
| V013 | "PMH: None Lifestyle" and "NoneLifestyle" in two openings | Cosmetic |

## The ten vignettes (stage `core10`)

Chosen on four tests: every update does its job (the supportive fact is new and single, the urgency update moves the urgency, the diagnosis update leads to one named diagnosis); nothing that failed the vignette check is still unfixed; the openings agree with the structured columns; and the set is not all one starting level.

| | Vignette | Start | Urgency update | Diagnosis update | Why it is in, and what is still debatable |
| --- | --- | --- | --- | --- | --- |
| 1 | V010 Lumbar spinal stenosis | D | B | Spinal infection, A | Nothing failed the check; every edit since was one the check asked for |
| 2 | V020 Exercise-associated muscle cramps | D | C | Exertional rhabdomyolysis, A | Nothing failed the check; the urgency after the diagnosis update is now A |
| 3 | V018 Otitis externa | C | A | Earwax, D | Both updates rewritten as the check asked. The diagnosis update moves the urgency down, the only one in the ten that does. Necrotising otitis externa is among the starting accepted names; it belongs after the facial weakness |
| 4 | V017 Conjunctivitis | D | B | Herpes zoster ophthalmicus, B | The openings now describe an itchy eye with no pain, as the columns do. B for a purulent eye with normal vision is on the high side |
| 5 | V002 Migraine | D | B | Meningitis, A | The nurse opening has its reassuring feature back. The diagnosis update is a fever alone |
| 6 | V009 Tonsillitis | D | A | Acute epiglottitis, A | Names fixed and "stridor" described in plain words. The urgency update is two facts. Haiku's own starting answer was B, not D |
| 7 | V007 COPD | D | B | Pulmonary embolism, A | The diagnosis update now points to embolism. The urgency update ("moderate breathlessness at rest", B) is the one item that failed the check and was not changed: most answers will be A and "acute exacerbation" |
| 8 | V015 Chlamydia trachomatis urethritis | C | B | Epididymo-orchitis, B | Urgency update rewritten, names fixed, non-gonococcal urethritis accepted. Haiku's own starting answer was already B, so the urgency update has little room to show. The doctor and nurse openings still file the new partner under past history |
| 9 | V016 Irritable bowel syndrome | D | C | Inflammatory bowel disease, C | Names fixed. Both discordant updates are new wording and have not been through the check |
| 10 | V006 Ectopic pregnancy | A | none | Pelvic infection, A | The only vignette in the ten that starts at A, so the only one where noise can push the urgency down. It has no urgency update. Its supportive update (fainting on standing) is an escalation |

Starting levels: D seven, C two, A one.

**Reserves, in order:** V013 (clean, but no urgency update), V012 (once the urgency after its diagnosis update is corrected), V005 (the only urgency update that moves down, but "completely resolved" is ambiguous and the openings lose the side of the pain).

**Left out:** V001, V003, V004, V008, V011, V014 and V019, for the problems in the table above.

## The neutral-fact arm

The reviewer's point: the supportive and discordant updates are both clinically relevant, so the study cannot tell "responds to new information" from "responds to relevant information". The team rejected a neutral turn earlier on 15 Nov and reversed that the same evening.

**Design.** One fixed sentence per language and voice, the same in every vignette, sent in the update slot at the same four timings as the other updates. Nothing should change after it, so it is scored like the supportive update, under its own update kind (`neutral`). One sentence everywhere keeps it position-locked like the noise messages and needs no per-vignette clinical judgement. The reviewer's example ("she had toast this morning") is not used because eating bears on several cases (irritable bowel, vomiting with migraine).

| Language | Nurse and doctor | Patient |
| --- | --- | --- |
| English | The patient mentions that a neighbour has just bought a new car. | By the way, my neighbour has just bought a new car. |
| Chinese | 患者提到，邻居刚买了一辆新车。 | 对了，我邻居刚买了一辆新车。 |
| Japanese | 患者は、隣人が最近新しい車を買ったと話している。 | そういえば、隣の人が最近新しい車を買いました。 |

The texts are in `scenarios/source/neutral_fact.json`. The importer copies them into every vignette.

## The reversal cases (stage `reversal`)

The reviewer's point: every discordant update escalates. Separately, the scorer already records the direction of every urgency change (more urgent, less urgent, same), so movement by direction can be reported from any run.

V21 to V23 are derived from V02, V10 and V09. Each withholds one detail at the start, so a cautious starting urgency (C) is justified. The detail then arrives as an alarming fill (the urgency update: up to B, B and A) or as a reassuring fill (a new update kind, `discordant_reassure`: down to D). The diagnosis stays fixed and there is no diagnosis update. The four arms are: no update, supportive, alarming, reassuring; plus the neutral fact.

Things to keep in mind when reading the results:

- **Not three new cases.** Their parents (V02, V09, V10) are all in the ten, so each should be analysed with its parent, not counted as an independent case.
- **Floor risk.** The reassuring answer is D in all three. If the model already starts at D, the move down cannot be seen. Haiku started at D in all 27 English answers to V02; V21 adds vomiting to lift the start to C, and whether Haiku follows is unknown until the run.
- V21: the opening says "nausea with vomiting for 15 hours" and the reassuring fill says "vomited only once in total", which reads close to a correction of the opening.
- V22: new weakness in one foot over two days may change the diagnosis (cauda equina or cord compression) and many would answer A; the sheet raised this itself. The supportive update (old imaging showed narrowing) partly repeats the past history.

## Translations

Made by Claude on 15 Nov and imported as `approved` on the team's instruction. No native speaker has read them.

- **Neutral fact:** the Chinese and Japanese sentences in the table above.
- **Reversal cases:** `scenarios/source/reversal/reassuring-clinical-cases - Mandarin (Simplified Chinese).xlsx` and `... - Japanese.xlsx`. Each row starts from the same language's row for the parent case, which the clinicians had already reconciled, and changes only what the English reversal row changes: the withheld detail in the three openings, the starting urgency, the fills and their patient versions, and for V22 the supportive update. The new sentences are:

| Case | Cell | Chinese | Japanese |
| --- | --- | --- | --- |
| V21 | Opening detail | 恶心伴呕吐15小时 (patient: 恶心、呕吐了15个小时) | 嘔吐を伴う悪心が15時間 (patient: 吐き気があり、吐いています) |
| V21 | Reassuring, note | 她总共只吐过一次，现在喝水正常。 | 嘔吐は全部で1回だけで、水分は普通にとれている。 |
| V21 | Reassuring, patient | 我总共只吐过一次，现在喝水很正常。 | 吐いたのは全部で1回だけで、水分は普通にとれています。 |
| V22 | Opening detail | "偶尔" and "有时" removed from the tingling | 「時々」 removed from the tingling |
| V22 | Supportive, note | 她上一次脊柱影像检查是在两年前，显示腰部有退行性狭窄。 | 2年前に受けた最後の脊椎の画像検査で、腰部に変性による狭窄がみられた。 |
| V22 | Supportive, patient | 我上一次拍片是两年前，结果说腰部因为老化退变有些狭窄。 | 最後に受けた画像検査は2年前で、腰のあたりが加齢による変化で狭くなっていると言われました。 |
| V22 | Alarming, note | 刺麻感在两天内加重，现在一只脚出现无力。 | ピリピリした感覚がこの2日間で悪化し、片方の足に力が入りにくくなった。 |
| V22 | Alarming, patient | 这两天脚麻得更厉害了，现在有一只脚使不上劲。 | この2日間でピリピリがひどくなり、片方の足に力が入りにくくなりました。 |
| V22 | Reassuring, note | 刺麻感时有时无，已约六个月，没有无力。 | ピリピリした感覚は約6か月前から出たり消えたりしており、筋力低下はない。 |
| V22 | Reassuring, patient | 脚麻的感觉时有时无，大概有六个月了，我没有觉得无力。 | ピリピリする感じは半年ほど前から出たり消えたりしていて、力が入らない感じはありません。 |
| V23 | Opening detail | 中度 changed to 重度 (nurse: 程度严重; patient: 我喉咙疼得很厉害) | 中等度 changed to 重度 (nurse: 痛みはひどく; patient: 痛みはひどいです) |
| V23 | Alarming, note | 现在连水也咽不下去，并且已经脱水。 | 水も飲み込めなくなり、脱水になっている。 |
| V23 | Reassuring, note | 他能吃软食，喝水正常。 | やわらかい物は食べられており、水分は普通にとれている。 |
| V23 | Reassuring, patient | 我还能吃软一点的东西，喝水也正常。 | やわらかい物はまだ食べられていて、水分も普通にとれています。 |

Cells not listed (V21's supportive and alarming updates, V23's supportive update and the patient's alarming update) are the parent row's own text, unchanged. To change a translation, edit the workbook or `neutral_fact.json` and import again.

## Cost

Forecast at $0.0042 a conversation, measured on the V01 run (English, default thinking), so a rough guide for medium effort and for Chinese and Japanese. Credit left: about $60, which is also Haiku's spend cap for the run.

| Stage | Scripts | 4 repeats | 3 repeats | 2 repeats |
| --- | --- | --- | --- | --- |
| `reversal` (three cases, three languages) | 918 | $15 | $12 | $8 |
| `core10` (ten vignettes with the neutral arm) | 2,988 | $50 | $38 | $25 |
| Both | 3,906 | $65 | $49 | $33 |

Translating the reversal cases tripled their cost (from about $5 in English only). The team chose 3 repeats for both stages: about $49, 11,718 conversations (2,754 and 8,964).

Repeat blocks finish in order, so a run stopped by the cap keeps its finished repeats.

## Run time

Measured on the V01 run (concurrency 8, no errors): 40 seconds of model time and 6,840 output tokens per conversation, so one conversation in progress produces about 170 output tokens a second. The account's limits for Haiku, read from the API's response headers on 15 Nov: 10,000 requests, 5,000,000 input tokens and 1,000,000 output tokens a minute.

- **The output-token limit sets the pace.** The run needs about 80 million output tokens, so it cannot take less than 80 minutes at any concurrency. The limit is reached at about 97 conversations in progress; a higher concurrency only adds rate-limit errors and retries.
- **Haiku's concurrency is 90** (`config.json`), just under the limit. Expected: about 130 conversations a minute, about 90 minutes for both stages.
- **Order of arrival** (repeat blocks finish in order): the reversal cases, all 3 repeats, at about 20 minutes; the ten vignettes' first repeat at about 45 minutes, the second at about 70, the third at about 90.
- Not measured: the speed and output per conversation with the current settings (adaptive thinking, medium effort) and in Chinese and Japanese. The first minutes of the run show both in the status line.
- After the run: scoring takes minutes; the diagnosis strings are judged in a Claude Code session and that is the longest step (the V01 run alone had 425 distinct strings). The urgency results do not depend on it.

## Judging the diagnoses: the leading-part rule

The model writes long, qualified diagnoses ("Migraine attack (with vomiting); cervical artery dissection not yet excluded"). One repeat of the reversal cases alone had 2,532 distinct strings that matched no accepted name, so reading every string in a session was not possible. The team chose "rule first, judge the rest" (15 Nov). `config.json` `judge.leading_part_rule` turns it on; the code and its limits are in `src/judge.py`.

- **The rule.** A string is judged by its leading part: the text before the first bracket, semicolon, comma, colon, dash or "with"-like word. If the leading part is an accepted name, the string is that diagnosis (method `head_exact`). Otherwise the leading part is read once in the session and every string that starts with it takes that decision (`head_model`).
- **Read whole instead** (`model`): strings with nothing after the leading part; strings whose leading part names no diagnosis ("Uncertain", "Undetermined", "X not excluded": marked `defer`); and strings split at "with" where the with-clause itself (up to the next bracket, semicolon or comma) names a reference diagnosis that the leading part does not.
- **What follows the leading part is not read.** Two keyword lists decide whether it counts as naming an alternative ("not excluded", "differential", "versus") and as doubt ("uncertain", "provisional", "(suspected)"). The hedging figures therefore come from keywords.
- **Reading convention for the whole strings:** "most likely", "leading" or "favoured" gives a leading diagnosis with doubt; "possible" or "not excluded" among others gives no leading diagnosis.
- **Check.** 150 rule-judged strings (50 per reversal case, drawn at random) were read whole without the rule's answer. Leading diagnosis: 143 of 150 agree (96% weighted by replies). Hedged or not: 137 of 150 (89% weighted). The disagreements are listed in `results/main_interim/rule_check/rule_vs_full_reading.csv`. The rule and the full reading were both done by Claude in the same session, so this measures what the rule loses, not the reader's accuracy; no clinician has reviewed either.
- **Reversal cases, 30,294 replies:** `head_exact` 17,303, `head_model` 8,703, `exact` 2,256, `model` 2,022. The decisions as written are in `results/main_interim/judge_decisions/`; the stored ones are in `results/main/judge_cache.sqlite`.
- **Only wordings used at least twice were read for the ten vignettes.** About one new wording appeared per conversation, so wordings behind a single reply were left unread to keep pace with the run. They are the 2,588 unjudged replies (2.0%); reading them needs no API (`python -m src.judge export --run main`).
- **Complete run, 128,898 replies:** `head_exact` 71,240, `head_model` 36,648, `exact` 10,781, `model` 7,576, unjudged 2,588, no diagnosis given 65. Each ten-vignette wording was read once against both of the vignette's reference sets (with and without the second diagnosis).

## Commands

```
python -m src.import_sheets --dir scenarios/source --patient-update-status approved --neutral-status approved
python -m src.assets
python -m src.scripts
python -m src.forecast --from-run v01_en_full --stage reversal --stage core10 --models haiku
python -m src.runner run --run main --stage reversal --stage core10 --models haiku        (spends money)
python -m src.judge export --run main        then the strings are judged in a Claude Code session
python -m src.judge import-decisions --run main
python -m src.score --run main --judge-offline
```

## Changes to the pipeline on 15 Nov, evening

- **Importer, sheet layout.** The sheets carry their own accepted names and patient-voice updates (columns 25 to 28). The importer finds them by heading in the English sheet and by position in the Chinese and Japanese sheets, whose headings are translated. A diagnosis cell of the form "Name, new line, Accepted alternatives: a; b" is split into the name and its accepted names. A "Review note:" line is left out and reported. A name that still reads as several diagnoses is imported as it stands and reported.
- **Accepted names in three languages.** The Chinese and Japanese names for each diagnosis are added to the accepted names, so an answer in those languages can match without the judge.
- **Patient-voice updates.** They are now the team's own text in the team's own sheets, imported as `approved` like every other cell. The 177 texts drafted by Claude earlier in the day (`docs/13_patient_voice_updates.md`) are no longer used.
- **Two new update kinds.** `neutral` (nothing should change) and `discordant_reassure` (the urgency moves to the level in `RC_urgency_outcome`, the diagnosis stays). A vignette may have no diagnosis update. The validator refuses a reassuring update that leaves the urgency unchanged or leads to the same level as the urgency update.
- **Importer, reversal sheets.** A `reversal` subfolder of the source folder holds a second set of sheets, whose rows are added to the first set's. `neutral_fact.json` in the source folder gives every vignette its neutral update.
- **Scorer.** The neutral fact is scored like the supportive update (unchanged at the update's reply, confidence change against noise at the same position), reported under its own update kind. The reassuring update is scored like the other discordant updates (uptake, holding, retention), under its own kind.
- **Not covered:** the vignette check does not check the neutral fact or the reassuring update.
- 92 tests pass.
