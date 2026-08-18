"""Golden execution of the urban contract over example primitives."""

from __future__ import annotations

from pathlib import Path

from umbral.application.urban.calculator import UrbanSignalCalculator
from umbral.application.urban.contract import load_urban_contract

ROOT = Path(__file__).resolve().parents[4]
CONTRACT_PATH = ROOT / "contracts" / "urban" / "v1" / "urban-contract-v1.json"


def _calculator() -> UrbanSignalCalculator:
    return UrbanSignalCalculator(load_urban_contract(CONTRACT_PATH))


def test_cafe_lifestyle_scores_density_and_distance() -> None:
    result = _calculator().calculate(
        poi_distances={
            "cafe": {
                "count_300m": [50.0, 120.0, 220.0, 280.0, 295.0],
                "nearest_m": [50.0],
            },
        }
    )
    signal = result.for_signal("cafe_lifestyle")
    assert signal is not None
    # count_300m = 5/5 = 1.0 (weight 0.60); nearest 50m <= far-ratio = 1.0 (weight 0.40)
    assert signal.value == 1.0
    assert signal.missing is False
    assert signal.inputs_present == 2
    assert signal.confidence == 1.0


def test_cafe_lifestyle_with_no_data_is_missing() -> None:
    result = _calculator().calculate(
        poi_distances={"cafe": {"count_300m": [], "nearest_m": []}}
    )
    signal = result.for_signal("cafe_lifestyle")
    assert signal is not None
    assert signal.missing is True
    assert signal.value == 0.0
    assert signal.confidence == 0.0


def test_partial_inputs_lower_confidence() -> None:
    result = _calculator().calculate(
        poi_distances={
            "cafe": {"count_300m": [100.0, 150.0], "nearest_m": [120.0]},
            # supermarket present but pharmacy/convenience/health missing
            "supermarket": {
                "count_600m": [200.0, 400.0, 550.0, 590.0, 600.0, 601.0],
                "nearest_m": [200.0],
            },
        }
    )
    daily = result.for_signal("daily_convenience")
    assert daily is not None
    # Only supermarket inputs present (1 of 4) -> confidence penalized.
    assert daily.inputs_present == 1
    assert daily.inputs_total == 4
    assert daily.confidence < 1.0
    assert daily.missing is False


def test_green_access_is_absolute() -> None:
    result = _calculator().calculate(
        poi_distances={
            "green_space": {"count_600m": [100.0, 200.0, 300.0], "nearest_m": [100.0]},
        }
    )
    signal = result.for_signal("green_access")
    assert signal is not None
    assert signal.value == 1.0  # nearest 100m <= near 150m


def test_composite_noise_risk_combines_base_signals() -> None:
    result = _calculator().calculate(
        poi_distances={
            "nightlife": {
                "count_300m": [80.0, 90.0, 100.0, 150.0, 200.0],
                "nearest_m": [80.0],
            },
        },
        linear_distances={
            "major_road": {"nearest_m": [30.0]},
            "highway": {"nearest_m": [5000.0]},
            "railway": {"nearest_m": [8000.0]},
            "subway_line": {"nearest_m": [9000.0]},
        },
    )
    noise = result.for_signal("noise_risk")
    assert noise is not None
    # nightlife_intensity=1.0, road_noise=0.6 (near major road, far highway),
    # rail_noise=0.0 (both rail lines far)
    expected = round(0.45 * 1.0 + 0.35 * 0.6 + 0.20 * 0.0, 4)
    assert noise.value == expected
    assert noise.missing is False


def test_composite_never_self_references() -> None:
    contract = load_urban_contract(CONTRACT_PATH)
    for composite in contract.composite_signals:
        assert composite.name not in composite.signal_refs


def test_reproducible_across_runs() -> None:
    calc = _calculator()
    inputs = {
        "poi_distances": {
            "cafe": {"count_300m": [50.0, 120.0, 220.0], "nearest_m": [50.0]},
        }
    }
    first = calc.calculate(**inputs)
    second = calc.calculate(**inputs)
    for name, value in first.signals.items():
        assert second.signals[name].value == value.value
        assert second.signals[name].confidence == value.confidence
