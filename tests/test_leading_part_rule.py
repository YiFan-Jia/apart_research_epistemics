"""The leading-part rule of the diagnosis judge: a string is judged by the part before its first qualifier."""
from src.judge import DEFER, DiagnosisJudge, leading_part, tail_reading

GOLD = {"start_dx": "Migraine", "start_accept": ["migraine without aura"], "post_dx": "Subarachnoid haemorrhage",
        "post_accept": [], "changed": "both", "accepted_names_version": "t1"}


def judge(head_rule=True):
    return DiagnosisJudge(None, "p1", None, offline_name="reader", head_rule=head_rule)


def test_leading_part_splits_at_the_first_qualifier():
    assert leading_part("Migraine attack (with vomiting); dissection not excluded")[0] == "Migraine attack"
    assert leading_part("Migraine") == ("Migraine", "", False)
    assert leading_part("Migraine or tension headache")[1] == ""          # "A or B" is one leading part
    assert leading_part("Stenosis with claudication")[2] is True           # a "with"-like split
    assert tail_reading("; dissection not yet excluded")["alternatives"]
    assert tail_reading("(likely)")["uncertain"] and not tail_reading(", likely bacterial")["uncertain"]
    assert not tail_reading("(with vomiting)")["alternatives"]


def test_an_accepted_leading_part_settles_the_string_and_the_method_says_so():
    j = judge()
    r = j.judge("V1", GOLD, "Migraine (with vomiting); subarachnoid haemorrhage not yet excluded")
    assert (r["leading"], r["method"], r["hedged"]) == ("start", "head_exact", True)
    assert judge(head_rule=False).judge("V1", GOLD, "Migraine (with vomiting)")["method"] == "unjudged"
    assert j.judge("V1", GOLD, "Migraine (suspected)")["uncertain"] is True


def test_an_unknown_leading_part_is_judged_once_for_all_its_strings():
    j = judge()
    items = [("V1", GOLD, "Migraine attack (with vomiting)"), ("V1", GOLD, "Migraine attack; SAH not excluded"),
             ("V1", GOLD, "Migraine attack")]
    assert [t for _, _, t in j.pending(items)] == ["Migraine attack"]
    j.store_offline("V1", GOLD, "Migraine attack", {"leading": "start", "leading_name": "", "modifiers": [],
                                                     "alternatives": [], "uncertain": False})
    assert j.pending(items) == []
    got = [j.judge(*it) for it in items]
    assert [g["method"] for g in got] == ["head_model", "head_model", "model"]
    assert [g["hedged"] for g in got] == [False, True, False]


def test_a_with_split_that_names_a_reference_diagnosis_is_read_whole():
    j = judge()
    text = "Thunderclap headache with subarachnoid haemorrhage"
    assert j.unit("V1", GOLD, text) == text
    assert j.unit("V1", GOLD, "Migraine with vomiting") == "Migraine"


def test_a_deferred_leading_part_sends_its_strings_to_a_whole_reading():
    j = judge()
    items = [("V1", GOLD, "Uncertain; migraine most likely")]
    assert [t for _, _, t in j.pending(items)] == ["Uncertain"]
    j.defer("V1", GOLD, "Uncertain")
    assert [t for _, _, t in j.pending(items)] == ["Uncertain; migraine most likely"]
    assert DEFER == "defer"
