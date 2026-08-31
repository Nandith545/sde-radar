"""Country -> state/province -> city lists for the region pickers.

Bundled rather than derived from the job pool, because a preference has to be
settable *before* a job from that place has ever been ingested -- a picker
that only offered cities we already had postings for could never be used to
go looking somewhere new. The live counts that annotate these options come
from the pool at request time; the vocabulary itself lives here.

Scope is the eight countries the connectors actually serve, which is the same
list `job_facets._COUNTRY_ALIASES` recognises. This is deliberately not a
geocoder and is not going to become one: the city lists are the places that
plausibly carry software jobs, not every settlement, and a location this
module cannot place comes back empty rather than guessed at.

The country slugs match `job_facets.infer_country`'s vocabulary exactly, so a
preference set here can be compared against a posting resolved from its
freeform location string without a translation layer in between.
"""

import unicodedata
from dataclasses import dataclass

# Cities are pipe-separated rather than list literals: 51 rows of
# `("Alabama", ["Birmingham", "Huntsville", ...])` is far harder to scan and
# to edit than one row per subdivision, and ruff's SIM905 pushes the literal
# form around anyway. Split once at import.
#
# Order within a row matters in one place: where two subdivisions of the same
# country share a city name, the first one listed wins the reverse lookup.

_US = """
AL|Alabama|Birmingham|Huntsville|Montgomery|Mobile
AK|Alaska|Anchorage|Fairbanks|Juneau
AZ|Arizona|Phoenix|Tucson|Scottsdale|Tempe|Chandler|Mesa|Gilbert
AR|Arkansas|Little Rock|Fayetteville|Bentonville|Rogers
CA|California|San Francisco|San Jose|Los Angeles|San Diego|Oakland|Sacramento|Palo Alto|Mountain View|Sunnyvale|Santa Clara|Irvine|Pasadena|Santa Monica|Berkeley|Cupertino|Menlo Park|Redwood City|San Mateo|Fremont|Long Beach|Culver City|El Segundo
CO|Colorado|Denver|Boulder|Colorado Springs|Fort Collins|Aurora|Broomfield
CT|Connecticut|Stamford|Hartford|New Haven|Norwalk|Greenwich
DE|Delaware|Wilmington|Dover|Newark
DC|District of Columbia|Washington
FL|Florida|Miami|Orlando|Tampa|Jacksonville|Fort Lauderdale|St. Petersburg|Boca Raton|Gainesville
GA|Georgia|Atlanta|Alpharetta|Savannah|Augusta|Athens|Sandy Springs
HI|Hawaii|Honolulu
ID|Idaho|Boise|Meridian|Idaho Falls
IL|Illinois|Chicago|Naperville|Schaumburg|Evanston|Champaign|Springfield
IN|Indiana|Indianapolis|Bloomington|Fort Wayne|Carmel|West Lafayette
IA|Iowa|Des Moines|Cedar Rapids|Iowa City|Ames
KS|Kansas|Overland Park|Wichita|Lawrence|Topeka|Olathe
KY|Kentucky|Louisville|Lexington|Covington
LA|Louisiana|New Orleans|Baton Rouge|Shreveport|Lafayette
ME|Maine|Portland|Bangor|Augusta
MD|Maryland|Baltimore|Bethesda|Columbia|Rockville|Annapolis|Silver Spring|Gaithersburg
MA|Massachusetts|Boston|Cambridge|Somerville|Waltham|Burlington|Worcester|Lowell|Quincy|Needham
MI|Michigan|Detroit|Ann Arbor|Grand Rapids|Lansing|Troy|Dearborn
MN|Minnesota|Minneapolis|St. Paul|Rochester|Bloomington|Eden Prairie
MS|Mississippi|Jackson|Gulfport|Hattiesburg
MO|Missouri|St. Louis|Kansas City|Columbia|Springfield
MT|Montana|Bozeman|Missoula|Billings
NE|Nebraska|Omaha|Lincoln
NV|Nevada|Las Vegas|Reno|Henderson
NH|New Hampshire|Manchester|Nashua|Portsmouth
NJ|New Jersey|Newark|Jersey City|Princeton|Hoboken|Trenton|Edison|Basking Ridge
NM|New Mexico|Albuquerque|Santa Fe|Las Cruces
NY|New York|New York|Brooklyn|Buffalo|Rochester|Albany|Syracuse|White Plains|Queens|Long Island City
NC|North Carolina|Raleigh|Charlotte|Durham|Chapel Hill|Cary|Greensboro|Winston-Salem
ND|North Dakota|Fargo|Bismarck|Grand Forks
OH|Ohio|Columbus|Cleveland|Cincinnati|Dublin|Dayton|Akron
OK|Oklahoma|Oklahoma City|Tulsa|Norman
OR|Oregon|Portland|Beaverton|Hillsboro|Eugene|Bend|Salem
PA|Pennsylvania|Philadelphia|Pittsburgh|Harrisburg|Allentown|King of Prussia|Malvern
RI|Rhode Island|Providence|Warwick
SC|South Carolina|Charleston|Columbia|Greenville|Mount Pleasant
SD|South Dakota|Sioux Falls|Rapid City
TN|Tennessee|Nashville|Memphis|Knoxville|Chattanooga|Franklin
TX|Texas|Austin|Dallas|Houston|San Antonio|Plano|Irving|Fort Worth|Richardson|Round Rock|El Paso|Frisco|Addison
UT|Utah|Salt Lake City|Lehi|Provo|Draper|Sandy|Ogden
VT|Vermont|Burlington|Montpelier
VA|Virginia|Arlington|Richmond|Reston|McLean|Alexandria|Herndon|Virginia Beach|Charlottesville|Norfolk
WA|Washington|Seattle|Bellevue|Redmond|Kirkland|Tacoma|Spokane|Renton|Bothell|Everett|Olympia|Bremerton|Sammamish
WV|West Virginia|Charleston|Morgantown|Huntington
WI|Wisconsin|Milwaukee|Madison|Green Bay|Middleton
WY|Wyoming|Cheyenne|Casper
"""

