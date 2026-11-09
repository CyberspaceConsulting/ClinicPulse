from datetime import date

import holidays


FEDERAL_STATE_CODES = {
    "Baden-Württemberg": "BW",
    "Bayern": "BY",
    "Berlin": "BE",
    "Brandenburg": "BB",
    "Bremen": "HB",
    "Hamburg": "HH",
    "Hessen": "HE",
    "Mecklenburg-Vorpommern": "MV",
    "Niedersachsen": "NI",
    "Nordrhein-Westfalen": "NW",
    "Rheinland-Pfalz": "RP",
    "Saarland": "SL",
    "Sachsen": "SN",
    "Sachsen-Anhalt": "ST",
    "Schleswig-Holstein": "SH",
    "Thüringen": "TH",
}


def german_public_holidays(
    federal_state: str, years: set[int]
) -> dict[date, str]:
    subdivision = FEDERAL_STATE_CODES.get(federal_state)
    if subdivision is None:
        raise ValueError(f"Unsupported German federal state: {federal_state}")
    return dict(holidays.country_holidays("DE", subdiv=subdivision, years=years))
