"""NORM-001 unit tests: hand-calculated expected values per contract."""
from src.normalize.gold import normalize_close


def test_goldm_uses_purity_995():
    # Close 7300.00 -> 7300 / 10 / 0.995
    assert abs(normalize_close(7300.0, 10, 0.995) - 733.6683417085427) < 1e-9


def test_goldten():
    # 7310 / 10 / 0.999
    assert abs(normalize_close(7310.0, 10, 0.999) - 731.7317317317317) < 1e-9


def test_goldguinea():
    # 5880 / 8 / 0.999 = 735.7357...
    assert abs(normalize_close(5880.0, 8, 0.999) - 735.7357357357357) < 1e-9


def test_goldpetal():
    # 735 / 1 / 0.999 = 735.7357...
    assert abs(normalize_close(735.0, 1, 0.999) - 735.7357357357357) < 1e-9


def test_scales_linearly_with_close():
    a = normalize_close(100.0, 8, 0.999)
    b = normalize_close(200.0, 8, 0.999)
    assert abs(b / a - 2.0) < 1e-12


def test_invalid_params_raise():
    try:
        normalize_close(100.0, 0, 0.999)
        assert False, "should raise"
    except ValueError:
        pass
