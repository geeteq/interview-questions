"""Generate a datacenter-rack.drawio diagram.

Layout:
  • Network elements at the top (cloud, two leaf routers, remote mgmt switch)
  • Front-view rack on the left  (42U, 21 servers at bottom, 3 switches at top)
  • Back-view rack on the right  (same equipment + two vertical PDUs)
  • Front-view links: each prod switch → both leafs (redundant), mgmt → remote mgmt
  • Cloud links: leaf1, leaf2, and remote mgmt all connect to cloud

Run:  python3 scripts/build_rack_diagram.py
Outputs: datacenter-rack.drawio
"""
from html import escape

cells = []
_id = 1

def cell(value, x, y, w, h, style):
    global _id
    _id += 1
    cid = f"v{_id}"
    cells.append(
        f'<mxCell id="{cid}" value="{escape(value)}" style="{style}" vertex="1" parent="1">'
        f'<mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/></mxCell>'
    )
    return cid

def edge(src, tgt, style, label=""):
    global _id
    _id += 1
    cid = f"e{_id}"
    cells.append(
        f'<mxCell id="{cid}" value="{escape(label)}" style="{style}" edge="1" parent="1" '
        f'source="{src}" target="{tgt}"><mxGeometry relative="1" as="geometry"/></mxCell>'
    )
    return cid

# ── Styles ─────────────────────────────────────────────────────────────────────
S_TEXT_TITLE = "text;html=1;align=center;verticalAlign=middle;fontSize=20;fontStyle=1"
S_TEXT_HD    = "text;html=1;align=center;verticalAlign=middle;fontSize=14;fontStyle=1;fillColor=#eeeeee;strokeColor=#666666"
S_RACK       = "rounded=0;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#000000;strokeWidth=3"
S_MGMT       = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;fontStyle=1"
S_PROD       = "rounded=0;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;fontStyle=1"
S_SERVER     = "rounded=0;whiteSpace=wrap;html=1;fillColor=#fff2cc;strokeColor=#d6b656;fontSize=9"
S_PDU        = "rounded=0;whiteSpace=wrap;html=1;fillColor=#e1d5e7;strokeColor=#9673a6;fontSize=10;fontStyle=1;horizontal=0"
S_BACK_DIM   = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#999999;fontSize=9;fontColor=#666666"
S_BACK_MGMT  = "rounded=0;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;fontSize=10;fontStyle=1;opacity=70"
S_BACK_PROD  = "rounded=0;whiteSpace=wrap;html=1;fillColor=#d5e8d4;strokeColor=#82b366;fontSize=10;fontStyle=1;opacity=70"

S_CLOUD  = "ellipse;shape=cloud;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;fontSize=14;fontStyle=1"
S_ROUTER = ("shape=mxgraph.cisco.routers.router;html=1;pointerEvents=1;dashed=0;"
            "fillColor=#036897;strokeColor=#ffffff;labelPosition=center;verticalLabelPosition=bottom;"
            "align=center;verticalAlign=top;fontSize=11;fontStyle=1")
S_SWITCH = ("shape=mxgraph.cisco.switches.workgroup_switch;html=1;pointerEvents=1;dashed=0;"
            "fillColor=#036897;strokeColor=#ffffff;labelPosition=center;verticalLabelPosition=bottom;"
            "align=center;verticalAlign=top;fontSize=11;fontStyle=1")

E_PROD = "endArrow=none;html=1;strokeColor=#0066CC;strokeWidth=2;exitX=0.5;exitY=0;exitDx=0;exitDy=0;entryX=0.5;entryY=1;entryDx=0;entryDy=0"
E_MGMT = "endArrow=none;html=1;strokeColor=#D79B00;strokeWidth=2;dashed=1;exitX=0.5;exitY=0;exitDx=0;exitDy=0;entryX=0.5;entryY=1;entryDx=0;entryDy=0"
E_CLOUD= "endArrow=none;html=1;strokeColor=#666666;strokeWidth=2;exitX=0.5;exitY=0;exitDx=0;exitDy=0;entryX=0.5;entryY=1;entryDx=0;entryDy=0"

# ── Geometry ───────────────────────────────────────────────────────────────────
U = 19
RACK_W = 240
RACK_INNER_TOP = 360
N_U = 42
RACK_INNER_H = N_U * U   # 798

FRONT_X = 60
BACK_X  = 1100   # back-view rack pinned to the far right of the page

# Network row at top
NET_Y = 60

# ── Build ──────────────────────────────────────────────────────────────────────
# Title
cell("Datacenter Rack — 42U Front + Back View",
     FRONT_X, 10, 900, 30, S_TEXT_TITLE)

# Network: cloud at top-center, remote-mgmt directly below cloud, leafs flanking
CLOUD_X, CLOUD_W = 540, 180          # cloud center @ x=630
RMGMT_W = 100                        # remote-mgmt center @ x=630 (under cloud)
cloud  = cell("Internet / WAN Cloud", CLOUD_X, NET_Y,           CLOUD_W, 90, S_CLOUD)
rmgmt  = cell("Remote MGMT Switch",   CLOUD_X + (CLOUD_W - RMGMT_W) // 2,
              NET_Y + 140, RMGMT_W, 60, S_SWITCH)
leaf1  = cell("Leaf 1",               420, NET_Y + 140,  80, 60, S_ROUTER)
leaf2  = cell("Leaf 2",               720, NET_Y + 140,  80, 60, S_ROUTER)

