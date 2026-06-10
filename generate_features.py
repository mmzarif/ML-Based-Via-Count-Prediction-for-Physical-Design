"""
generate_features.py
--------------------
Parse a post-CTS DEF file (possibly gzip-compressed despite .def extension)
and emit per-net features to a CSV.

Output columns:
  netName, util, cp, bboxArea, bboxAr, numPins

Usage:
  python3 generate_features.py \
      --def  path/to/aes_cipher_top_XX_YYYY_cts.def \
      --util 0.60 \
      --cp   1.600 \
      --out  training.features.csv
"""

import argparse
import gzip
import math
import os
import re
import sys
import csv

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def open_def(path):
    """Return a text-mode file handle; transparently handles gzip."""
    # Try reading first two bytes to detect gzip magic
    with open(path, "rb") as f:
        magic = f.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    else:
        return open(path, "r", encoding="utf-8", errors="replace")


def parse_def(path):
    """
    Parse a DEF file and return:
      - components: dict  cell_instance_name -> cell_type
      - nets:       dict  net_name -> list of (inst_name, pin_name) connections
      - pin_coords: dict  inst_name -> (x, y)  [in DEF database units]
      - dbu:        int   database units per micron (from UNITS line)

    Coordinate extraction strategy
    --------------------------------
    For COMPONENTS we record placed coordinates (PLACED / FIXED).
    For PINS (top-level IO pads) we also record coordinates.
    For net bounding boxes we use the pin coordinates of every connected
    instance/port.
    """
    components = {}   # inst -> cell_type
    inst_xy    = {}   # inst -> (x, y)
    nets       = {}   # net  -> [(inst, pin), ...]
    dbu        = 1000 # default

    in_components = False
    in_nets       = False
    in_pins       = False
    cur_net       = None
    cur_pin_name  = None
    cur_pin_x     = None
    cur_pin_y     = None

    with open_def(path) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            # ---- UNITS ----
            if line.startswith("UNITS DISTANCE MICRONS"):
                parts = line.split()
                dbu = int(parts[3])
                continue

            # ---- COMPONENTS ----
            if line.startswith("COMPONENTS ") and not in_components:
                in_components = True
                continue
            if line == "END COMPONENTS":
                in_components = False
                continue
            if in_components and line.startswith("- "):
                # Format: - instName cellType + PLACED ( x y ) orient ;
                parts = line.split()
                inst      = parts[1]
                cell_type = parts[2]
                components[inst] = cell_type
                # Grab placement coords if present
                if "PLACED" in parts or "FIXED" in parts:
                    try:
                        idx = parts.index("(")
                        x = int(parts[idx + 1])
                        y = int(parts[idx + 2])
                        inst_xy[inst] = (x, y)
                    except (ValueError, IndexError):
                        pass
                continue

            # ---- TOP-LEVEL PINS ----
            if line.startswith("PINS ") and not in_pins:
                in_pins = True
                continue
            if line == "END PINS":
                in_pins = False
                cur_pin_name = None
                continue
            if in_pins:
                if line.startswith("- "):
                    cur_pin_name = line.split()[1]
                    cur_pin_x = None
                    cur_pin_y = None
                if cur_pin_name and "PLACED" in line or (cur_pin_name and "FIXED" in line):
                    m = re.search(r"\(\s*(-?\d+)\s+(-?\d+)\s*\)", line)
                    if m:
                        cur_pin_x = int(m.group(1))
                        cur_pin_y = int(m.group(2))
                        # Use a special key "__PIN__<name>" for top-level pins
                        inst_xy[f"__PIN__{cur_pin_name}"] = (cur_pin_x, cur_pin_y)
                continue

            # ---- NETS ----
            if line.startswith("NETS ") and not in_nets:
                in_nets = True
                continue
            if line == "END NETS":
                in_nets = False
                cur_net = None
                continue
            if in_nets:
                if line.startswith("- "):
                    # New net definition
                    cur_net = line.split()[1]
                    nets[cur_net] = []
                    # Connections may be on same line: - netName ( inst pin ) ( inst pin ) ...
                    _parse_net_connections(line, cur_net, nets)
                elif cur_net is not None and line.startswith("("):
                    # Continuation line with connections
                    _parse_net_connections(line, cur_net, nets)
                elif cur_net is not None and "(" in line and not line.startswith("+"):
                    _parse_net_connections(line, cur_net, nets)
                continue

    return components, inst_xy, nets, dbu


def _parse_net_connections(line, net_name, nets):
    """Extract ( inst pin ) pairs from a net definition line."""
    for m in re.finditer(r"\(\s*(\S+)\s+(\S+)\s*\)", line):
        inst = m.group(1)
        pin  = m.group(2)
        nets[net_name].append((inst, pin))


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_net_features(nets, inst_xy, dbu, util, cp):
    """
    For each net compute:
      bboxArea  - bounding box area in µm²
      bboxAr    - bounding box aspect ratio (long / short side), >= 1.0
      numPins   - number of (inst, pin) connections (= degree of net)

    Returns list of dicts.
    """
    rows = []
    scale = dbu  # DEF coords are in database units; divide by dbu to get µm

    for net_name, conns in nets.items():
        np_ = len(conns)
        if np_ < 2 or np_ > 50:
            continue  # spec: only nets of size 2-50

        # Collect coordinates for connected instances
        xs, ys = [], []
        for inst, pin in conns:
            key = inst if inst != "PIN" else f"__PIN__{pin}"
            if key in inst_xy:
                xs.append(inst_xy[key][0])
                ys.append(inst_xy[key][1])

        if len(xs) < 2:
            # Fall back: use numPins only, leave geometry as 0
            bbox_area = 0.0
            bbox_ar   = 1.0
        else:
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            dx = (x_max - x_min) / scale   # µm
            dy = (y_max - y_min) / scale   # µm
            bbox_area = dx * dy
            long_  = max(dx, dy)
            short_ = min(dx, dy)
            bbox_ar = long_ / short_ if short_ > 0 else long_ if long_ > 0 else 1.0

        rows.append({
            "netName":  net_name,
            "util":     util,
            "cp":       cp,
            "bboxArea": round(bbox_area, 6),
            "bboxAr":   round(bbox_ar,   6),
            "numPins":  np_,
        })

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Extract per-net features from post-CTS DEF")
    ap.add_argument("--def",  dest="def_file", required=True,
                    help="Path to post-CTS DEF (plain or gzip-compressed)")
    ap.add_argument("--util", type=float, required=True,
                    help="Initial utilization fraction (e.g. 0.60 for 60%%)")
    ap.add_argument("--cp",   type=float, required=True,
                    help="Target clock period in ns (e.g. 1.600)")
    ap.add_argument("--out",  default="training.features.csv",
                    help="Output CSV path")
    args = ap.parse_args()

    print(f"[generate_features] Parsing DEF: {args.def_file}", flush=True)
    components, inst_xy, nets, dbu = parse_def(args.def_file)
    print(f"  components={len(components)}, nets={len(nets)}, "
          f"placed_instances={len(inst_xy)}, DBU={dbu}", flush=True)

    rows = compute_net_features(nets, inst_xy, dbu, args.util, args.cp)
    print(f"  qualifying nets (2-50 pins): {len(rows)}", flush=True)

    fieldnames = ["netName", "util", "cp", "bboxArea", "bboxAr", "numPins"]
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[generate_features] Wrote {len(rows)} rows -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
