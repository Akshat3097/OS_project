"""Every VIT BCSE303L past-paper question in the bank must match its official answer key,
except where the key itself has a documented arithmetic slip (then the Gantt chart / completion
times must still match)."""
from engine import question_bank

KNOWN_KEY_ERRORS = {"CAT1-2025C2-Q4-FCFS", "CAT1-2025C2-Q4-SJF", "CAT1-2025C2-Q4-SRTF", "CAT2-2024B2-Q1-BANKERS"}


def test_bank_loads():
    items = question_bank.load()
    assert len(items) >= 20


def test_engine_matches_answer_keys():
    papers = [i for i in question_bank.load() if not question_bank.is_notes_example(i)]   # notes: test_teacher_notes.py
    for row in map(question_bank.check, papers):
        if row["id"] in KNOWN_KEY_ERRORS:
            structural = [ok for name, ok in row["checks"] if name in ("completion times", "safe/unsafe",
                                                                       "official sequence is valid")]
            assert structural and all(structural), row
            assert row["notes"], row["id"]
        else:
            assert row["match"] is not False, row


def test_every_item_builds_a_problem():
    for it in question_bank.load():
        question_bank.to_problem(it).solve()
