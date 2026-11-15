# scenarios: the file contract with the asset builder

The vignette store, the rewrites and translations, and the asset store are delivered into this folder. The pipeline only reads these files. From 15 Nov `vignettes.json` and `assets.json` are produced from the clinicians' three spreadsheets by the importer (next section); do not edit them by hand, change the spreadsheet and import again. `fixture/` holds a small worked example (V00) used by the tests; it is in the earlier one-update format, which the pipeline still reads. Check a delivery with:

```
python -m src.assets                 # what is ready and missing, stage by stage
python -m src.assets --all           # every problem, not the first few per vignette
```

## Importing the clinicians' spreadsheets

```
python -m src.import_sheets --dir scenarios/source --patient-update-status approved --neutral-status approved
python -m src.assets
```

One spreadsheet per language (English, Mandarin, Japanese), one row per vignette, the same column order in each. The importer writes `vignettes.json`, `assets.json` and `import_report.md` here and keeps the previous two files as `*.bak`. It changes nothing clinical. It strips stray spaces, renumbers `V001` as `V01`, reads a severity cell that the spreadsheet turned into a date ("5/10" stored as 5 October) back as "5/10", and reads "None" in the urgency-update cell as "no urgency-only update for this vignette". Everything it notices is listed in `import_report.md`. Imported texts get status `approved` unless `--status draft` is given. The three updates are written once per language in the spreadsheet, as a clinician's note; the nurse and the doctor send that text.

`source/` holds the three spreadsheets as downloaded from Drive on the evening of 15 Nov, after the clinicians' fixes. Columns 25 to 28 of each are the accepted names for the starting diagnosis and the three updates in the patient's own words (`baseline_accepted_diagnosis_names`, `CC_both_pt`, `DC_urgency_patient`, `DC_Dx_patient` in the English sheet; the other two translate the headings, so the importer reads them by position). The importer uses the patient columns for the patient only. Where a cell is empty, the patient gets the note-style update and the import report says so. If an update is changed, change the patient column beside it too. `source/patient_updates.json` is the earlier set drafted by Claude, no longer used.

`source/reversal/` holds the three reversal cases (V021 to V023): the clinicians' English workbook and Claude's Chinese and Japanese versions of it. They have three more columns (`RC_Urgency`, `RC_urgency_outcome`, `RC_urgency_patient`: a reassuring update that lowers the urgency) and no diagnosis update. The importer adds their rows to the main sheets' rows.

`source/neutral_fact.json` holds the neutral fact: one irrelevant sentence per language, for the nurse and doctor and for the patient. The importer gives it to every vignette as the `neutral` update, with the status given by `--neutral-status`.

Every file is UTF-8 JSON. Write it with the encoding stated explicitly (`encoding="utf-8"`, `ensure_ascii=False`); Windows defaults corrupt Chinese and Japanese.

## `vignettes.json` (from the clinicians)

```json
{"format_version": 2, "vignettes": [ { ...one record per vignette... } ]}
```

Each vignette has a supportive update and two alternative discordant updates: an **urgency update**, which should change the urgency while the diagnosis stays the same, and a **diagnosis update**, which should change the most likely diagnosis. Only one update is ever added to a conversation.

