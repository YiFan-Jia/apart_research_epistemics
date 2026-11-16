# Scored tables for the main run (scorer v2)

These are the scored outputs of the main run, produced by `src/score.py`. The raw run (database, transcripts, extractions) is not in git because it is about 1.2 GB.

`long_table.csv` (one row per reply, 75 MB) is stored compressed as `long_table.csv.gz`. Unzip it before running the report scripts, which read `long_table.csv`:

```bash
gunzip -k results/main/scores/s2/long_table.csv.gz
python report/report_numbers.py results/main/scores/s2 report/report_numbers_final.json
python report/report_figures.py results/main/scores/s2 report/figures_final
```

Everything else in this folder (summary, outcomes, contrasts and so on) is read as is.
