from app.versions import compare, satisfies


def test_compare_single_digit():
    assert compare("1.3.0", "1.2.9") == 1


def test_satisfies_range():
    assert satisfies("1.5.2", ">=1.4, <2.0")