| Field | Content |
| --- | --- |
| `id` | `V01` to `V20` (`source_id` keeps the spreadsheet's `V001`) |
| `clerking` | The case in English in the third person. The importer builds it from the structured columns (age, sex, complaint, onset, character, timing, modifiers, severity, two associated symptoms, history, lifestyle); the vignette check compares every version with it |
| `start_dx` | Starting diagnosis (`baseline_working_diagnosis`) |
| `start_accept` | List of other names accepted as the starting diagnosis. The spreadsheet has none, so the importer leaves it empty; the judge model reads free-text answers against `start_dx` |
| `start_urgency` | `A`, `B`, `C` or `D` on the current scale: **A emergency: emergency assessment now; B same day: assessment by a clinician within 24 hours; C soon: within 2 to 7 days; D routine: a routine appointment or self-care** (scale `v3`, A most urgent). The exact wording is in `config.json` (`urgency_levels`) |
| `urgency_scale_version` | The scale the urgency answers were set on: `"v3"`. Required. The validator refuses a vignette whose value differs from `urgency_scale_version` in `config.json`, so answers set on another scale cannot be scored backwards |
| `supportive_update` | One sentence, English (`CC_both`) |
| `urgency_update`, `urgency_post_urgency` | The urgency update and the urgency after it (`DC_Urgency`, `DC_urgency_outcome`). The diagnosis is expected to stay `start_dx`. `urgency_update` may be `null`: the vignette then runs without this arm. The validator refuses an urgency update whose urgency equals `start_urgency` |
| `dx_update`, `post_dx`, `dx_post_urgency` | The diagnosis update, the diagnosis after it and the urgency after it (`DC_Dx`, `DC_DxOutcome`, `DC_DxOutcomeUrgency`). The urgency may equal `start_urgency` (only the diagnosis changes) |
| `post_accept` | List of other names accepted as `post_dx` (empty from the importer). Keep it mutually exclusive with `start_accept` |
| `uncertainty` | `low`, `medium`, `high` or `null` |

The earlier one-update format (`discordant_update`, `post_urgency`, `changed`, as in `fixture/`) is still read: such a vignette has a single `discordant` update.

## `assets.json` (rewrites and translations)

```json
{"format_version": 2, "assets": [ {"vignette": "V01", "perspective": "patient", "language": "en", "slot": "opening",
                                    "text": "...", "status": "approved"}, ... ]}
```

One record per vignette × perspective (`patient`, `nurse`, `consultant`) × language (`en`, `zh`, `ja`) × slot: `opening`, `supportive`, and whichever of `neutral`, `discordant_urgency`, `discordant_reassure` and `discordant_dx` the vignette has. With the neutral fact that is 45 per vignette, 36 for one with no urgency update, and 45 for a reversal case (which has a reassuring update and no diagnosis update). A one-update vignette uses the slot `discordant`. `text` and `status` (`draft`, `auto_checked`, `flagged`, `approved`) are required. Any other fields (`check`, `back_translation`, `source_hash`, `generator`) are kept for your records and ignored.

- **The opening is the rewritten vignette only.** Do not add the question at the end: the pipeline appends the fixed ask for that perspective and language from `prompts.json`.
- Only `approved` assets are used. A stage builds as soon as every asset it uses is approved, so a batch, which uses all three languages and all three speakers, builds once every text of its vignettes is approved.
- Checked automatically: present and non-empty; Chinese text has Chinese characters and no kana; Japanese text has kana; English has no CJK; no leading, trailing or doubled whitespace; no leftover notes or preambles ("TODO", "Here is", "Translation:", brackets); the updates differ from each other and from the opening; the opening does not contain the ask.
- **Changing an approved asset after a run has started stops that run from resuming.** Start a new run name.

## `noise_bank.json` and `prompts.json`

`noise_bank.json`: ten messages per noise type (`nondirect`, `direct`) per language, `position` 1 to 10, each with `text` and `status`. `prompts.json`: the one English system prompt (its `{urgency_levels}` placeholder, and `{location}` if present, are filled from `config.json`) and the nine asks (perspective × language). A message is status `draft` until the clinicians sign it off; a stage does not build while any message it uses is a draft. Noise must carry no information: no clinical content, no direction, and no outside opinion ("I've been told you're wrong" was replaced on 15 Nov for that reason).

## `dx_mappings.json` (written by `python -m src.judge import-review`)

Clinician-reviewed readings of free-text diagnoses, one entry per vignette and diagnosis string: the leading diagnosis (`start`, `post`, `both`, `other` or `none`), modifiers, alternatives and stated doubt. These override the judge model at scoring. Do not write it by hand: mark up the `dx_review.csv` that each scoring produces and import it (see `docs/11_pipeline_guide.md`).

## `scripts.jsonl` (generated, not committed)

Built by `python -m src.scripts` from the files above, stage by stage. Never edit it by hand.