_CANADA = """
ON|Ontario|Toronto|Ottawa|Mississauga|Waterloo|Kitchener|Hamilton|London|Markham|Brampton|Oakville
BC|British Columbia|Vancouver|Victoria|Burnaby|Richmond|Surrey|Kelowna
QC|Quebec|Montreal|Quebec City|Laval|Gatineau|Sherbrooke
AB|Alberta|Calgary|Edmonton|Red Deer
MB|Manitoba|Winnipeg
SK|Saskatchewan|Saskatoon|Regina
NS|Nova Scotia|Halifax|Dartmouth
NB|New Brunswick|Moncton|Fredericton|Saint John
NL|Newfoundland and Labrador|St. John's
PE|Prince Edward Island|Charlottetown
NT|Northwest Territories|Yellowknife
NU|Nunavut|Iqaluit
YT|Yukon|Whitehorse
"""

_UK = """
ENG|England|London|Manchester|Birmingham|Bristol|Leeds|Cambridge|Oxford|Reading|Newcastle|Sheffield|Liverpool|Nottingham|Brighton|Milton Keynes
SCT|Scotland|Edinburgh|Glasgow|Aberdeen|Dundee
WLS|Wales|Cardiff|Swansea|Newport
NIR|Northern Ireland|Belfast|Derry=Londonderry
"""

_GERMANY = """
BE|Berlin|Berlin
BY|Bavaria|Munich=München|Nuremberg=Nürnberg|Augsburg|Regensburg|Erlangen|Ingolstadt
NW|North Rhine-Westphalia|Cologne=Köln|Düsseldorf|Dortmund|Essen|Bonn|Münster|Bochum|Aachen
BW|Baden-Württemberg|Stuttgart|Karlsruhe|Mannheim|Freiburg|Heidelberg
HE|Hesse|Frankfurt|Wiesbaden|Darmstadt|Kassel|Offenbach
HH|Hamburg|Hamburg
NI|Lower Saxony|Hanover=Hannover|Braunschweig|Osnabrück|Oldenburg|Göttingen
SN|Saxony|Dresden|Leipzig|Chemnitz
RP|Rhineland-Palatinate|Mainz|Ludwigshafen|Koblenz|Trier
BB|Brandenburg|Potsdam|Cottbus
SH|Schleswig-Holstein|Kiel|Lübeck
HB|Bremen|Bremen
ST|Saxony-Anhalt|Magdeburg|Halle
TH|Thuringia|Erfurt|Jena|Weimar
MV|Mecklenburg-Vorpommern|Rostock|Schwerin
SL|Saarland|Saarbrücken
"""

