import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.classifier import EXCEPTION_TAXONOMY, classify  # noqa: E402
from backend.matcher import MatchDecision  # noqa: E402


def test_exact_match_needs_no_exception():
    decision = MatchDecision("EXACT_MATCH", 100, "ALL_EXACT", False, {})
    assert classify(decision) is None


def test_missing_settlement_maps_correctly():
    decision = MatchDecision("MISSING_SETTLEMENT", 100, "NO_BANK_CREDIT", True, {})
    code = classify(decision)
    assert code == "MISSING_SETTLEMENT"
    assert code in EXCEPTION_TAXONOMY


def test_ambiguous_match_stays_unresolved_category():
    decision = MatchDecision("AMBIGUOUS_MATCH", 50, "MULTIPLE_COMPOSITE_CANDIDATES", True, {})
    assert classify(decision) == "AMBIGUOUS_MATCH"


def test_unknown_status_raises_instead_of_inventing_label():
    decision = MatchDecision("SOME_NEW_UNPLANNED_STATUS", 0, "X", True, {})
    try:
        classify(decision)
        assert False, "expected ValueError"
    except ValueError:
        pass
