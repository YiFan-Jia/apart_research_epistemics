# scenarios: the file contract with the asset builder

The vignette store, the rewrites and translations, and the asset store are delivered into this folder. The pipeline only reads these files. **`fixture/` holds a complete worked example (V00 in all 27 slots) in exactly the format the pipeline reads: match it.** Check a delivery with:

```
python -m src.assets                 # what is ready and missing, stage by stage
python -m src.assets --all           # every problem, not the first few per vignette
```

Every file is UTF-8 JSON. Write it with the encoding stated explicitly (`encoding="utf-8"`, `ensure_ascii=False`); Windows defaults corrupt Chinese and Japanese.

## `vignettes.json` (from the clinicians)

```json
{"format_version": 1, "vignettes": [ { ...one record per vignette... } ]}
```

| Field | Content |
| --- | --- |
| `id` | `V01` to `V20` |
| `clerking` | Third-person English clerking text |
| `start_dx` | Starting diagnosis |
| `start_accept` | List of other names accepted as the starting diagnosis (may be empty) |
| `start_urgency` | `A`, `B`, `C` or `D` |
| `supportive_update`, `discordant_update` | One sentence each, English |
| `post_dx` | Diagnosis after the discordant update (same as `start_dx` when only urgency changes) |
| `post_accept` | List of other names accepted after the update. **New field, not in the vignette brief: the judge needs it.** Keep it mutually exclusive with `start_accept` |
| `post_urgency` | `A` to `D` |
| `changed` | `diagnosis`, `urgency` or `both` |
| `uncertainty` | `low`, `medium` or `high` |

## `assets.json` (rewrites and translations)

```json
{"format_version": 1, "assets": [ {"vignette": "V01", "perspective": "patient", "language": "en", "slot": "opening",
                                    "text": "...", "status": "approved"}, ... ]}
```

One record per vignette × perspective (`patient`, `nurse`, `consultant`) × language (`en`, `zh`, `ja`) × slot (`opening`, `supportive`, `discordant`): 27 per vignette. `text` and `status` (`draft`, `auto_checked`, `flagged`, `approved`) are required. Any other fields (`check`, `back_translation`, `source_hash`, `generator`) are kept for your records and ignored.

- **The opening is the rewritten vignette only.** Do not add the question at the end: the pipeline appends the fixed ask for that perspective and language from `prompts.json`.
- Only `approved` assets are used. A stage builds as soon as every asset it uses is approved, so English patient assets alone are enough for the pilot and stage 1.
- Checked automatically: present and non-empty; Chinese text has Chinese characters and no kana; Japanese text has kana; English has no CJK; no leading, trailing or doubled whitespace; no leftover notes or preambles ("TODO", "Here is", "Translation:", brackets); the two updates differ from each other and from the opening; the opening does not contain the ask.
- **Changing an approved asset after a run has started stops that run from resuming.** Start a new run name.

## `noise_bank.json` and `prompts.json`

`noise_bank.json`: ten messages per noise type (`nondirect`, `direct`) per language, `position` 1 to 10, each with `text` and `status`. `prompts.json`: the one English system prompt (with `{location}` and `{urgency_levels}` placeholders filled from `config.json`) and the nine asks (perspective × language). The English drafts here are status `draft` until the clinicians sign them off; who owns them is still an open item (build spec section 10).

## `scripts.jsonl` (generated, not committed)

Built by `python -m src.scripts` from the files above, stage by stage. Never edit it by hand.
