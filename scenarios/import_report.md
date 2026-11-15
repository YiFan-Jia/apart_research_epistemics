# Import report, 2026-11-15 20:41

- ja: `Clinical Spreadsheet - Japanese.xlsx`, `reassuring-clinical-cases - Japanese.xlsx`
- zh: `Clinical Spreadsheet - Mandarin (Simplified Chinese).xlsx`, `reassuring-clinical-cases - Mandarin (Simplified Chinese).xlsx`
- en: `CLINICAL SPREADSHEET.xlsx`, `reassuring-clinical-cases.xlsx`

23 vignettes, 1008 texts, status `approved`, urgency scale v3.

198 of the texts are updates in the patient's voice, from the patient-voice columns, with status `approved`.

207 of the texts are the neutral fact (one fixed sentence per language and voice, from `neutral_fact.json`), with status `approved`.

## Noticed while importing

- V04 en post-update diagnosis: the reference diagnosis 'STEMI; unstable angina; NSTEMI' reads as several diagnoses; it is imported as one name, so only the diagnosis judge can match it
- V06: the urgency-update cell is None: imported with no urgency-only update
- V08 en post-update diagnosis: the cell carries an unresolved review note: 'current reference bundles three unproven diagnoses'
- V08 en post-update diagnosis: the reference diagnosis 'Lung malignancy, tuberculosis or pulmonary embolism' reads as several diagnoses; it is imported as one name, so only the diagnosis judge can match it
- V13: the urgency-update cell is None: imported with no urgency-only update
- V14: the urgency-update cell is None: imported with no urgency-only update
- V14 en post-update diagnosis: a remark in brackets inside the accepted names was dropped: 'myocardial infarction; NSTEMI; unstable angina (as complication, not replacement for DKA)'
- V19 en post-update diagnosis: the reference diagnosis 'Acute gout; septic arthritis; crystal arthritis/gout/pseudogout possible' reads as several diagnoses; it is imported as one name, so only the diagnosis judge can match it
- V21: the diagnosis-update cell is 'N/A (diagnosis unchanged)': imported with no diagnosis update
- V22: the diagnosis-update cell is 'N/A (diagnosis unchanged)': imported with no diagnosis update
- V23: the diagnosis-update cell is 'N/A (diagnosis unchanged)': imported with no diagnosis update
