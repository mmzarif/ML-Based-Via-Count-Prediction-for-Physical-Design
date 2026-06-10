"""
generate_label.py
-----------------
Parse a post-routed DEF file (possibly gzip-compressed despite .def extension)
and emit per-net via counts to a CSV.

Strategy
--------
In a routed DEF the SPECIALNETS / NETS sections carry ROUTED wire geometry.
Vias appear as either:
  + ROUTED  metalX  0  ( x y ) viaName  ( x2 y2 ) ...
or as continuation lines:
  NEW metalX 0  ( x y ) viaName ...

We count every via token (a token that is NOT a metal layer name, NOT a
coordinate, NOT a keyword, NOT a number) per net.  The provided Aprisa
DEF uses standard DEF 5.8 routing syntax.

Output columns:
  netName, numVias

Usage:
  python3 generate_label.py \
      --def  path/to/aes_cipher_top_XX_YYYY_routed.def \
      --out  training.label.csv
"""

import argparse
import gzip
import re
import csv
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Keywords / tokens that are NOT via names inside a routing statement
_ROUTE_KEYWORDS = {
    "ROUTED", "FIXED", "COVER", "NOSHIELD",
    "NEW", "SHIELD", "TAPERRULE", "STYLE",
    "RECT", "VIRTUAL", "MASK",
}

# DEF layer names for TSMC 65 BEOL  (metal + via layers)
# Via names typically start with  M<n>_M<n+1>  or  via<n>  or  VIA<n>
# We detect them heuristically: a token that is non-numeric, not a keyword,
# not a coordinate group marker.
_COORD_RE  = re.compile(r"^\(|\)$|^-?\d+$")
_LAYER_RE  = re.compile(r"^[Mm][0-9]|^metal|^Metal|^METAL|^poly|^Poly|^li[0-9]")
_VIA_RE    = re.compile(
    r"^[Vv][Ii][Aa]|^M\d+_M\d+|^via\d|^VIA\d|^v\d",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def open_def(path):
    with open(path, "rb") as f:
        magic = f.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def is_via_token(tok):
    """Heuristic: is this DEF token a via reference?"""
    if not tok:
        return False
    if tok in _ROUTE_KEYWORDS:
        return False
    if _COORD_RE.match(tok):
        return False
    if _LAYER_RE.match(tok):
        return False
    # Must look like a via name
    return bool(_VIA_RE.match(tok))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_via_counts(path):
    """
    Return dict: net_name -> via_count
    Counts vias in both NETS and SPECIALNETS sections.
    """
    via_counts = {}
    in_nets    = False
    cur_net    = None
    in_routing = False   # True once we see a ROUTED/FIXED/NEW token in a net

    with open_def(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # Section boundaries
            if (line.startswith("NETS ") or line.startswith("SPECIALNETS ")) \
                    and not in_nets:
                in_nets = True
                continue

            if line in ("END NETS", "END SPECIALNETS"):
                in_nets    = False
                cur_net    = None
                in_routing = False
                continue

            if not in_nets:
                continue

            # New net definition
            if line.startswith("- "):
                parts    = line.split()
                cur_net  = parts[1]
                via_counts.setdefault(cur_net, 0)
                in_routing = False

            if cur_net is None:
                continue

            # Detect start of routing info
            if "ROUTED" in line or "FIXED" in line or "COVER" in line:
                in_routing = True

            if not in_routing:
                continue

            # Remove parentheses so coords are separate tokens
            cleaned = line.replace("(", " ").replace(")", " ")
            tokens  = cleaned.split()

            for tok in tokens:
                if is_via_token(tok):
                    via_counts[cur_net] += 1

    return via_counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Extract per-net via counts from post-routed DEF")
    ap.add_argument("--def", dest="def_file", required=True,
                    help="Path to post-routed DEF (plain or gzip-compressed)")
    ap.add_argument("--out", default="training.label.csv",
                    help="Output CSV path")
    args = ap.parse_args()

    print(f"[generate_label] Parsing DEF: {args.def_file}", flush=True)
    via_counts = parse_via_counts(args.def_file)

    # Filter to nets that actually have routing info (via_count >= 0 is fine;
    # 0-via nets are valid, they exist).
    total_vias = sum(via_counts.values())
    print(f"  nets with routing data: {len(via_counts)}, "
          f"total vias counted: {total_vias}", flush=True)

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["netName", "numVias"])
        writer.writeheader()
        for net, count in via_counts.items():
            writer.writerow({"netName": net, "numVias": count})

    print(f"[generate_label] Wrote {len(via_counts)} rows -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
