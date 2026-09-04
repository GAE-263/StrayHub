from services.api.app.domain.personal_name import surname_of


def test_single_character_surname() -> None:
    assert surname_of("黃品翰") == "黃"


def test_compound_surname_keeps_both_characters() -> None:
    assert surname_of("歐陽靖") == "歐陽"
    assert surname_of("司馬光") == "司馬"


def test_western_name_uses_trailing_surname() -> None:
    assert surname_of("John Smith") == "Smith"
    assert surname_of("  Mary  Jane  Watson ") == "Watson"


def test_missing_or_blank_name_yields_none() -> None:
    assert surname_of(None) is None
    assert surname_of("") is None
    assert surname_of("   ") is None
