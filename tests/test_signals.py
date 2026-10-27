"""SIG-002 unit tests: state machine with synthetic data."""
from src.backtest.signals import identify_trades, state_machine


def test_enter_at_threshold():
    z = [0.5, 2.2, 2.4, 1.0, 0.3]
    pos = state_machine(z, entry_z=2.0, exit_z=0.5)
    assert pos[0] == 0
    assert pos[1] == -1  # positive z -> short spread
    assert pos[2] == -1
    assert pos[3] == -1  # still holding until |z| <= exit
    assert pos[4] == 0


def test_long_spread_on_negative_z():
    z = [-2.5, -1.0, -0.4]
    pos = state_machine(z, entry_z=2.0, exit_z=0.5)
    assert pos[0] == 1 and pos[1] == 1 and pos[2] == 0


def test_no_position_on_missing_data():
    z = [2.5, None, 1.0]
    pos = state_machine(z, entry_z=2.0, exit_z=0.5)
    assert pos[0] == -1
    assert pos[1] == -1  # hold; never open on missing day; stays
    assert pos[2] == -1


def test_flip_goes_through_flat():
    z = [2.5, -3.0, 0.2]
    pos = state_machine(z, entry_z=2.0, exit_z=0.5)
    # Entry short at 2.5; -3.0 doesn't flip directly; only exits at 0.2
    assert pos[0] == -1
    assert pos[1] == -1
    assert pos[2] == 0


def test_identify_trades_groups_consecutive():
    z = [3.0, 2.5, 0.2, 0.1, -2.5, -1.0, 0.1]
    pos = state_machine(z, entry_z=2.0, exit_z=0.5)
    trades = identify_trades([i for i in range(len(pos))], pos)
    assert len(trades) == 2
    assert trades[0]["direction"] == -1
    assert trades[1]["direction"] == 1