_INDIA = """
KA|Karnataka|Bengaluru=Bangalore|Mysuru=Mysore|Mangaluru=Mangalore
MH|Maharashtra|Mumbai=Bombay|Pune|Nagpur|Nashik
TS|Telangana|Hyderabad|Warangal
TN|Tamil Nadu|Chennai=Madras|Coimbatore|Madurai
DL|Delhi|New Delhi|Delhi
HR|Haryana|Gurugram=Gurgaon|Faridabad|Panipat
UP|Uttar Pradesh|Noida|Ghaziabad|Lucknow|Kanpur|Varanasi
WB|West Bengal|Kolkata=Calcutta|Siliguri|Durgapur
GJ|Gujarat|Ahmedabad|Surat|Vadodara=Baroda|Gandhinagar
KL|Kerala|Kochi=Cochin|Thiruvananthapuram=Trivandrum|Kozhikode
AP|Andhra Pradesh|Visakhapatnam|Vijayawada|Tirupati
RJ|Rajasthan|Jaipur|Jodhpur|Udaipur
MP|Madhya Pradesh|Indore|Bhopal|Jabalpur
PB|Punjab|Ludhiana|Mohali|Amritsar|Jalandhar
CH|Chandigarh|Chandigarh
OD|Odisha|Bhubaneswar|Cuttack
BR|Bihar|Patna
JH|Jharkhand|Ranchi|Jamshedpur
AS|Assam|Guwahati
CG|Chhattisgarh|Raipur
UA|Uttarakhand|Dehradun|Haridwar
GA|Goa|Panaji|Vasco da Gama
HP|Himachal Pradesh|Shimla
"""

_NETHERLANDS = """
NH|North Holland|Amsterdam|Haarlem|Hilversum|Alkmaar|Amstelveen
ZH|South Holland|Rotterdam|The Hague=Den Haag|Leiden|Delft|Dordrecht
NB|North Brabant|Eindhoven|Tilburg|Breda|'s-Hertogenbosch
UT|Utrecht|Utrecht|Amersfoort
GE|Gelderland|Arnhem|Nijmegen|Apeldoorn|Ede
OV|Overijssel|Enschede|Zwolle|Deventer
LI|Limburg|Maastricht|Venlo|Heerlen
GR|Groningen|Groningen
FR|Friesland|Leeuwarden
FL|Flevoland|Almere|Lelystad
DR|Drenthe|Assen|Emmen
ZE|Zeeland|Middelburg|Vlissingen
"""

_AUSTRALIA = """
NSW|New South Wales|Sydney|Newcastle|Wollongong
VIC|Victoria|Melbourne|Geelong|Ballarat
QLD|Queensland|Brisbane|Gold Coast|Cairns|Townsville
WA|Western Australia|Perth|Fremantle
SA|South Australia|Adelaide
ACT|Australian Capital Territory|Canberra
TAS|Tasmania|Hobart|Launceston
NT|Northern Territory|Darwin
"""

_IRELAND = """
D|Dublin|Dublin
CK|Cork|Cork
GY|Galway|Galway
LK|Limerick|Limerick
WD|Waterford|Waterford
KE|Kildare|Naas|Maynooth
MH|Meath|Navan
"""


@dataclass(frozen=True)
class Subdivision:
    code: str
    label: str
    cities: tuple[str, ...]
    """Display names, in the order the picker shows them."""
    aliases: tuple[tuple[str, ...], ...]
    """Per city, every name it answers to -- the display name first, then any
    others written as `Display=Other` in the table above. Boards disagree
    about which to use (Arbeitnow says München, Adzuna says Munich; Indian
    postings still say Bangalore as often as Bengaluru), and a posting has to
    resolve to the same place whichever it picked."""


