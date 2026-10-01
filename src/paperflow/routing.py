from paperflow.models import (
    Publisher,
    Route,
    RouteDecision,
)
from paperflow.utils.doi import normalize_doi


def route_doi(value: str) -> RouteDecision:
    """
    Determine the PaperFlow V2 processing route for a DOI.

    Supported scope:

    - 10.1016/... -> Elsevier structured XML
    - 10.1007/s12273... -> Building Simulation PDF
    - 10.1038/... -> Nature / Nature Portfolio JATS

    Other publishers and Springer journals are intentionally
    outside the current PaperFlow V2 scope.
    """

    doi = normalize_doi(value)

    if doi.startswith("10.1016/"):
        return RouteDecision(
            doi=doi,
            publisher=Publisher.ELSEVIER,
            route=Route.ELSEVIER,
            supported=True,
            reason="Elsevier DOI supported by PaperFlow V2.",
        )

    if doi.startswith("10.1007/s12273"):
        return RouteDecision(
            doi=doi,
            publisher=Publisher.SPRINGER_NATURE,
            route=Route.BUILDING_SIMULATION,
            supported=True,
            reason=("Building Simulation DOI supported by PaperFlow V2."),
        )

    if doi.startswith("10.1038/"):
        return RouteDecision(
            doi=doi,
            publisher=Publisher.SPRINGER_NATURE,
            route=Route.NATURE,
            supported=True,
            reason=("Nature Portfolio DOI supported by PaperFlow V2."),
        )

    if doi.startswith("10.1007/"):
        return RouteDecision(
            doi=doi,
            publisher=Publisher.SPRINGER_NATURE,
            route=Route.UNSUPPORTED,
            supported=False,
            reason=(
                "Springer DOI recognized, but PaperFlow V2 "
                "currently supports only Building Simulation "
                "(10.1007/s12273...)."
            ),
        )

    return RouteDecision(
        doi=doi,
        publisher=Publisher.UNKNOWN,
        route=Route.UNSUPPORTED,
        supported=False,
        reason=("No PaperFlow V2 route exists for this DOI."),
    )
