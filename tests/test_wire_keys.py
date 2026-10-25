"""Thermostat wire names stay in the heating parser."""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "custom_components" / "salus_it600_cloud"
WIRE = "ep9:sIT600TH:"
FENCED = ("climate.py", "sensor.py", "binary_sensor.py", "coordinator.py", "state.py")


def test_platforms_do_not_name_thermostat_wire_keys() -> None:
    for name in FENCED:
        text = (PACKAGE / name).read_text()
        assert WIRE not in text, name


def test_cube_names_no_host_and_no_wire_keys() -> None:
    text = (PACKAGE / "cube.py").read_text()
    lowered = text.lower()
    assert WIRE not in text
    assert "http://" not in lowered
    assert "https://" not in lowered
    assert "salusconnect" not in lowered


def test_live_poll_does_not_import_cube() -> None:
    for name in ("coordinator.py", "__init__.py"):
        text = (PACKAGE / name).read_text()
        assert "from .cube" not in text
        assert "import cube" not in text