@dataclass(frozen=True)
class Country:
    slug: str
    label: str
    subdivision_label: str
    """What this country calls the tier: "State", "Province", "Land"... Shown
    as the picker's own label, because "State" over a list of German Länder
    or Canadian provinces reads as a bug to anyone who lives there."""
    subdivisions: tuple[Subdivision, ...]
    has_coded_addresses: bool
    """Whether addresses in this country routinely spell the subdivision as a
    short code ("Seattle, WA"). Only then is it safe to read a bare two-letter
    token in a location string as a subdivision -- doing it for Germany would
    turn the "BE" in any string into Berlin."""


def _parse(block: str) -> tuple[Subdivision, ...]:
    rows = []
    for line in block.strip().splitlines():
        code, label, *entries = line.split("|")
        rows.append(
            Subdivision(
                code=code,
                label=label,
                cities=tuple(e.split("=")[0] for e in entries),
                aliases=tuple(tuple(e.split("=")) for e in entries),
            )
        )
    return tuple(rows)


COUNTRIES: dict[str, Country] = {
    c.slug: c
    for c in (
        Country("united states", "United States", "State", _parse(_US), True),
        Country("canada", "Canada", "Province", _parse(_CANADA), True),
        Country("united kingdom", "United Kingdom", "Nation", _parse(_UK), False),
        Country("germany", "Germany", "State", _parse(_GERMANY), False),
        Country("india", "India", "State", _parse(_INDIA), False),
        Country("netherlands", "Netherlands", "Province", _parse(_NETHERLANDS), False),
        Country("australia", "Australia", "State", _parse(_AUSTRALIA), True),
        Country("ireland", "Ireland", "County", _parse(_IRELAND), False),
    )
}


def normalize(text: str) -> str:
    """Casefold and strip accents, so "Münster" and "Munster" are one key.

    Arbeitnow returns German city names with their umlauts and Adzuna does
    not, and a picker that treated those as two different places would show
    the user two rows for one city.
    """
    stripped = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return " ".join(stripped.lower().replace(".", "").split())


def _build_city_index() -> dict[str, dict[str, str]]:
    """city (and alias) -> subdivision code, per country.

    A name that occurs in more than one subdivision of the same country is
    left out entirely rather than resolved to a favourite. "Portland" is in
    both Oregon and Maine, "Springfield" in Illinois and Missouri, "Newark"
    in New Jersey and Delaware; picking one would silently file half of those
    postings under a state they are not in.

    Dropping them costs very little, because the ambiguity only bites when a
    posting names a bare city with no code -- and a US posting that says
    "Portland, OR" is read from the code long before this index is consulted.
    Reporting "don't know" is the same choice `job_facets` makes everywhere
    else it cannot read a location.
    """
    index: dict[str, dict[str, str]] = {}
    for slug, country in COUNTRIES.items():
        seen: dict[str, set[str]] = {}
        for sub in country.subdivisions:
            for entry in sub.aliases:
                for name in entry:
                    seen.setdefault(normalize(name), set()).add(sub.code)
        index[slug] = {name: next(iter(codes)) for name, codes in seen.items() if len(codes) == 1}
    return index


_CITY_INDEX = _build_city_index()

# Longest-first search order, computed once rather than sorted per lookup --
# `locate` runs against every posting in the pool when the picker asks for
# counts, and re-sorting a few hundred names each time showed up immediately.
_CITY_SEARCH_ORDER: dict[str, list[str]] = {
    slug: sorted(names, key=len, reverse=True) for slug, names in _CITY_INDEX.items()
}


def _build_city_display() -> dict[str, dict[str, str]]:
    """normalized name (including aliases) -> the display name to show.

    So a posting that says "Bangalore" counts towards the "Bengaluru" option
    the picker actually offers, rather than towards a second row for a city
    that is already in the list under its other name.
    """
    display: dict[str, dict[str, str]] = {}
    for slug, country in COUNTRIES.items():
        names: dict[str, str] = {}
        for sub in country.subdivisions:
            for entry in sub.aliases:
                for name in entry:
                    names.setdefault(normalize(name), entry[0])
        display[slug] = names
    return display


