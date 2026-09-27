from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, StringConstraints

# ISO 3166-1 alpha-2 officially assigned codes (249). Reserved/withdrawn codes (UK, EU, XK, ...)
# are rejected: the eligibility rules compare codes exactly, so aliases would silently mismatch.
ISO_COUNTRY_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS
    BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE
    EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM
    HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC
    LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA
    NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW
    SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO
    TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split()  # noqa: SIM905 -- a readable block beats 249 quoted strings
)


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


def _iso_country(value: str) -> str:
    if value not in ISO_COUNTRY_CODES:
        raise ValueError(f"{value} is not an ISO 3166-1 alpha-2 country code")
    return value


CountryCode = Annotated[
    str,
    BeforeValidator(_upper),
    StringConstraints(pattern=r"^[A-Z]{2}$"),
    AfterValidator(_iso_country),
]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


# For optional free text: surrounding whitespace is dropped and "" means "not provided". Put
# length limits on the inner `str` (a constraint on `str | None` would also apply to None):
#   Annotated[Annotated[str, Field(max_length=200)] | None, BlankToNone]
BlankToNone = BeforeValidator(_blank_to_none)


def _unique_countries(values: list[str] | None) -> list[str] | None:
    return None if values is None else list(dict.fromkeys(values))


CountryList = Annotated[list[CountryCode] | None, AfterValidator(_unique_countries)]
