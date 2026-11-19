"""Phase 8a — static incident-report map rendering. Real matplotlib output,
not a fabricated basemap; regression-guards the honesty discipline (no
geometry -> None, never a blank/misleading image)."""
from __future__ import annotations

from types import SimpleNamespace

from varuna_integration.report_maps import render_case_map


def _case(origin=None, landfalls=None):
    starting_point = SimpleNamespace(point=origin) if origin is not None else None
    fc_value = SimpleNamespace(landfalls=landfalls or []) if landfalls is not None else None
    forecast = SimpleNamespace(value=fc_value) if fc_value is not None else None
    return SimpleNamespace(starting_point=starting_point, forecast=forecast)


def test_returns_none_when_no_geometry_at_all():
    assert render_case_map(_case()) is None


def test_returns_none_when_sections_are_entirely_absent():
    case = SimpleNamespace()
    assert render_case_map(case) is None


def test_returns_valid_png_with_only_origin():
    origin = SimpleNamespace(lon=72.6, lat=18.9)
    png = render_case_map(_case(origin=origin))
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1000


def test_returns_valid_png_with_only_landfalls():
    lf = SimpleNamespace(position=SimpleNamespace(lon=80.3, lat=13.2), location_name="Chennai coast",
                         hours_until=18.0, probability=0.4)
    png = render_case_map(_case(landfalls=[lf]))
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_returns_valid_png_with_both_origin_and_landfall():
    origin = SimpleNamespace(lon=72.6, lat=18.9)
    lf = SimpleNamespace(position=SimpleNamespace(lon=72.62, lat=18.92), location_name="Mumbai coast",
                         hours_until=12.0, probability=0.5)
    png = render_case_map(_case(origin=origin, landfalls=[lf]))
    assert png is not None
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_landfall_missing_position_is_skipped_not_crashing():
    lf_no_pos = SimpleNamespace(position=None, location_name="unknown", hours_until=1.0, probability=0.1)
    # No origin either -> genuinely no plottable geometry -> None, not a crash.
    assert render_case_map(_case(landfalls=[lf_no_pos])) is None
