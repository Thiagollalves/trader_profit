from trader_profit.config import load_config


def test_load_config_disables_live_by_default():
    config = load_config({"TRADER_PROFIT_MODE": "live"})

    assert config.requested_mode.value == "live"
    assert config.mode.value == "simulation"
    assert config.live_enabled is False
