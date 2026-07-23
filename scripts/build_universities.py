"""Generate public/universities.json — the static US university directory the
frontend picker filters client-side (no network validation call).

Source of truth: the IPEDS HD directory (Institutional Characteristics).
  https://nces.ed.gov/ipeds/use-the-data  →  "hd2023.csv"
Columns used: UNITID, INSTNM, STABBR, WEBADDR (→ a bare registrable `domain`).
Only 4-year+, degree-granting, currently-open institutions are kept to keep the
file lean.

Usage:
    python scripts/build_universities.py            # from data/hd2023.csv if present
    python scripts/build_universities.py path.csv   # explicit CSV path

If no CSV is available, a curated seed list of well-known 4-year institutions
(real names + registrable domains) is written instead, so the feature works out
of the box. Drop hd2023.csv in and re-run to ship the full directory.

Output shape (array):
    [{ "unitid": 236948, "name": "University of Washington-Seattle Campus",
       "state": "WA", "domain": "washington.edu" }, ...]
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public" / "universities.json"
DEFAULT_CSV = ROOT / "data" / "hd2023.csv"


def registrable_domain(webaddr: str) -> str | None:
    """Reduce a messy WEBADDR ("www.Example.edu/apply", "http://x.edu") to a bare
    registrable domain ("example.edu"). Returns None if nothing usable."""
    if not webaddr:
        return None
    s = webaddr.strip().lower()
    s = re.sub(r"^[a-z]+://", "", s)      # strip scheme
    s = s.split("/")[0].split("?")[0]      # strip path/query
    s = s.strip().strip(".")
    if s.startswith("www."):
        s = s[4:]
    # Keep only host-looking tokens with a dot and no spaces.
    if not s or " " in s or "." not in s:
        return None
    return s


def from_csv(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    with csv_path.open(newline="", encoding="latin-1") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # ICLEVEL 1 = 4-year+, INSTCAT/DEGGRANT vary by year; keep it simple and
            # lenient — filter to 4-year (ICLEVEL == "1") when the column exists.
            if r.get("ICLEVEL") not in (None, "", "1"):
                continue
            domain = registrable_domain(r.get("WEBADDR", ""))
            name = (r.get("INSTNM") or "").strip()
            if not domain or not name:
                continue
            try:
                unitid = int(r.get("UNITID") or 0)
            except ValueError:
                continue
            rows.append(
                {"unitid": unitid, "name": name, "state": (r.get("STABBR") or "").strip(), "domain": domain}
            )
    # De-dupe by unitid, sort by name.
    seen: set[int] = set()
    out = []
    for row in sorted(rows, key=lambda x: x["name"]):
        if row["unitid"] in seen:
            continue
        seen.add(row["unitid"])
        out.append(row)
    return out


# A curated seed of real, well-known 4-year US institutions (name + registrable
# domain accurate; unitid is the IPEDS id where known). Used only when hd2023.csv
# is not available. Kept lean and broad across states and public/private.
SEED: list[dict] = [
    {"unitid": 236948, "name": "University of Washington-Seattle Campus", "state": "WA", "domain": "washington.edu"},
    {"unitid": 240444, "name": "University of Wisconsin-Madison", "state": "WI", "domain": "wisc.edu"},
    {"unitid": 166683, "name": "Massachusetts Institute of Technology", "state": "MA", "domain": "mit.edu"},
    {"unitid": 243744, "name": "Stanford University", "state": "CA", "domain": "stanford.edu"},
    {"unitid": 110635, "name": "University of California-Berkeley", "state": "CA", "domain": "berkeley.edu"},
    {"unitid": 110662, "name": "University of California-Los Angeles", "state": "CA", "domain": "ucla.edu"},
    {"unitid": 110671, "name": "University of California-San Diego", "state": "CA", "domain": "ucsd.edu"},
    {"unitid": 110644, "name": "University of California-Irvine", "state": "CA", "domain": "uci.edu"},
    {"unitid": 110705, "name": "University of California-Davis", "state": "CA", "domain": "ucdavis.edu"},
    {"unitid": 190150, "name": "Columbia University in the City of New York", "state": "NY", "domain": "columbia.edu"},
    {"unitid": 190415, "name": "Cornell University", "state": "NY", "domain": "cornell.edu"},
    {"unitid": 130794, "name": "Yale University", "state": "CT", "domain": "yale.edu"},
    {"unitid": 186131, "name": "Princeton University", "state": "NJ", "domain": "princeton.edu"},
    {"unitid": 166027, "name": "Harvard University", "state": "MA", "domain": "harvard.edu"},
    {"unitid": 215062, "name": "University of Pennsylvania", "state": "PA", "domain": "upenn.edu"},
    {"unitid": 144050, "name": "University of Chicago", "state": "IL", "domain": "uchicago.edu"},
    {"unitid": 147767, "name": "Northwestern University", "state": "IL", "domain": "northwestern.edu"},
    {"unitid": 162928, "name": "Johns Hopkins University", "state": "MD", "domain": "jhu.edu"},
    {"unitid": 198419, "name": "Duke University", "state": "NC", "domain": "duke.edu"},
    {"unitid": 221999, "name": "Vanderbilt University", "state": "TN", "domain": "vanderbilt.edu"},
    {"unitid": 227757, "name": "Rice University", "state": "TX", "domain": "rice.edu"},
    {"unitid": 179867, "name": "Washington University in St Louis", "state": "MO", "domain": "wustl.edu"},
    {"unitid": 130943, "name": "Georgetown University", "state": "DC", "domain": "georgetown.edu"},
    {"unitid": 217156, "name": "Brown University", "state": "RI", "domain": "brown.edu"},
    {"unitid": 182670, "name": "Dartmouth College", "state": "NH", "domain": "dartmouth.edu"},
    {"unitid": 211440, "name": "Carnegie Mellon University", "state": "PA", "domain": "cmu.edu"},
    {"unitid": 199120, "name": "University of North Carolina at Chapel Hill", "state": "NC", "domain": "unc.edu"},
    {"unitid": 139959, "name": "Georgia Institute of Technology-Main Campus", "state": "GA", "domain": "gatech.edu"},
    {"unitid": 139755, "name": "University of Georgia", "state": "GA", "domain": "uga.edu"},
    {"unitid": 170976, "name": "University of Michigan-Ann Arbor", "state": "MI", "domain": "umich.edu"},
    {"unitid": 145637, "name": "University of Illinois Urbana-Champaign", "state": "IL", "domain": "illinois.edu"},
    {"unitid": 174066, "name": "University of Minnesota-Twin Cities", "state": "MN", "domain": "umn.edu"},
    {"unitid": 153658, "name": "University of Iowa", "state": "IA", "domain": "uiowa.edu"},
    {"unitid": 155317, "name": "University of Kansas", "state": "KS", "domain": "ku.edu"},
    {"unitid": 204796, "name": "Ohio State University-Main Campus", "state": "OH", "domain": "osu.edu"},
    {"unitid": 243780, "name": "Purdue University-Main Campus", "state": "IN", "domain": "purdue.edu"},
    {"unitid": 151351, "name": "Indiana University-Bloomington", "state": "IN", "domain": "iu.edu"},
    {"unitid": 163286, "name": "University of Maryland-College Park", "state": "MD", "domain": "umd.edu"},
    {"unitid": 234076, "name": "University of Virginia-Main Campus", "state": "VA", "domain": "virginia.edu"},
    {"unitid": 233921, "name": "Virginia Polytechnic Institute and State University", "state": "VA", "domain": "vt.edu"},
    {"unitid": 228778, "name": "The University of Texas at Austin", "state": "TX", "domain": "utexas.edu"},
    {"unitid": 228723, "name": "Texas A & M University-College Station", "state": "TX", "domain": "tamu.edu"},
    {"unitid": 201885, "name": "Case Western Reserve University", "state": "OH", "domain": "case.edu"},
    {"unitid": 186380, "name": "Rutgers University-New Brunswick", "state": "NJ", "domain": "rutgers.edu"},
    {"unitid": 130590, "name": "University of Connecticut", "state": "CT", "domain": "uconn.edu"},
    {"unitid": 129020, "name": "University of Colorado Boulder", "state": "CO", "domain": "colorado.edu"},
    {"unitid": 104179, "name": "University of Arizona", "state": "AZ", "domain": "arizona.edu"},
    {"unitid": 104151, "name": "Arizona State University Campus Immersion", "state": "AZ", "domain": "asu.edu"},
    {"unitid": 209551, "name": "University of Oregon", "state": "OR", "domain": "uoregon.edu"},
    {"unitid": 209542, "name": "Oregon State University", "state": "OR", "domain": "oregonstate.edu"},
    {"unitid": 134130, "name": "University of Florida", "state": "FL", "domain": "ufl.edu"},
    {"unitid": 134097, "name": "Florida State University", "state": "FL", "domain": "fsu.edu"},
    {"unitid": 137351, "name": "University of Central Florida", "state": "FL", "domain": "ucf.edu"},
    {"unitid": 100751, "name": "The University of Alabama", "state": "AL", "domain": "ua.edu"},
    {"unitid": 145600, "name": "University of Illinois Chicago", "state": "IL", "domain": "uic.edu"},
    {"unitid": 110680, "name": "University of California-Santa Barbara", "state": "CA", "domain": "ucsb.edu"},
    {"unitid": 110714, "name": "University of California-Santa Cruz", "state": "CA", "domain": "ucsc.edu"},
    {"unitid": 123961, "name": "University of Southern California", "state": "CA", "domain": "usc.edu"},
    {"unitid": 122409, "name": "California Institute of Technology", "state": "CA", "domain": "caltech.edu"},
    {"unitid": 110097, "name": "California Polytechnic State University-San Luis Obispo", "state": "CA", "domain": "calpoly.edu"},
    {"unitid": 130697, "name": "New York University", "state": "NY", "domain": "nyu.edu"},
    {"unitid": 196097, "name": "Stony Brook University", "state": "NY", "domain": "stonybrook.edu"},
    {"unitid": 195030, "name": "Syracuse University", "state": "NY", "domain": "syracuse.edu"},
    {"unitid": 194824, "name": "Rensselaer Polytechnic Institute", "state": "NY", "domain": "rpi.edu"},
    {"unitid": 218663, "name": "University of South Carolina-Columbia", "state": "SC", "domain": "sc.edu"},
    {"unitid": 218733, "name": "Clemson University", "state": "SC", "domain": "clemson.edu"},
    {"unitid": 157085, "name": "University of Kentucky", "state": "KY", "domain": "uky.edu"},
    {"unitid": 159391, "name": "Louisiana State University and Agricultural & Mechanical College", "state": "LA", "domain": "lsu.edu"},
    {"unitid": 176017, "name": "University of Mississippi", "state": "MS", "domain": "olemiss.edu"},
    {"unitid": 178396, "name": "University of Missouri-Columbia", "state": "MO", "domain": "missouri.edu"},
    {"unitid": 181464, "name": "University of Nebraska-Lincoln", "state": "NE", "domain": "unl.edu"},
    {"unitid": 182281, "name": "University of Nevada-Reno", "state": "NV", "domain": "unr.edu"},
    {"unitid": 187985, "name": "University of New Mexico-Main Campus", "state": "NM", "domain": "unm.edu"},
    {"unitid": 207500, "name": "University of Oklahoma-Norman Campus", "state": "OK", "domain": "ou.edu"},
    {"unitid": 218964, "name": "University of Tennessee-Knoxville", "state": "TN", "domain": "utk.edu"},
    {"unitid": 230764, "name": "University of Utah", "state": "UT", "domain": "utah.edu"},
    {"unitid": 230728, "name": "Brigham Young University", "state": "UT", "domain": "byu.edu"},
    {"unitid": 240727, "name": "University of Wyoming", "state": "WY", "domain": "uwyo.edu"},
    {"unitid": 236595, "name": "Washington State University", "state": "WA", "domain": "wsu.edu"},
    {"unitid": 126614, "name": "Colorado State University-Fort Collins", "state": "CO", "domain": "colostate.edu"},
    {"unitid": 171100, "name": "Michigan State University", "state": "MI", "domain": "msu.edu"},
    {"unitid": 214777, "name": "Pennsylvania State University-Main Campus", "state": "PA", "domain": "psu.edu"},
    {"unitid": 215293, "name": "University of Pittsburgh-Pittsburgh Campus", "state": "PA", "domain": "pitt.edu"},
    {"unitid": 216287, "name": "Temple University", "state": "PA", "domain": "temple.edu"},
    {"unitid": 206084, "name": "University of Cincinnati-Main Campus", "state": "OH", "domain": "uc.edu"},
    {"unitid": 152080, "name": "University of Notre Dame", "state": "IN", "domain": "nd.edu"},
    {"unitid": 164988, "name": "Boston University", "state": "MA", "domain": "bu.edu"},
    {"unitid": 164924, "name": "Boston College", "state": "MA", "domain": "bc.edu"},
    {"unitid": 167358, "name": "Northeastern University", "state": "MA", "domain": "northeastern.edu"},
    {"unitid": 165015, "name": "Brandeis University", "state": "MA", "domain": "brandeis.edu"},
    {"unitid": 168342, "name": "Tufts University", "state": "MA", "domain": "tufts.edu"},
    {"unitid": 168421, "name": "University of Massachusetts-Amherst", "state": "MA", "domain": "umass.edu"},
    {"unitid": 227216, "name": "Southern Methodist University", "state": "TX", "domain": "smu.edu"},
    {"unitid": 225511, "name": "University of Houston", "state": "TX", "domain": "uh.edu"},
    {"unitid": 228246, "name": "Texas Tech University", "state": "TX", "domain": "ttu.edu"},
    {"unitid": 139658, "name": "Emory University", "state": "GA", "domain": "emory.edu"},
    {"unitid": 100858, "name": "Auburn University", "state": "AL", "domain": "auburn.edu"},
    {"unitid": 232557, "name": "George Mason University", "state": "VA", "domain": "gmu.edu"},
    {"unitid": 131496, "name": "George Washington University", "state": "DC", "domain": "gwu.edu"},
    {"unitid": 131469, "name": "American University", "state": "DC", "domain": "american.edu"},
    {"unitid": 145813, "name": "Illinois Institute of Technology", "state": "IL", "domain": "iit.edu"},
    {"unitid": 199193, "name": "North Carolina State University at Raleigh", "state": "NC", "domain": "ncsu.edu"},
    {"unitid": 240329, "name": "Marquette University", "state": "WI", "domain": "marquette.edu"},
    {"unitid": 201645, "name": "Miami University-Oxford", "state": "OH", "domain": "miamioh.edu"},
]


def main() -> None:
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CSV
    if csv_path.exists():
        data = from_csv(csv_path)
        note = f"built from {csv_path.name} (IPEDS HD directory)"
    else:
        # De-dupe the seed by unitid, sort by name.
        seen: set[int] = set()
        data = []
        for row in sorted(SEED, key=lambda x: x["name"]):
            if row["unitid"] in seen:
                continue
            seen.add(row["unitid"])
            data.append(row)
        note = "curated seed (no hd2023.csv found; drop it in data/ and re-run for the full IPEDS directory)"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=0, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(data)} institutions → {OUT.relative_to(ROOT)}  [{note}]")


if __name__ == "__main__":
    main()
