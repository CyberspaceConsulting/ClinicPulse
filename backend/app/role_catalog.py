"""Roles offered per facility type; shipped locally, never fetched from a server."""

ACCESS_ROLE_LABELS = {
    "HOSPITAL_MANAGEMENT": "Krankenhausleitung",
    "PERSONNEL": "Personaler",
    "OBERARZT": "Oberarzt",
    "CHEFARZT": "Chefarzt",
    "KIOSK": "Kiosk",
    "EMPLOYEE": "Mitarbeiter",
}

_COMMON_ACCESS = ("HOSPITAL_MANAGEMENT", "PERSONNEL", "KIOSK", "EMPLOYEE")
_PHYSICIAN_ACCESS = ("HOSPITAL_MANAGEMENT", "PERSONNEL", "OBERARZT", "CHEFARZT", "KIOSK", "EMPLOYEE")

PROFILE_CATALOG: dict[str, dict[str, object]] = {
    "hospital": {
        "access_roles": _PHYSICIAN_ACCESS,
        "management_label": "Krankenhausleitung",
        "functions": (
            "Pflegefachkraft", "Arzt", "Assistenzarzt", "Oberarzt", "Pflegeassistenz", "Hebamme", "Medizinische Fachangestellte",
        ),
    },
    "rescue_service": {
        "access_roles": _COMMON_ACCESS,
        "management_label": "Wachleitung",
        "functions": (
            "Notfallsanitäter", "Rettungssanitäter", "Rettungsassistent", "Rettungshelfer", "Notarzt",
        ),
    },
    "ils": {
        "access_roles": _COMMON_ACCESS,
        "management_label": "Leitstellenleitung",
        "functions": ("Disponent", "Schichtführer", "Auszubildender"),
    },
    "care_facility": {
        "access_roles": _COMMON_ACCESS,
        "management_label": "Einrichtungsleitung",
        "functions": ("Pflegefachkraft", "Pflegeassistenz", "Pflegehelfer", "Betreuungskraft", "Hauswirtschaft"),
    },
    "other": {
        "access_roles": _COMMON_ACCESS,
        "management_label": "Leitung",
        "functions": ("Mitarbeiter", "Teamleitung"),
    },
}


def facility_structure(profile: str | None, configuration: object | None = None) -> dict[str, object]:
    """Effective organisational structure; only the facility type "other" is configurable."""
    if profile == "other":
        get = lambda name: getattr(configuration, name, None)  # noqa: E731
        return {
            "single_unit": bool(get("single_unit")),
            "uses_vehicles": bool(get("uses_vehicles")),
            "unit_label": get("unit_label"),
            "unit_label_plural": get("unit_label_plural"),
            "unit_gender": get("unit_gender"),
            "lead_label": get("lead_label"),
        }
    return {
        "single_unit": profile == "ils",
        "uses_vehicles": profile == "rescue_service",
        "unit_label": None,
        "unit_label_plural": None,
        "unit_gender": None,
        "lead_label": None,
    }


def catalog_for(profile: str | None, configuration: object | None = None) -> dict[str, object]:
    entry = PROFILE_CATALOG.get(profile or "", PROFILE_CATALOG["other"])
    structure = facility_structure(profile if profile in PROFILE_CATALOG else "other", configuration)
    labels = dict(ACCESS_ROLE_LABELS)
    labels["HOSPITAL_MANAGEMENT"] = str(structure["lead_label"] or entry["management_label"])
    return {
        "operational_profile": profile if profile in PROFILE_CATALOG else "other",
        "access_roles": [{"key": key, "label": labels[key]} for key in entry["access_roles"]],  # type: ignore[union-attr]
        "functions": list(entry["functions"]),  # type: ignore[call-overload]
        "structure": structure,
    }


def access_role_allowed(profile: str | None, role_key: str) -> bool:
    return role_key == "ADMIN" or any(role["key"] == role_key for role in catalog_for(profile)["access_roles"])  # type: ignore[union-attr]