# Cloud uplinks (leafs and remote mgmt → cloud)
edge(leaf1, cloud, "endArrow=none;html=1;strokeColor=#666666;strokeWidth=2", label="WAN")
edge(leaf2, cloud, "endArrow=none;html=1;strokeColor=#666666;strokeWidth=2")
edge(rmgmt, cloud, "endArrow=none;html=1;strokeColor=#666666;strokeWidth=2;dashed=1", label="Mgmt")

# Section labels
cell("FRONT VIEW", FRONT_X, RACK_INNER_TOP - 30, RACK_W, 25, S_TEXT_HD)
cell("BACK VIEW",  BACK_X,  RACK_INNER_TOP - 30, RACK_W, 25, S_TEXT_HD)

# ── FRONT RACK frame ──
cell("", FRONT_X, RACK_INNER_TOP, RACK_W, RACK_INNER_H, S_RACK)

# Top switches (U42 mgmt, U41 prod1, U40 prod2)
def y_for_u(u):
    """Top y-coord for a unit number (1=bottom, 42=top)."""
    return RACK_INNER_TOP + (N_U - u) * U

front_mgmt  = cell("MGMT Switch — U42",         FRONT_X, y_for_u(42), RACK_W, U, S_MGMT)
front_prod1 = cell("Production Switch 1 — U41", FRONT_X, y_for_u(41), RACK_W, U, S_PROD)
front_prod2 = cell("Production Switch 2 — U40", FRONT_X, y_for_u(40), RACK_W, U, S_PROD)

# 21 servers at the bottom (U1..U21)
for n in range(1, 22):
    cell(f"Server {n:02d} — U{n}", FRONT_X, y_for_u(n), RACK_W, U, S_SERVER)

# ── BACK RACK frame + dimmed equipment + side PDUs ──
cell("", BACK_X, RACK_INNER_TOP, RACK_W, RACK_INNER_H, S_RACK)

# Equipment area is now the full back-rack width
cell("MGMT (rear)",         BACK_X, y_for_u(42), RACK_W, U, S_BACK_MGMT)
cell("PROD SW 1 (rear)",    BACK_X, y_for_u(41), RACK_W, U, S_BACK_PROD)
cell("PROD SW 2 (rear)",    BACK_X, y_for_u(40), RACK_W, U, S_BACK_PROD)
for n in range(1, 22):
    cell(f"Server {n:02d} (rear)", BACK_X, y_for_u(n), RACK_W, U, S_BACK_DIM)

# Vertical PDUs — one on each outer side of the back-view cabinet
PDU_W   = 22
PDU_GAP = 6
cell("PDU A — vertical (rear left)",
     BACK_X - PDU_GAP - PDU_W, RACK_INNER_TOP, PDU_W, RACK_INNER_H, S_PDU)
cell("PDU B — vertical (rear right)",
     BACK_X + RACK_W + PDU_GAP, RACK_INNER_TOP, PDU_W, RACK_INNER_H, S_PDU)

# ── Front-view connections ──
# Production switches → both leaf routers (redundant)
edge(front_prod1, leaf1, E_PROD, label="uplink")
edge(front_prod1, leaf2, E_PROD)
edge(front_prod2, leaf1, E_PROD)
edge(front_prod2, leaf2, E_PROD, label="redundant")

# Management switch → remote management switch
edge(front_mgmt, rmgmt, E_MGMT, label="mgmt uplink")

# ── Legend ──
LEG_X, LEG_Y = 540, 1180
cell("Legend",                         LEG_X,        LEG_Y,        200, 25, "text;html=1;fontStyle=1;fontSize=12;align=left")
cell("Production data link",           LEG_X + 20,   LEG_Y + 30,   180, 18, "text;html=1;fontSize=11;align=left;strokeColor=none")
cell("",                               LEG_X,        LEG_Y + 38,    15,  2, "rounded=0;fillColor=#0066CC;strokeColor=#0066CC")
cell("Management uplink (dashed)",     LEG_X + 20,   LEG_Y + 55,   180, 18, "text;html=1;fontSize=11;align=left;strokeColor=none")
cell("",                               LEG_X,        LEG_Y + 63,    15,  2, "rounded=0;fillColor=none;strokeColor=#D79B00;dashed=1")
cell("Cloud / WAN",                    LEG_X + 20,   LEG_Y + 80,   180, 18, "text;html=1;fontSize=11;align=left;strokeColor=none")
cell("",                               LEG_X,        LEG_Y + 88,    15,  2, "rounded=0;fillColor=#666666;strokeColor=#666666")

# ── Wrap ──
xml = (
    '<mxfile host="app.diagrams.net" agent="Claude" version="22.0.0">'
    '<diagram id="rack" name="Rack Layout">'
    '<mxGraphModel dx="1400" dy="1200" grid="1" gridSize="10" guides="1" tooltips="1" '
    'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1420" pageHeight="1300" '
    'math="0" shadow="0">'
    '<root><mxCell id="0"/><mxCell id="1" parent="0"/>'
    + "".join(cells) +
    "</root></mxGraphModel></diagram></mxfile>"
)

with open("datacenter-rack.drawio", "w") as f:
    f.write(xml)

print(f"Wrote datacenter-rack.drawio ({len(xml):,} bytes, {len(cells)} cells)")
