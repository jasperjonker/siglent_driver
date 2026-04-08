from siglent_driver.siglent import _siglent_mode_token


def test_mode_token_mapping():
    assert _siglent_mode_token("current") == "CURRent"
    assert _siglent_mode_token("voltage") == "VOLTage"
    assert _siglent_mode_token("power") == "POWer"
    assert _siglent_mode_token("resistance") == "RESistance"
    assert _siglent_mode_token("led") == "LED"
