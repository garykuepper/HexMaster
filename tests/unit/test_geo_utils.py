from hexmaster.utils.geo_utils import calculate_distance


def test_calculate_distance_basic():
    """Test distance between two identical points is 0."""
    town1 = {"q": 1, "r": 1, "x": 0.5, "y": 0.5}
    town2 = {"q": 1, "r": 1, "x": 0.5, "y": 0.5}
    assert calculate_distance(town1, town2) == 0.0


def test_calculate_distance_known_values():
    """Test distance between two different points."""
    # These are arbitrary but consistent values to test logic
    town1 = {"q": 10, "r": 20, "x": 0.2, "y": 0.8}
    town2 = {"q": 12, "r": 22, "x": 0.5, "y": 0.3}

    dist = calculate_distance(town1, town2)
    assert dist > 0
    # Expected value based on formula:
    # x1 = 10 * 1.5 + (0.2 - 0.5) * 2.0 = 15 - 0.6 = 14.4
    # y1 = 20 * 1.73205 + (0.8 - 0.5) * 1.73205 = 34.641 + 0.519615 = 35.160615
    # x2 = 12 * 1.5 + (0.5 - 0.5) * 2.0 = 18
    # y2 = 22 * 1.73205 + (0.3 - 0.5) * 1.73205 = 38.1051 - 0.34641 = 37.75869
    # dx = 18 - 14.4 = 3.6
    # dy = 37.75869 - 35.160615 = 2.598075
    # dist = sqrt(3.6^2 + 2.598075^2) = sqrt(12.96 + 6.75) = sqrt(19.71) ~= 4.439
    assert round(dist, 3) == 4.440


def test_calculate_distance_invalid_input():
    """Test that missing keys return 0.0."""
    town1 = {"q": 1, "r": 1}
    town2 = {"q": 1, "r": 1, "x": 0.5, "y": 0.5}
    assert calculate_distance(town1, town2) == 0.0
