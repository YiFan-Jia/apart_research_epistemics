"""Convert the clinicians' spreadsheets into scenarios/vignettes.json and scenarios/assets.json. No model.

One spreadsheet per language, one row per vignette, the same column order in each. The English sheet gives
the reference answers and the structured case; each sheet gives that language's three openings (doctor,
nurse, patient) and its updates. An update is written as a clinician's note, used for the nurse and the
doctor, and again in the patient's words, used for the patient.

Columns after the first 24 are optional and are found by their headings in the English sheet. A Chinese or
Japanese sheet that translates its headings is read at the positions the English sheet has.
    baseline_accepted_diagnosis_names               accepted names for the starting diagnosis, "a; b; c"
    CC_both_pt, DC_urgency_patient, DC_Dx_patient   the three updates in the patient's words
    RC_Urgency, RC_urgency_outcome, RC_urgency_patient
                                                    a reassuring update (urgency goes down, diagnosis stays),
                                                    the urgency after it, and the patient's wording
A diagnosis cell may carry accepted names on a second line: "Name", new line, "Accepted alternatives: a; b".
A diagnosis-update cell that reads "N/A" means the vignette has no diagnosis update; "None" in the
urgency-update cell means it has no urgency-only update.

A folder given with --dir may hold a subfolder "reversal" with a second set of sheets (the reversal cases);
their rows are added to the first set's. If the folder holds neutral_fact.json, its one fixed sentence per
language and voice becomes every vignette's neutral update.

Nothing clinical is changed. The importer only: strips stray spaces; reads a severity cell that the
spreadsheet turned into a date ("5/10" stored as 5 October) back as "5/10"; splits the accepted names; and
renumbers V001 as V01. Everything it notices is listed in the import report.

Usage:
    python -m src.import_sheets --dir scenarios/source --patient-update-status approved --neutral-status approved
    python -m src.import_sheets --en "CLINICAL SPREADSHEET.xlsx" --zh "...Mandarin....xlsx" --ja "...Japanese.xlsx"
    python -m src.import_sheets --dir <folder> --status draft                # default: approved

Writes scenarios/vignettes.json, scenarios/assets.json and scenarios/import_report.md, keeping the previous
two files as *.bak. Then check the result with: python -m src.assets
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
import time
from pathlib import Path

from .common import ASSET_STATUSES, ROOT, URGENCY_LEVELS, load_config, read_json, write_json, write_text

# Column positions, the same in all three sheets (the header names differ by language).
COL = {"id": 0, "complaint": 1, "start_dx": 2, "age": 3, "sex": 4, "onset": 5, "character": 6, "timing": 7,
       "modifiers": 8, "severity": 9, "associated_1": 10, "associated_2": 11, "pmh": 12, "lifestyle": 13,
       "start_urgency": 14, "supportive": 15, "urgency_update": 16, "urgency_post_urgency": 17, "dx_update": 18,
       "post_dx": 19, "dx_post_urgency": 20, "consultant": 21, "nurse": 22, "patient": 23}
EN_HEADERS = {"id": "case_id", "start_dx": "baseline_working_diagnosis", "start_urgency": "baseline_urgency",
              "supportive": "CC_both", "urgency_update": "DC_Urgency", "urgency_post_urgency": "DC_urgency_outcome",
              "dx_update": "DC_Dx", "post_dx": "DC_DxOutcome", "dx_post_urgency": "DC_DxOutcomeUrgency",
              "nurse": "nurse_text_4_lines", "patient": "patient_text_4_lines"}
PATIENT_NOTE = "the update in the patient's voice, from the sheet's patient-voice column beside the note-style update"
NEUTRAL_NOTE = "the neutral fact: one fixed sentence per language and voice, the same in every vignette (neutral_fact.json)"
NONE_WORDS = {"none", "n/a", "na", "nil", "-", ""}
SLOT_OF = {"supportive": "supportive", "urgency_update": "discordant_urgency",
           "reassuring_update": "discordant_reassure", "dx_update": "discordant_dx"}
# Optional columns after the fixed ones, found by heading (any of the names listed, compared without case).
PATIENT_HEADERS = {"supportive": ["CC_both_patient", "CC_both_pt"], "urgency_update": ["DC_Urgency_patient"],
                   "dx_update": ["DC_Dx_patient"], "reassuring_update": ["RC_urgency_patient"]}
ACCEPT_HEADER = "baseline_accepted_diagnosis_names"
OPTIONAL = {"accept": [ACCEPT_HEADER], "reassuring_update": ["RC_Urgency"],
            "reassuring_post_urgency": ["RC_urgency_outcome"],
            **{f"pt:{key}": names for key, names in PATIENT_HEADERS.items()}}
# A post-update diagnosis cell may carry accepted names on a second line: "Name\nAccepted alternatives: a; b".
ACCEPT_LABELS = ("accepted alternatives", "可接受的其他名称", "許容される別名")
REVIEW_LABELS = ("review note", "待审核", "要検討")
SEVERAL = re.compile(r";|；|/|\bor\b|、|または|或")
NEUTRAL_VOICES = ("clinician", "patient")


def clean(x) -> str | None:
    """Text of a cell: lines stripped, runs of spaces collapsed, blank lines dropped."""
    if x is None:
        return None
    if isinstance(x, float) and x == int(x):
        x = int(x)
    lines = [" ".join(str(line).split()) for line in str(x).replace("\r", "\n").split("\n")]
    out = "\n".join(line for line in lines if line)
    return out or None


def none_like(text: str | None) -> bool:
    """True for an empty cell and for "None", "N/A", "N/A (diagnosis unchanged)" and the like."""
    low = (text or "").strip().lower()
    return low in NONE_WORDS or low.startswith("n/a")


def severity(x, notes: list[str], vid: str) -> str | None:
    """A severity score typed as 5/10 is stored by the spreadsheet as a date (5 October): read it back."""
    if isinstance(x, (dt.datetime, dt.date)):
        notes.append(f"{vid}: severity cell holds the date {x:%Y-%m-%d}; read as {x.day}/{x.month}")
        return f"{x.day}/{x.month}"
    return clean(x)


def read_sheet(path: Path) -> list[list]:
    import openpyxl  # noqa: PLC0415
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = [list(r) for r in ws.iter_rows(values_only=True) if any(c is not None and str(c).strip() for c in r)]
    width = max(max(COL.values()) + 1, max((len(r) for r in rows), default=0))
    return [r + [None] * (width - len(r)) for r in rows]


def optional_columns(header: list, like: dict[str, int] | None = None) -> dict[str, int]:
    """Column key -> position, for the optional columns this sheet has (the keys of OPTIONAL). `like` gives
    an English sheet's positions, used where this sheet's own heading is not one of the known names."""
    names = {(clean(h) or "").lower(): i for i, h in enumerate(header) if h is not None and i > max(COL.values())}
    out = {}
    for key, options in OPTIONAL.items():
        hit = next((names[o.lower()] for o in options if o.lower() in names), None)
        if hit is None and like and key in like and like[key] < len(header) and clean(header[like[key]]):
            hit = like[key]
        if hit is not None:
            out[key] = hit
    return out


def split_names(text: str | None) -> list[str]:
    """Names from a cell that lists them with semicolons. A remark in brackets at the end of a name is dropped."""
    out = []
    for part in re.split(r"[;；]", text or ""):
        name = re.sub(r"\s*[（(][^（()）]*[)）]\s*$", "", " ".join(part.split())).strip(" .。")
        if name and name.lower() not in {n.lower() for n in out}:
            out.append(name)
    return out


def diagnosis_cell(text: str | None, where: str, notes: list[str]) -> tuple[str | None, list[str]]:
    """(name, accepted names) from a post-update diagnosis cell.

    The first line is the name. A line that starts "Accepted alternatives:" lists accepted names. A line that
    starts "Review note:" is left out of the name and reported. Nothing is decided here: a first line that
    still reads as several diagnoses is imported as it stands and reported.
    """
    if not text:
        return None, []
    name, accept = None, []
    for line in text.split("\n"):
        m = re.match(r"\s*([^:：]{1,40})[:：](.*)$", line)
        low, rest = (m.group(1).strip().lower(), m.group(2)) if m else ("", "")
        if low in ACCEPT_LABELS:
            raw = [" ".join(x.split()) for x in re.split(r"[;；]", rest) if x.strip()]
            accept += split_names(rest)
            if any(re.search(r"[（(][^（()）]*[)）]\s*$", x) for x in raw):
                notes.append(f"{where}: a remark in brackets inside the accepted names was dropped: {rest.strip()!r}")
        elif low in REVIEW_LABELS:
            notes.append(f"{where}: the cell carries an unresolved review note: {rest.strip()!r}")
        elif name is None:
            name = line.strip()
        else:
            notes.append(f"{where}: extra line in the diagnosis cell ignored: {line!r}")
    if name and SEVERAL.search(name):
        notes.append(f"{where}: the reference diagnosis {name!r} reads as several diagnoses; it is imported as one "
                     f"name, so only the diagnosis judge can match it")
    return name, accept


def new_id(raw: str) -> str:
    m = re.fullmatch(r"V0*(\d+)", raw.strip())
    if not m:
        raise ValueError(f"case id {raw!r} is not of the form V001")
    return f"V{int(m.group(1)):02d}"


def clerking(f: dict) -> str:
    """The structured English case as one third-person text: the source every version is compared with."""
    parts = [f"{f['age']}-year-old {f['sex'].lower()}.", f"Presenting complaint: {f['complaint']}.",
             f"Onset and duration: {f['onset']}.", f"Character: {f['character']}.", f"Timing: {f['timing']}.",
             f"Exacerbating or relieving factors: {f['modifiers']}.", f"Severity: {f['severity']}.",
             f"Associated: {f['associated_1']}; {f['associated_2']}.", f"Past medical history: {f['pmh']}.",
             f"Lifestyle: {f['lifestyle']}."]
    return " ".join(parts)


def _unique(names: list[str], main: str | None) -> list[str]:
    seen, out = {(main or "").lower()}, []
    for n in names:
        if n.lower() not in seen:
            seen.add(n.lower())
            out.append(n)
    return out


def _level(raw, notes: list[str], where: str) -> str | None:
    val = (clean(raw) or "").upper()
    if raw is not None and str(raw) != val:
        notes.append(f"{where} cell is {str(raw)!r}; read as {val!r}")
    return val if val in URGENCY_LEVELS else (val or None)


def neutral_problems(neutral: dict, langs) -> list[str]:
    return [f"neutral fact: no {voice} text for {lang}" for lang in langs for voice in NEUTRAL_VOICES
            if not ((neutral.get(lang) or {}).get(voice) or "").strip()]


def convert(paths: dict, scale_version: str, status: str, patient_update_status: str = "draft",
            neutral: dict | None = None, neutral_status: str = "draft") -> tuple[list[dict], list[dict], list[str]]:
    """paths: language -> one spreadsheet, or a list of them (the main sheet, then any further set of rows).
    neutral: language -> {"clinician": text, "patient": text}, the fixed neutral fact; None for no neutral arm."""
    notes: list[str] = []
    files = {lang: (list(p) if isinstance(p, (list, tuple)) else [p]) for lang, p in paths.items()}
    tables = {lang: [read_sheet(Path(p)) for p in ps] for lang, ps in files.items()}
    en_cols = []
    for rows in tables["en"]:
        for key, name in EN_HEADERS.items():
            got = clean(rows[0][COL[key]])
            if got != name:
                raise ValueError(f"English sheet: column {COL[key] + 1} is headed {got!r}, expected {name!r}; "
                                 f"the column order has changed, so the importer must be updated")
        en_cols.append((len([h for h in rows[0] if h is not None]), optional_columns(rows[0])))
    if neutral is not None:
        problems = neutral_problems(neutral, files)
        if problems:
            raise ValueError("; ".join(problems))

    rows_by_lang: dict[str, dict[str, tuple[list, dict]]] = {}
    for lang, tabs in tables.items():
        rows_by_lang[lang] = {}
        for n, rows in enumerate(tabs):
            if lang == "en":
                cols = en_cols[n][1]
            else:
                width = len([h for h in rows[0] if h is not None])
                like = next((c for w, c in en_cols if w == width), en_cols[0][1])
                cols = optional_columns(rows[0], like)
            if n == 0:
                missing_cols = [PATIENT_HEADERS[key][0] for key in ("supportive", "urgency_update", "dx_update")
                                if f"pt:{key}" not in cols]
                if missing_cols:
                    notes.append(f"{lang} sheet: no column headed {', '.join(missing_cols)}: the patient is given "
                                 f"the note-style update there")
            for r in rows[1:]:
                vid = new_id(str(r[COL["id"]]))
                if vid in rows_by_lang[lang]:
                    raise ValueError(f"{lang} sheet: case {vid} appears twice")
                rows_by_lang[lang][vid] = (r, cols)

    vignettes, assets = [], []
    gen = f"imported from the clinical spreadsheets on {time.strftime('%d %b %Y')}"
    pgen = f"{gen}; {PATIENT_NOTE}"
    for vid, (r, cols) in rows_by_lang["en"].items():
        f = {k: clean(r[i]) for k, i in COL.items()}
        f["severity"] = severity(r[COL["severity"]], notes, vid)
        missing = [k for k in ("complaint", "start_dx", "age", "sex", "onset", "character", "timing", "modifiers",
                               "severity", "associated_1", "associated_2", "pmh", "lifestyle") if not f[k]]
        if missing:
            notes.append(f"{vid}: empty cell(s) in the English sheet: {', '.join(missing)}")
            f.update({k: f[k] or "not stated" for k in missing})
        has = {"supportive": True, "urgency_update": not none_like(f["urgency_update"]),
               "dx_update": not none_like(f["dx_update"]),
               "reassuring_update": "reassuring_update" in cols and not none_like(clean(r[cols["reassuring_update"]]))}
        if not has["urgency_update"]:
            notes.append(f"{vid}: the urgency-update cell is {f['urgency_update']!r}: imported with no urgency-only update")
        if not has["dx_update"]:
            notes.append(f"{vid}: the diagnosis-update cell is {f['dx_update']!r}: imported with no diagnosis update")
        urg = {"start_urgency": _level(r[COL["start_urgency"]], notes, f"{vid}: start_urgency")}
        if has["urgency_update"]:
            urg["urgency_post_urgency"] = _level(r[COL["urgency_post_urgency"]], notes, f"{vid}: urgency_post_urgency")
        if has["dx_update"]:
            urg["dx_post_urgency"] = _level(r[COL["dx_post_urgency"]], notes, f"{vid}: dx_post_urgency")
        if has["reassuring_update"]:
            urg["reassuring_post_urgency"] = (_level(r[cols["reassuring_post_urgency"]], notes,
                                                     f"{vid}: reassuring_post_urgency")
                                              if "reassuring_post_urgency" in cols else None)

        # Accepted names. The English names come first; the Chinese and Japanese sheets' own names for the same
        # diagnoses follow, so that an answer in those languages can match without the judge.
        post_dx, post_accept = (diagnosis_cell(f["post_dx"], f"{vid} en post-update diagnosis", notes)
                                if has["dx_update"] else (None, []))
        start_accept = split_names(clean(r[cols["accept"]])) if "accept" in cols else []
        for lang in files:
            if lang == "en" or vid not in rows_by_lang[lang]:
                continue
            lr, lcols = rows_by_lang[lang][vid]
            start_accept += [clean(lr[COL["start_dx"]])] if clean(lr[COL["start_dx"]]) else []
            if "accept" in lcols:
                start_accept += split_names(clean(lr[lcols["accept"]]))
            if has["dx_update"] and not none_like(clean(lr[COL["post_dx"]])):
                other_dx, other_accept = diagnosis_cell(clean(lr[COL["post_dx"]]), "", [])
                post_accept += ([other_dx] if other_dx else []) + other_accept
        start_accept, post_accept = _unique(start_accept, f["start_dx"]), _unique(post_accept, post_dx)
        both = ({n.lower() for n in [f["start_dx"] or "", *start_accept]}
                & {n.lower() for n in [post_dx or "", *post_accept]}) - {""}
        if both:
            notes.append(f"{vid}: the same name is accepted before and after the diagnosis update: {sorted(both)}")

        rec = {
            "id": vid, "source_id": clean(r[COL["id"]]),
            "clerking": clerking(f),
            "start_dx": f["start_dx"], "start_accept": start_accept, "start_urgency": urg["start_urgency"],
            "urgency_scale_version": scale_version,
            "supportive_update": f["supportive"],
            "urgency_update": f["urgency_update"] if has["urgency_update"] else None,
            "urgency_post_urgency": urg.get("urgency_post_urgency"),
            "dx_update": f["dx_update"] if has["dx_update"] else None,
            "post_dx": post_dx, "post_accept": post_accept, "dx_post_urgency": urg.get("dx_post_urgency"),
            "uncertainty": None,
            "source": {k: f[k] for k in ("complaint", "age", "sex", "onset", "character", "timing", "modifiers",
                                         "severity", "associated_1", "associated_2", "pmh", "lifestyle")},
        }
        if has["reassuring_update"]:
            rec["reassuring_update"] = clean(r[cols["reassuring_update"]])
            rec["reassuring_post_urgency"] = urg["reassuring_post_urgency"]
        if neutral is not None:
            rec["neutral_update"] = neutral["en"]["clinician"].strip()
        vignettes.append(rec)

        for lang in files:
            if vid not in rows_by_lang[lang]:
                notes.append(f"{vid}: no row in the {lang} sheet")
                continue
            lr, lcols = rows_by_lang[lang][vid]
            for persp in ("patient", "nurse", "consultant"):
                texts = {"opening": clean(lr[COL[persp]])}
                reworded = set()
                for col, slot in SLOT_OF.items():
                    if not has[col]:
                        continue
                    pos = COL.get(col, lcols.get(col))
                    texts[slot] = clean(lr[pos]) if pos is not None else None
                    if persp == "patient" and f"pt:{col}" in lcols:
                        own = clean(lr[lcols[f"pt:{col}"]])
                        if own:
                            texts[slot] = own
                            reworded.add(slot)
                        else:
                            notes.append(f"{vid} {lang} patient {slot}: the {PATIENT_HEADERS[col][0]} cell is empty; "
                                         f"the note-style update is used")
                for slot, text in texts.items():
                    if not text:
                        notes.append(f"{vid} {lang} {persp} {slot}: empty cell")
                        continue
                    own = slot in reworded
                    assets.append({"vignette": vid, "perspective": persp, "language": lang, "slot": slot,
                                   "text": text, "status": patient_update_status if own else status,
                                   "generator": pgen if own else gen})
                if neutral is not None:
                    voice = "patient" if persp == "patient" else "clinician"
                    assets.append({"vignette": vid, "perspective": persp, "language": lang, "slot": "neutral",
                                   "text": neutral[lang][voice].strip(), "status": neutral_status,
                                   "generator": NEUTRAL_NOTE})
    for lang in files:
        extra = sorted(set(rows_by_lang[lang]) - set(rows_by_lang["en"]))
        if extra:
            notes.append(f"{lang} sheet has rows with no English row: {', '.join(extra)}")
    return vignettes, assets, notes


def _language(name: str) -> str:
    name = name.lower()
    return "ja" if "japanese" in name else "zh" if ("mandarin" in name or "chinese" in name) else "en"


def find_files(folder: Path) -> dict[str, list[Path]]:
    """language -> the main sheet in the folder, then the sheet in its "reversal" subfolder if there is one."""
    out: dict[str, list[Path]] = {}
    for sub in (folder, folder / "reversal"):
        seen = {}
        for p in sorted(sub.glob("*.xlsx")) if sub.is_dir() else []:
            lang = _language(p.name)
            if lang in seen:
                raise ValueError(f"two files look like the {lang} sheet: {seen[lang].name} and {p.name}")
            seen[lang] = p
            out.setdefault(lang, []).append(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=None, help="folder holding the three spreadsheets")
    ap.add_argument("--en", default=None)
    ap.add_argument("--zh", default=None)
    ap.add_argument("--ja", default=None)
    ap.add_argument("--scenarios", default=str(ROOT / "scenarios"))
    ap.add_argument("--status", default="approved", choices=ASSET_STATUSES,
                    help="status given to every imported text (default approved: the sheets are the signed-off source)")
    ap.add_argument("--patient-update-status", default="draft", choices=ASSET_STATUSES,
                    help="status given to the patient-voice updates from the patient-voice columns (default draft)")
    ap.add_argument("--neutral-file", default=None,
                    help="the fixed neutral fact (default: neutral_fact.json in --dir, if it is there)")
    ap.add_argument("--neutral-status", default="draft", choices=ASSET_STATUSES,
                    help="status given to the neutral fact (default draft)")
    args = ap.parse_args(argv)
    try:
        paths = find_files(Path(args.dir)) if args.dir else {}
        for lang in ("en", "zh", "ja"):
            if getattr(args, lang):
                paths[lang] = [Path(getattr(args, lang))]
        if "en" not in paths:
            raise ValueError("the English spreadsheet is needed (--en or --dir)")
        nfile = Path(args.neutral_file) if args.neutral_file else (Path(args.dir) / "neutral_fact.json" if args.dir else None)
        neutral = read_json(nfile)["texts"] if nfile is not None and nfile.exists() else None
        if args.neutral_file and neutral is None:
            raise ValueError(f"no such file: {args.neutral_file}")
        cfg = load_config()
        vignettes, assets, notes = convert(paths, cfg["urgency_scale_version"], args.status, args.patient_update_status,
                                           neutral, args.neutral_status)
    except (ValueError, OSError, KeyError) as e:
        print(f"CANNOT IMPORT: {e}")
        return 2
    d = Path(args.scenarios)
    for name in ("vignettes.json", "assets.json"):
        if (d / name).exists():
            shutil.copyfile(d / name, d / (name + ".bak"))
    write_json(d / "vignettes.json", {"format_version": 2, "vignettes": vignettes})
    write_json(d / "assets.json", {"format_version": 2, "assets": assets})
    n_own = sum(PATIENT_NOTE in a["generator"] for a in assets)
    n_neutral = sum(a["slot"] == "neutral" for a in assets)
    lines = [f"# Import report, {time.strftime('%Y-%m-%d %H:%M')}", "",
             *(f"- {lang}: " + ", ".join(f"`{p.name}`" for p in ps) for lang, ps in paths.items()), "",
             f"{len(vignettes)} vignettes, {len(assets)} texts, status `{args.status}`, urgency scale "
             f"{cfg['urgency_scale_version']}.", "",
             f"{n_own} of the texts are updates in the patient's voice, from the patient-voice columns, with status "
             f"`{args.patient_update_status}`.", "",
             (f"{n_neutral} of the texts are the neutral fact (one fixed sentence per language and voice, from "
              f"`{nfile.name}`), with status `{args.neutral_status}`." if neutral is not None
              else "No neutral fact was given, so no vignette has a neutral update."), "",
             "## Noticed while importing", ""]
    lines += [f"- {n}" for n in notes] or ["Nothing."]
    write_text(d / "import_report.md", "\n".join(lines) + "\n")
    print(f"imported {len(vignettes)} vignettes and {len(assets)} texts into {d} "
          f"({n_own} patient-voice updates, status {args.patient_update_status}; "
          f"{n_neutral} neutral-fact texts, status {args.neutral_status})")
    for n in notes:
        print(f"  note: {n}")
    print("next: python -m src.assets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
