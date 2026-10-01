from paperflow.models import Publisher, Route
from paperflow.routing import route_doi


def test_elsevier_route():
    result = route_doi("10.1016/j.buildenv.2025.113229")

    assert result.doi == ("10.1016/j.buildenv.2025.113229")

    assert result.publisher == Publisher.ELSEVIER
    assert result.route == Route.ELSEVIER
    assert result.supported is True


def test_elsevier_url_route():
    result = route_doi("https://doi.org/10.1016/j.buildenv.2026.114205")

    assert result.publisher == Publisher.ELSEVIER
    assert result.route == Route.ELSEVIER
    assert result.supported is True


def test_building_simulation_route():
    result = route_doi("10.1007/s12273-026-1484-2")

    assert result.publisher == Publisher.SPRINGER_NATURE

    assert result.route == Route.BUILDING_SIMULATION

    assert result.supported is True


def test_other_springer_is_not_supported():
    result = route_doi("10.1007/s00134-026-00000-0")

    assert result.publisher == Publisher.SPRINGER_NATURE

    assert result.route == Route.UNSUPPORTED
    assert result.supported is False


def test_nature_route():
    result = route_doi("10.1038/s41467-019-11026-x")

    assert result.publisher == Publisher.SPRINGER_NATURE

    assert result.route == Route.NATURE
    assert result.supported is True


def test_unknown_route():
    result = route_doi("10.5555/example-doi")

    assert result.publisher == Publisher.UNKNOWN
    assert result.route == Route.UNSUPPORTED
    assert result.supported is False
