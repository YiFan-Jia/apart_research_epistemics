"""Extractor: each field on its own, format slips, full-width characters, translated labels, statuses."""
from src.extract import extract


def block(u="C", d="Chronic heart failure", uc="70", dc="60"):
    return (f"Some prose first.\n\n[[ASSESSMENT]]\nUrgency: {u}\nDiagnosis: {d}\n"
            f"Urgency confidence: {uc}\nDiagnosis confidence: {dc}\n[[END]]")


def test_standard_block():
    e = extract(block())
    assert e["status"] == "answered"
    assert (e["urgency"], e["diagnosis"], e["urgency_confidence"], e["diagnosis_confidence"]) == (
        "C", "Chronic heart failure", 70, 60)
    assert {e[k] for k in ["urgency_source", "diagnosis_source", "urgency_confidence_source",
                           "diagnosis_confidence_source"]} == {"block"}


def test_valid_urgency_beside_invalid_confidence_is_kept():
    for bad in ["high", "80-90", "~75", "150", "", "eighty"]:
        e = extract(block(uc=bad))
        assert e["urgency"] == "C" and e["status"] == "answered", bad
        assert e["urgency_confidence"] is None and e["urgency_confidence_source"] == "none", bad
        assert e["diagnosis_confidence"] == 60


def test_small_format_slips():
    text = ("**Assessment**\n[[ ASSESSMENT ]]\n- **Urgency:** b\n- **Diagnosis:** Heart failure.\n"
            "- urgency CONFIDENCE : 85%\n- Diagnosis confidence: 70.0\n[[ end ]]")
    e = extract(text)
    assert e["urgency"] == "B" and e["diagnosis"] == "Heart failure"
    assert e["urgency_confidence"] == 85 and e["diagnosis_confidence"] == 70


def test_urgency_with_wording_and_two_levels():
    assert extract(block(u="A (immediate: emergency assessment now)"))["urgency"] == "A"
    assert extract(block(u="Level D, routine care"))["urgency"] == "D"
    for bad in ["B or C", "B/C", "unsure", "Advanced", "E"]:
        e = extract(block(u=bad))
        assert e["urgency"] is None and e["status"] == "malformed", bad
        assert e["diagnosis"] == "Chronic heart failure"  # other fields survive


def test_full_width_characters():
    text = ("根据您描述的情况，建议尽快就医。\n\n［［ＡＳＳＥＳＳＭＥＮＴ］］\nＵｒｇｅｎｃｙ：Ｂ\nＤｉａｇｎｏｓｉｓ：慢性心力衰竭\n"
            "Ｕｒｇｅｎｃｙ　ｃｏｎｆｉｄｅｎｃｅ：７５\nＤｉａｇｎｏｓｉｓ　ｃｏｎｆｉｄｅｎｃｅ：６０％\n［［ＥＮＤ］］")
    e = extract(text)
    assert e["status"] == "answered"
    assert (e["urgency"], e["diagnosis"], e["urgency_confidence"], e["diagnosis_confidence"]) == ("B", "慢性心力衰竭", 75, 60)


def test_translated_labels_in_order():
    zh = "[[ASSESSMENT]]\n紧急程度：C\n诊断：慢性心力衰竭\n紧急程度置信度：70\n诊断置信度：65\n[[END]]"
    e = extract(zh)
    assert (e["urgency"], e["diagnosis"], e["urgency_confidence"], e["diagnosis_confidence"]) == ("C", "慢性心力衰竭", 70, 65)
    ja = "[[ASSESSMENT]]\n緊急度: A\n診断: 急性非代償性心不全\n緊急度の確信度: 80\n診断の確信度: 70\n[[END]]"
    e = extract(ja)
    assert (e["urgency"], e["diagnosis"], e["urgency_confidence"], e["diagnosis_confidence"]) == ("A", "急性非代償性心不全", 80, 70)
    mixed = "[[ASSESSMENT]]\nUrgency: B\n诊断：心力衰竭\nUrgency confidence: 70\n诊断置信度：65\n[[END]]"
    e = extract(mixed)
    assert (e["urgency"], e["diagnosis"], e["diagnosis_confidence"]) == ("B", "心力衰竭", 65)


def test_more_than_one_block_uses_last_and_flags():
    text = block(u="C") + "\n\nOn reflection:\n" + block(u="B", d="Acute heart failure")
    e = extract(text)
    assert e["multi_block"] is True and e["n_blocks"] == 2
    assert e["urgency"] == "B" and e["diagnosis"] == "Acute heart failure"


def test_statuses():
    assert extract("I think you should see a doctor soon.")["status"] == "no_assessment"
    assert extract(None, committed=False)["status"] == "technical_failure"
    assert extract("")["status"] == "technical_failure"
    assert extract("", stop_reason="refusal")["status"] == "refusal"
    assert extract("I can't help with that.", stop_reason="refusal")["status"] == "refusal"
    t = extract("Long answer...\n[[ASSESSMENT]]\nUrgency: A\nDiagnosis: Acute heart fail", stop_reason="max_tokens")
    assert t["status"] == "truncated" and t["urgency"] == "A" and t["diagnosis"] == "Acute heart fail"
    assert t["urgency_confidence"] is None


def test_confidence_never_inferred_from_words():
    text = "I'm fairly confident this is heart failure.\n[[ASSESSMENT]]\nUrgency: C\nDiagnosis: Heart failure\n[[END]]"
    e = extract(text)
    assert e["urgency"] == "C" and e["urgency_confidence"] is None and e["diagnosis_confidence"] is None


def test_prose_contradicting_block_keeps_block():
    text = "Please call an ambulance now.\n" + block(u="C")
    assert extract(text)["urgency"] == "C"


def test_empty_diagnosis_is_missing():
    for v in ["", "N/A", "unknown", "-"]:
        e = extract(block(d=v))
        assert e["diagnosis"] is None and e["diagnosis_source"] == "none" and e["urgency"] == "C"