_CITY_DISPLAY = _build_city_display()

AMBIGUOUS_CITIES: dict[str, frozenset[str]] = {}
"""Per country, the city names that appear in more than one subdivision.

Exposed so the API can tell the picker which of its own options are unusable
for inference, rather than leaving that knowledge only inside this module.
"""
for _slug, _country in COUNTRIES.items():
    _seen: dict[str, int] = {}
    for _sub in _country.subdivisions:
        for _entry in _sub.aliases:
            for _name in _entry:
                _seen[normalize(_name)] = _seen.get(normalize(_name), 0) + 1
    AMBIGUOUS_CITIES[_slug] = frozenset(n for n, count in _seen.items() if count > 1)

_CODES: dict[str, set[str]] = {slug: {s.code for s in c.subdivisions} for slug, c in COUNTRIES.items()}


def subdivisions(country_slug: str) -> tuple[Subdivision, ...]:
    country = COUNTRIES.get(country_slug)
    return country.subdivisions if country else ()


def cities(country_slug: str, codes: list[str] | None = None) -> list[str]:
    """Every city in the named subdivisions, or in the whole country when
    `codes` is empty -- which is what "All states" selects."""
    wanted = set(codes or [])
    out: list[str] = []
    for sub in subdivisions(country_slug):
        if wanted and sub.code not in wanted:
            continue
        out.extend(sub.cities)
    return out


def locate(location: str, country_slug: str) -> tuple[str, str]:
    """Resolve a freeform location to (subdivision code, city display name).

    Either half can be empty, and empty always means "could not tell" rather
    than "none". A posting can resolve to a state without a city ("Austin, TX"
    when Austin were missing from the table) or to neither ("Remote (USA)",
    "Unspecified"); callers must skip the preference in those cases rather
    than treat an unreadable location as failing it. That is the same
    asymmetry `job_facets` applies to work mode and country, for the same
    reason: penalising a job for a string we could not parse hides a real
    match behind a reason the user can never see.
    """
    if not location or country_slug not in COUNTRIES:
        return "", ""
    country = COUNTRIES[country_slug]

    code = ""
    if country.has_coded_addresses:
        for token in location.replace(",", " ").split():
            bare = token.strip("()").upper()
            if bare in _CODES[country_slug]:
                code = bare
                break

    text = normalize(location)
    # Longest name first, so "New York" is not shadowed by a shorter entry and
    # multi-word names win over the single words inside them.
    for name in _CITY_SEARCH_ORDER[country_slug]:
        if name in text:
            return code or _CITY_INDEX[country_slug][name], _CITY_DISPLAY[country_slug][name]
    return code, ""


def infer_subdivision(location: str, country_slug: str) -> str:
    """Best-effort subdivision code for a posting's location, or ""."""
    return locate(location, country_slug)[0]


# --- Postal codes --------------------------------------------------------
#
# These resolve a postal code to a subdivision *for the profile address*.
# They are never used to filter jobs: no connector returns a postal code and
# `JobListing` has no column for one, so a postal-code job filter could only
# ever match nothing.
#
# Only the three countries whose codes map to subdivisions cleanly and
# publicly are covered. UK outward codes, German Postleitzahlen, Indian PINs
# and Dutch four-digit ranges all cross subdivision boundaries often enough
# that a table here would be quietly wrong for real addresses, and being
# wrong about someone's own address is worse than asking them to pick.
_US_ZIP_RANGES = """
AL|35000|36999
AK|99500|99999
AZ|85000|86999
AR|71600|72999
CA|90000|96199
CO|80000|81999
CT|06000|06999
DE|19700|19999
DC|20000|20099
DC|20200|20599
FL|32000|34999
GA|30000|31999
GA|39800|39999
HI|96700|96899
ID|83200|83899
IL|60000|62999
IN|46000|47999
IA|50000|52999
KS|66000|67999
KY|40000|42799
LA|70000|71499
ME|03900|04999
MD|20600|21999
MA|01000|02799
MI|48000|49999
MN|55000|56799
MS|38600|39799
MO|63000|65899
MT|59000|59999
NE|68000|69399
NV|88900|89899
NH|03000|03899
NJ|07000|08999
NM|87000|88499
NY|00500|00599
NY|10000|14999
NC|27000|28999
ND|58000|58899
OH|43000|45999
OK|73000|74999
OR|97000|97999
PA|15000|19699
RI|02800|02999
SC|29000|29999
SD|57000|57799
TN|37000|38599
TX|75000|79999
TX|88500|88599
UT|84000|84799
VT|05000|05999
VA|20100|20199
VA|22000|24699
WA|98000|99499
WV|24700|26899
WI|53000|54999
WY|82000|83199
"""

