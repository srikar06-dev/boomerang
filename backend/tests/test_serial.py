from app.stages.serial import matches, norm


def test_lookalikes_fold_together():
    assert norm("X0O57BNA55") == norm("XOO57BNA5S")


def test_exact_and_fuzzy_match():
    assert matches("X0057BNA55", ["X0057BNA55"]) is True
    assert matches("X0057BNA55", ["X0057BNA56"]) is True        # one misread character
    assert matches("X0057BNA55", ["X0057BN55"]) is True         # one dropped character


def test_shipped_serial_found_among_other_label_codes():
    assert matches("X0057BNA55", ["X00285289", "MODEL-ABC", "X0057BNA55"]) is True


def test_clearly_different_serial_is_a_mismatch():
    assert matches("X0057BNA55", ["X00285289"]) is False


def test_nothing_readable_is_no_evidence():
    assert matches("X0057BNA55", [None, ""]) is None
    assert matches(None, ["ABC123"]) is None
