from umbral.urban.signals import (
    UrbanSignalCalculator,
    classify_osm_linear_feature,
    classify_osm_poi,
)


def test_osm_classifier_maps_daily_and_noise_pois():
    assert classify_osm_poi({"shop": "supermarket"}) == "supermarket"
    assert classify_osm_poi({"amenity": "pharmacy"}) == "pharmacy"
    assert classify_osm_poi({"amenity": "nightclub"}) == "nightlife"
    assert classify_osm_poi({"amenity": "cafe"}) == "cafe"


def test_osm_classifier_maps_transport_green_and_linear_features():
    assert classify_osm_poi({"railway": "station", "station": "subway"}) == "subway_station"
    assert classify_osm_poi({"highway": "bus_stop"}) == "bus_stop"
    assert classify_osm_poi({"leisure": "park"}) == "green_space"
    assert classify_osm_linear_feature({"highway": "primary"}) == "major_road"
    assert classify_osm_linear_feature({"railway": "rail"}) == "railway"


def test_urban_signal_calculator_scores_walkability_transit_noise_and_green():
    result = UrbanSignalCalculator().calculate(
        poi_distances={
            "supermarket": [180, 520],
            "pharmacy": [160],
            "convenience": [120, 400],
            "cafe": [90, 250],
            "nightlife": [80],
            "restaurant": [60, 110, 240],
            "bus_stop": [80, 160, 260],
            "subway_station": [650],
            "green_space": [300],
        },
        linear_distances={
            "major_road": [70],
            "railway": [450],
        },
    )

    assert result.signals["walkability"] >= 0.75
    assert result.signals["transit_access"] >= 0.70
    assert result.signals["noise_risk"] >= 0.65
    assert result.signals["green_access"] >= 0.60
    assert result.signals["contributors"]