# Australia Post's ranges. Two states share a first digit with a territory,
# which is why these are ranges rather than a digit lookup.
_AU_POSTCODE_RANGES = """
NT|0800|0999
NSW|1000|2599
ACT|2600|2618
NSW|2619|2899
ACT|2900|2920
NSW|2921|2999
VIC|3000|3999
QLD|4000|4999
SA|5000|5999
WA|6000|6999
TAS|7000|7999
VIC|8000|8999
QLD|9000|9999
"""

# Canadian forward sortation areas are keyed by their first letter, which is
# the one national scheme where a single character is authoritative.
_CA_POSTAL_LETTERS = {
    "A": "NL",
    "B": "NS",
    "C": "PE",
    "E": "NB",
    "G": "QC",
    "H": "QC",
    "J": "QC",
    "K": "ON",
    "L": "ON",
    "M": "ON",
    "N": "ON",
    "P": "ON",
    "R": "MB",
    "S": "SK",
    "T": "AB",
    "V": "BC",
    "Y": "YT",
    # X covers both Northwest Territories and Nunavut, so it resolves to
    # neither -- the same rule the ambiguous city names follow.
}


def _parse_ranges(block: str) -> tuple[tuple[str, int, int], ...]:
    rows = []
    for line in block.strip().splitlines():
        code, low, high = line.split("|")
        rows.append((code, int(low), int(high)))
    return tuple(rows)


_NUMERIC_RANGES: dict[str, tuple[tuple[str, int, int], ...]] = {
    "united states": _parse_ranges(_US_ZIP_RANGES),
    "australia": _parse_ranges(_AU_POSTCODE_RANGES),
}

POSTAL_COUNTRIES = frozenset({"united states", "canada", "australia"})
"""Countries where entering a postal code can fill in the subdivision."""


def subdivision_from_postal(country_slug: str, postal_code: str) -> str:
    """Subdivision code for a postal code, or "" when it can't be resolved.

    Empty covers all of: an unsupported country, a malformed code, and a code
    that falls in a genuinely shared range. The caller shows the picker
    untouched in every one of those cases, so a bad guess is never written
    into someone's address.
    """
    code = (postal_code or "").strip().upper()
    if not code or country_slug not in POSTAL_COUNTRIES:
        return ""

    if country_slug == "canada":
        return _CA_POSTAL_LETTERS.get(code[0], "")

    digits = "".join(ch for ch in code if ch.isdigit())
    if not digits:
        return ""
    # Australia's are four digits, the US's five. Taking a prefix rather than
    # rejecting a longer string means a ZIP+4 ("98052-8300") still resolves.
    width = 4 if country_slug == "australia" else 5
    if len(digits) < width:
        return ""
    value = int(digits[:width])
    for sub_code, low, high in _NUMERIC_RANGES[country_slug]:
        if low <= value <= high:
            return sub_code
    return ""


def state_label(country_slug: str, code: str) -> str:
    """Human name for a subdivision code, or the code itself if unrecognised.

    Falling back to the code keeps user-facing text readable rather than
    blank when a stored preference outlives a table edit.
    """
    for sub in subdivisions(country_slug):
        if sub.code == code:
            return sub.label
    return code
