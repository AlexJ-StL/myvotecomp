import pytest

from ingest.geography import normalize_state_fips


def test_state_fips_normalization_accepts_codes_names_and_abbreviations() -> None:
    assert normalize_state_fips("1") == "01"
    assert normalize_state_fips("28") == "28"
    assert normalize_state_fips("al") == "01"
    assert normalize_state_fips("District of Columbia") == "11"
    assert normalize_state_fips("U.S. Virgin Islands") == "78"


def test_state_fips_normalization_rejects_unknown_and_out_of_range_codes() -> None:
    for value in ("000", "99", "Atlantis", ""):
        with pytest.raises(ValueError, match="Unknown state or FIPS code"):
            normalize_state_fips(value)
