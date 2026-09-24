"""由 FreeCAD 求值几何 (evaluated_geometry.json) + layout 属性生成：
  - 每层 1:1 毫米 DXF（模型空间，分图层，含轴网/尺寸/文字）
  - A1 图纸 PDF（B1/1F/2F/RF 平面 1:400、光刻区放大 1:200、A-A/B-B 剖面、说明页）
依赖：ezdxf, matplotlib；中文字体：PDF 用 Noto Sans CJK，DXF 文字样式指定 simhei.ttf（Windows）
"""
import os, json, math
import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.enums import TextEntityAlignment
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle, Circle, Polygon
from matplotlib import font_manager

import plant_config

ROOT = os.environ.get("FAB1_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFG = plant_config.load(); DR = CFG["drawings"]; META = CFG["meta"]
lay = json.load(open(os.path.join(ROOT, "source", "layout.json"), encoding="utf-8"))
ev = {e["id"]: e for e in json.load(open(os.path.join(ROOT, "source", "evaluated_geometry.json")))}
P = lay["params"]; L, W = P["L"], P["W"]; LV = P["levels"]
CX = (P["core"][0] + P["core"][1]) / 2; AX = (P["fabA"][0] + P["fabA"][1]) / 2; BX = (P["fabB"][0] + P["fabB"][1]) / 2; MY = W / 2
ST_ = dict(P["stats"], **{k.lower(): v for k, v in P["stats"]["rf_equip"].items()})
fmt_ = lambda t: t.format(**ST_)
OUT = os.path.join(ROOT, "out"); os.makedirs(OUT, exist_ok=True)

# 以 FreeCAD 求值结果覆盖几何（保证 DXF/PDF 与原生模型一致）
OBJ = []
for d in lay["objects"]:
    e = ev[d["id"]]
    d = dict(d, x=e["xmin"], y=e["ymin"], z=e["zmin"], dx=e["xmax"] - e["xmin"], dy=e["ymax"] - e["ymin"], dz=e["zmax"] - e["zmin"])
    OBJ.append(d)
BY = {d["id"]: d for d in OBJ}

for fp in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
           r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf"):
    if os.path.exists(fp):
        font_manager.fontManager.addfont(fp)
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PROC_RGB = {"LIT": "#F4C542", "ETC": "#E56B5D", "CVD": "#6FA8E8", "ALD": "#5B7FD6", "PVD": "#8B72D1", "DIF": "#EE9A4D",
            "IMP": "#D467A8", "CMP": "#63C08A", "WET": "#4FC3CF", "MET": "#A9CF52"}
PROC_ACI = {"LIT": 2, "ETC": 1, "CVD": 5, "ALD": 150, "PVD": 6, "DIF": 30, "IMP": 210, "CMP": 3, "WET": 4, "MET": 80}
LAYERS = {  # name: (ACI, rgb, lw_pdf)
    "A-GRID": (8, "#9AA0A6", 0.25), "A-WALL": (7, "#2B2F33", 0.6), "A-GLAZ": (4, "#7FB2DE", 0.6), "S-COLS": (7, "#3C4043", 0.3),
    "A-ZONE-CR": (51, "#FFF4C7", 0.2), "A-ZONE-CHASE": (9, "#E3E3E3", 0.2), "A-ZONE-SUPPORT": (200, "#E6DFF7", 0.2),
    "A-ZONE-CORE": (92, "#D9EFD3", 0.2), "A-ZONE-INTERBAY": (41, "#FCE8B0", 0.2), "A-VERT": (94, "#A6D69A", 0.3),
    "M-TOOL": (7, "#888", 0.2), "M-AUX": (5, "#5B8CC7", 0.2), "M-ROOM": (200, "#CFC2EE", 0.3), "P-UTIL": (30, "#F2C28B", 0.3),
    "M-FFU": (140, "#BCD3F5", 0.2), "M-DCC": (130, "#A9DCDC", 0.2), "M-RF": (8, "#C9CCD1", 0.3), "M-STACK": (8, "#8A8D91", 0.3),
    "T-OHT": (30, "#E8930C", 0.5), "T-STK": (30, "#F29A38", 0.3), "A-REF": (8, "#B0B0B0", 0.15), "A-EXT": (4, "#9CC3E6", 0.3),
    "A-TEXT": (7, "#222", 0.2), "A-DIMS": (1, "#C0392B", 0.2), "A-SECT": (1, "#C0392B", 0.5),
}
ZONE_LAYER = {"cleanroom": "A-ZONE-CR", "chase": "A-ZONE-CHASE", "support": "A-ZONE-SUPPORT", "core": "A-ZONE-CORE", "interbay": "A-ZONE-INTERBAY"}
CAT_LAYER = {"wall": "A-WALL", "column": "S-COLS", "tool": "M-TOOL", "aux": "M-AUX", "room": "M-ROOM", "utility": "P-UTIL",
             "ffu": "M-FFU", "dcc": "M-DCC", "rf_equip": "M-RF", "stack": "M-STACK", "stocker": "T-STK", "vertical": "A-VERT", "ext": "A-EXT"}


# ---------------- 通用原语 ----------------
class View:
    """把一组模型坐标原语记录下来，供 DXF 与 PDF 两个后端输出"""
    def __init__(self):
        self.items = []

    def rect(self, layer, x, y, w, h, fill=None, alpha=1.0, lw=None, ls="-", ident=None):
        self.items.append(("rect", layer, x, y, w, h, fill, alpha, lw, ls, ident))

    def line(self, layer, pts, lw=None, ls="-", closed=False):
        self.items.append(("line", layer, pts, lw, ls, closed))

    def circle(self, layer, x, y, r, fill=None):
        self.items.append(("circle", layer, x, y, r, fill))

    def text(self, layer, x, y, s, h, ha="center", va="center", rot=0, bold=False):
        self.items.append(("text", layer, x, y, s, h, ha, va, rot, bold))

    def dim(self, p1, p2, off, horizontal=True, txt=None):
        self.items.append(("dim", "A-DIMS", p1, p2, off, horizontal, txt))


def obj_rect(v, d, layer=None, fill=None, alpha=1.0, lw=None, ls="-"):
    layer = layer or ("A-GLAZ" if d.get("kind") == "curtain" else None) or CAT_LAYER.get(d["cat"]) or ZONE_LAYER.get(d.get("zone"), "A-ZONE-CR")
    v.rect(layer, d["x"], d["y"], d["dx"], d["dy"], fill if fill is not None else LAYERS[layer][1], alpha, lw, ls, d["id"])


def grid(v, tags=True):
    gx, gy = P["grid_x"], P["grid_y"]
    ext = 9000; r = 1500
    for i, x in enumerate(gx):
        v.line("A-GRID", [(x, -ext), (x, W + ext)], ls="-.")
        if tags:
            for yy in (-ext - r, W + ext + r):
                v.circle("A-GRID", x, yy, r); v.text("A-TEXT", x, yy, str(i + 1), 1300)
    for j, y in enumerate(gy):
        v.line("A-GRID", [(-ext, y), (L + ext, y)], ls="-.")
        if tags:
            for xx in (-ext - r, L + ext + r):
                v.circle("A-GRID", xx, y, r); v.text("A-TEXT", xx, y, "ABCDEFG"[j], 1300)


def dims(v):
    gx, gy = P["grid_x"], P["grid_y"]
    for a, b in zip(gx, gx[1:]):
        v.dim((a, 0), (b, 0), -6000, True)
    v.dim((0, 0), (L, 0), -14500, True, f"{L:,}")
    for a, b in zip(gy, gy[1:]):
        v.dim((L, a), (L, b), 6000, False)
    v.dim((0, 0), (0, W), -14500, False, f"{W:,}")


def plan(level):
    v = View()
    grid(v)
    objs = [d for d in OBJ if d["level"] == level]
    if level == "B1":
        for d in OBJ:  # 1F bay 投影参照
            if d["id"].startswith("FAB1-1F-BAY-"):
                v.rect("A-REF", d["x"], d["y"], d["dx"], d["dy"], None, 1, 0.15, "--")
        for d in objs:
            if d["cat"] in ("utility",):
                obj_rect(v, d, alpha=0.35, ls="--")
                v.text("A-TEXT", d["x"] + 30000, d["y"] + d["dy"] / 2, d["name"], 1100, ha="left")
        for d in objs:
            if d["cat"] in ("room", "vertical"):
                obj_rect(v, d, alpha=0.8)
                v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, d["name"].split(" (")[0].split("（")[0], 700,
                       rot=90 if d["dx"] < d["dy"] and d["dx"] < 9000 else 0)
            elif d["cat"] == "aux":
                obj_rect(v, d, fill=PROC_RGB[d["proc"]], alpha=0.55)
        for d in OBJ:
            if d["id"].startswith("FAB1-1F-BAY-"):
                v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, "B1·" + d["id"][-3:], 900, rot=90)
    elif level == "1F":
        for d in objs:
            if d["cat"] == "zone":
                z = d.get("zone")
                fill = LAYERS[ZONE_LAYER[z]][1]
                obj_rect(v, d, fill=fill, alpha=0.9 if z != "chase" else 0.8)
        for d in objs:
            if d["cat"] in ("room", "vertical", "stocker"):
                obj_rect(v, d, alpha=0.9)
            if d["cat"] == "tool":
                obj_rect(v, d, fill=PROC_RGB[d["proc"]])
        for r in lay["oht"]:
            v.line("T-OHT", [tuple(p) for p in r["pts"]], closed=bool(r.get("loop")))
        for d in objs:
            if d["id"].startswith("FAB1-1F-BAY-"):
                n = sum(1 for t in objs if t["cat"] == "tool" and t.get("bay") == d["id"][-3:])
                v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2,
                       f"{d['id'][-3:]} {P['proc'][d['proc']]['name'].split(' ')[0]} {d['iso']} ×{n}", 800, rot=90)
        for d in objs:
            if d["cat"] in ("room", "vertical"):
                v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, d["name"].split(" (")[0].split("（")[0], 650,
                       rot=90 if d["dx"] < d["dy"] and d["dx"] < 9000 else 0)
        nstk = sum(1 for d in objs if d["cat"] == "stocker")
        v.text("A-TEXT", AX, MY, f"中央主通道 Interbay · OHT 主环线 · Stocker ×{nstk}", 1200)
        v.text("A-TEXT", BX, MY, "中央主通道 Interbay · OHT 主环线", 1200)
        v.text("A-TEXT", CX, MY, "Twin-Fab 连接段 / 核心筒（南北玻璃幕墙）", 1300, rot=90)
        v.text("A-TEXT", CX, P["south_bay"][0] / 2 + 150, "南侧灰区服务走廊", 900)
        v.text("A-TEXT", CX, W - P["south_bay"][0] / 2 - 50, "北侧灰区服务走廊", 900)
        v.text("A-TEXT", AX, -24000, "FAB-A（西）", 2200, bold=True); v.text("A-TEXT", BX, -24000, "FAB-B（东）", 2200, bold=True)
        for d in OBJ:
            if d["id"] == "FAB1-EXT-LOBBY":
                obj_rect(v, d, alpha=0.6); v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, "主入口门厅", 1100, rot=90)
    elif level == "2F":
        for d in objs:
            if d["cat"] == "ffu":
                obj_rect(v, d, alpha=0.9 if d["coverage"] == 1 else 0.55)
                v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, f"FFU {d['id'][-3:]} {int(d['coverage']*100)}% ≈{d['ffu_count']}", 750, rot=90)
            elif d["cat"] in ("dcc",):
                obj_rect(v, d, alpha=0.7)
            elif d["cat"] in ("vertical", "utility"):
                obj_rect(v, d, alpha=0.6, ls="--" if d["cat"] == "utility" else "-")
        v.text("A-TEXT", CX, MY, "工艺排气总管（酸/碱/VOC/一般）", 1100)
    elif level == "RF":
        v.rect("A-REF", 0, 0, L, W, "#F4F5F6", 1, 0.2)
        for d in objs:
            if d["cat"] == "rf_equip":
                obj_rect(v, d, alpha=1)
                v.text("A-TEXT", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, d["name"].split("（")[0].replace(" 空调箱", "").replace(" 外气空调箱", ""), 650)
            elif d["cat"] == "stack":
                v.circle("M-STACK", d["x"] + d["dx"] / 2, d["y"] + d["dy"] / 2, d["dx"] / 2, fill="#8A8D91")
        v.text("A-TEXT", CX, MY, f"连接段屋面 {LV['RF']/1000:+.3f}（不设女儿墙）", 1100, rot=90)
        for xx in (AX, BX):
            v.text("A-TEXT", xx, W * 0.32, f"屋面 {LV['RF']/1000:+.3f}（排水坡度、检修通道待深化）", 1000)
    # 外墙、柱（所有层）
    for d in objs:
        if d["cat"] == "wall":
            obj_rect(v, d)
        elif d["cat"] == "column":
            obj_rect(v, d)
    dims(v)
    return v


def section_x(xc):
    """A-A：沿 X=xc 切（显示 Y-Z）"""
    v = View()
    for d in OBJ:
        if d["x"] <= xc <= d["x"] + d["dx"] and d["cat"] not in ("zone",):
            lay_ = CAT_LAYER.get(d["cat"], "A-REF")
            fill = PROC_RGB.get(d.get("proc")) if d["cat"] in ("tool", "aux") else LAYERS[lay_][1]
            if d["cat"] == "slab":
                fill = "#9DA3A8"
            v.rect(lay_, d["y"], d["z"], d["dy"], d["dz"], fill, 0.9 if d["cat"] not in ("wall",) else 1, None, "-", d["id"])
    sec_common(v, W)
    return v


def section_y(yc):
    v = View()
    for d in OBJ:
        if d["y"] <= yc <= d["y"] + d["dy"] and d["cat"] not in ("zone",):
            lay_ = CAT_LAYER.get(d["cat"], "A-REF")
            fill = PROC_RGB.get(d.get("proc")) if d["cat"] in ("tool", "aux") else LAYERS[lay_][1]
            if d["cat"] == "slab":
                fill = "#9DA3A8"
            v.rect(lay_, d["x"], d["z"], d["dx"], d["dz"], fill, 0.9, None, "-", d["id"])
    sec_common(v, L)
    return v


def sec_common(v, span):
    v.line("A-SECT", [(-25000, 0), (span + 25000, 0)], lw=0.8)
    v.text("A-TEXT", -20000, 1200, "室外地坪 ±0.000", 1100, ha="left", va="bottom")
    names = {"FDN": "基础底板", "B1": "B1 次设备层", "1F": "1F 主洁净室", "2F": "2F 回风夹层", "RF": "RF 屋顶"}
    for k, z in LV.items():
        v.line("A-GRID", [(span, z), (span + 22000, z)], ls="--")
        v.line("A-TEXT", [(span + 2000, z), (span + 3500, z + 1500), (span + 500, z + 1500), (span + 2000, z)])
        v.text("A-TEXT", span + 4500, z + 900, f"{names[k]}  {z/1000:+.3f}", 1200, ha="left")
    for a, b in zip(["B1", "1F", "2F"], ["1F", "2F", "RF"]):
        v.dim((-3000, LV[a]), (-3000, LV[b]), -4000, False, f"{LV[b]-LV[a]:,}")


# ---------------- DXF 后端 ----------------
def to_dxf(v, path, title):
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.MM
    doc.header["$INSUNITS"] = 4
    doc.styles.add("CJK", font="simhei.ttf")
    for n, (aci, rgb, lw) in LAYERS.items():
        doc.layers.add(n, color=aci)
    doc.dimstyles.duplicate_entry("EZDXF", "FAB1")
    ds = doc.dimstyles.get("FAB1")
    ds.dxf.dimtxt = 900; ds.dxf.dimasz = 600; ds.dxf.dimexe = 300; ds.dxf.dimexo = 300; ds.dxf.dimtxsty = "CJK"; ds.dxf.dimdec = 0
    msp = doc.modelspace()
    if "FAB1_DT" not in doc.appids:
        doc.appids.new("FAB1_DT")
    for it in v.items:
        k = it[0]
        if k == "rect":
            _, layer, x, y, w, h, fill, alpha, lw, ls, ident = it
            e = msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": layer})
            if ls == "--":
                e.dxf.linetype = "DASHED"
            if ident:
                d = BY.get(ident, {})
                e.set_xdata("FAB1_DT", [(1000, ident), (1000, d.get("cat", "")), (1000, d.get("proc", "") or ""), (1000, d.get("parent", "") or "")])
                if d.get("cat") == "tool":
                    e.dxf.color = PROC_ACI[d["proc"]]
        elif k == "line":
            _, layer, pts, lw, ls, closed = it
            e = msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": layer})
            if ls == "-.":
                e.dxf.linetype = "CENTER"
            elif ls == "--":
                e.dxf.linetype = "DASHED"
        elif k == "circle":
            _, layer, x, y, r, fill = it
            msp.add_circle((x, y), r, dxfattribs={"layer": layer})
        elif k == "text":
            _, layer, x, y, s, h, ha, va, rot, bold = it
            al = {("center", "center"): TextEntityAlignment.MIDDLE_CENTER, ("left", "center"): TextEntityAlignment.MIDDLE_LEFT,
                  ("left", "bottom"): TextEntityAlignment.BOTTOM_LEFT}.get((ha, va), TextEntityAlignment.MIDDLE_CENTER)
            t = msp.add_text(s, height=h, rotation=rot, dxfattribs={"layer": layer, "style": "CJK"})
            t.set_placement((x, y), align=al)
        elif k == "dim":
            _, layer, p1, p2, off, hor, txt = it
            if hor:
                base = (p1[0], p1[1] + off); angle = 0
            else:
                base = (p1[0] + off, p1[1]); angle = 90
            dd = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dimstyle="FAB1", text=txt or "<>", dxfattribs={"layer": layer})
            dd.render()
    t = msp.add_text(title, height=2500, dxfattribs={"layer": "A-TEXT", "style": "CJK"})
    t.set_placement((0, -34000), align=TextEntityAlignment.BOTTOM_LEFT)
    msp.add_text("单位 mm · 1:1 模型空间 · 原点=西南角外皮 ±0.000 · 概念方案，不用于施工", height=1200,
                 dxfattribs={"layer": "A-TEXT", "style": "CJK"}).set_placement((0, -37500), align=TextEntityAlignment.BOTTOM_LEFT)
    doc.saveas(path)
    return path


# ---------------- PDF 后端 ----------------
A1 = (841, 594)


def draw_view(ax, v, ox, oy, scale, clip=None):
    s = 1.0 / scale
    X = lambda x: ox + x * s
    Y = lambda y: oy + y * s
    for it in v.items:
        k = it[0]
        if k == "rect":
            _, layer, x, y, w, h, fill, alpha, lw, ls, ident = it
            if clip and not (x + w > clip[0] and x < clip[2] and y + h > clip[1] and y < clip[3]):
                continue
            edge = "#2B2F33" if layer in ("A-WALL", "S-COLS") else ("#6b6b6b" if layer in ("M-TOOL",) else "#8a8a8a")
            if layer == "A-REF":
                edge = "#B0B0B0"
            ax.add_patch(Rectangle((X(x), Y(y)), w * s, h * s, facecolor=fill if fill else "none", alpha=alpha,
                                   edgecolor=edge, lw=lw if lw else LAYERS[layer][2], ls=ls))
        elif k == "line":
            _, layer, pts, lw, ls, closed = it
            pp = list(pts) + ([pts[0]] if closed else [])
            if clip and all(not (clip[0] <= p[0] <= clip[2] and clip[1] <= p[1] <= clip[3]) for p in pp) and layer != "A-GRID":
                continue
            ax.plot([X(p[0]) for p in pp], [Y(p[1]) for p in pp], color=LAYERS[layer][1], lw=lw or LAYERS[layer][2] * 1.5,
                    ls={"-.": (0, (8, 2, 1, 2)), "--": (0, (4, 2))}.get(ls, "-"))
        elif k == "circle":
            _, layer, x, y, r, fill = it
            if clip and not (clip[0] - r <= x <= clip[2] + r and clip[1] - r <= y <= clip[3] + r):
                continue
            ax.add_patch(Circle((X(x), Y(y)), r * s, facecolor=fill or "white", edgecolor="#555", lw=0.3))
        elif k == "text":
            _, layer, x, y, s_, h, ha, va, rot, bold = it
            if clip and not (clip[0] <= x <= clip[2] and clip[1] <= y <= clip[3]):
                continue
            ax.text(X(x), Y(y), s_, fontsize=max(h * s * 2.83, 2.2), ha=ha, va=va, rotation=rot, color="#1f1f1f",
                    fontweight="bold" if bold else "normal")
        elif k == "dim":
            _, layer, p1, p2, off, hor, txt = it
            if clip:
                continue
            if hor:
                y0 = p1[1] + off
                ax.plot([X(p1[0]), X(p2[0])], [Y(y0)] * 2, color="#C0392B", lw=0.25)
                for px in (p1[0], p2[0]):
                    ax.plot([X(px)] * 2, [Y(p1[1]), Y(y0) - 1.5 * (1 if off < 0 else -1)], color="#C0392B", lw=0.15)
                    ax.plot([X(px) - 0.6, X(px) + 0.6], [Y(y0) - 0.6, Y(y0) + 0.6], color="#C0392B", lw=0.4)
                ax.text((X(p1[0]) + X(p2[0])) / 2, Y(y0) + 0.5, txt or f"{abs(p2[0]-p1[0]):,.0f}", fontsize=3.2 if not txt else 5,
                        ha="center", va="bottom", color="#C0392B")
            else:
                x0 = p1[0] + off
                ax.plot([X(x0)] * 2, [Y(p1[1]), Y(p2[1])], color="#C0392B", lw=0.25)
                for py in (p1[1], p2[1]):
                    ax.plot([X(p1[0]), X(x0)], [Y(py)] * 2, color="#C0392B", lw=0.15)
                    ax.plot([X(x0) - 0.6, X(x0) + 0.6], [Y(py) - 0.6, Y(py) + 0.6], color="#C0392B", lw=0.4)
                ax.text(X(x0) - 0.6, (Y(p1[1]) + Y(p2[1])) / 2, txt or f"{abs(p2[1]-p1[1]):,.0f}", fontsize=3.2 if not txt else 5,
                        ha="right", va="center", rotation=90, color="#C0392B")


def new_sheet(no, title, scale_txt):
    fig = plt.figure(figsize=(A1[0] / 25.4, A1[1] / 25.4))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, A1[0]); ax.set_ylim(0, A1[1]); ax.axis("off")
    ax.add_patch(Rectangle((10, 10), A1[0] - 20, A1[1] - 20, fill=False, lw=1.0))
    # 标题栏
    tb = [(10, 10, 821, 34)]
    ax.add_patch(Rectangle((10, 10), A1[0] - 20, 34, fill=False, lw=0.8))
    cols = [(10, "专案名称", META["project"]), (250, "图名", title), (470, "比例", scale_txt),
            (540, "图号", no), (610, "版本 / 日期", P["revision"].replace(" / ", " · ")), (700, "状态", P["status"].replace(" / ", " · "))]
    for i, (x, k, val) in enumerate(cols):
        if i:
            ax.plot([x, x], [10, 44], color="k", lw=0.5)
        ax.text(x + 3, 38, k, fontsize=7, color="#555", va="center")
        ax.text(x + 3, 22, val, fontsize=12 if i in (0, 1) else 11, va="center", fontweight="bold" if i == 1 else "normal")
    ax.text(A1[0] - 14, 50, META["basis"],
            fontsize=6.5, ha="right", color="#555")
    return fig, ax


def north(ax, x, y):
    ax.add_patch(Polygon([(x, y + 12), (x - 4, y - 4), (x, y), (x + 4, y - 4)], closed=True, color="k"))
    ax.text(x, y + 15, "N", ha="center", fontsize=12, fontweight="bold")


def scalebar(ax, x, y, scale, meters=(0, 10, 20, 50)):
    s = 1000 / scale
    for a, b in zip(meters, meters[1:]):
        ax.add_patch(Rectangle((x + a * s, y), (b - a) * s, 2, facecolor="k" if meters.index(a) % 2 == 0 else "white", edgecolor="k", lw=0.4))
    for m in meters:
        ax.text(x + m * s, y + 3.5, f"{m}", fontsize=6, ha="center")
    ax.text(x + meters[-1] * s + 3, y + 1, "m", fontsize=6, va="center")


def legend(ax, x, y, items, title="图例"):
    ax.text(x, y, title, fontsize=9, fontweight="bold")
    for i, (c, t) in enumerate(items):
        yy = y - 6 - i * 5.5
        ax.add_patch(Rectangle((x, yy - 1.8), 7, 3.6, facecolor=c, edgecolor="#666", lw=0.3))
        ax.text(x + 9, yy, t, fontsize=7, va="center")


PROC_LEG = [(PROC_RGB[k], f"{k} {P['proc'][k]['name']}（{P['stats']['tool_slots_by_proc'].get(k,0)}）") for k in PROC_RGB]
LEVEL_NAME = {"B1": "B1 次设备层 (Sub-Fab)", "1F": "1F 主洁净室 (Main Cleanroom)", "2F": "2F 夹层回风楼层 (Return Air Plenum / FFU)", "RF": "RF 屋顶层 (Rooftop Mechanical)"}
LEVEL_TITLE = {k: f"{v} 平面图  {LV[k]/1000:+.3f}" for k, v in LEVEL_NAME.items()}

if __name__ == "__main__":
    views = {lv: plan(lv) for lv in ("B1", "1F", "2F", "RF")}
    secA_x = DR["section_a_x"]
    secB_y = DR["section_b_y"]
    vA, vB = section_x(secA_x), section_y(secB_y)
    dxf_files = []
    for lv, v in views.items():
        dxf_files.append(to_dxf(v, os.path.join(OUT, f"FAB1_V2_{lv}_平面_mm.dxf"), META["short_name"] + " " + LEVEL_TITLE[lv]))
    # 剖面 DXF（X 为水平坐标，Y 为标高）
    dxf_files.append(to_dxf(vA, os.path.join(OUT, "FAB1_V2_A-A_剖面_mm.dxf"), f"A-A 横剖面（X={secA_x:,} mm，水平向=项目北 Y）"))
    dxf_files.append(to_dxf(vB, os.path.join(OUT, "FAB1_V2_B-B_剖面_mm.dxf"), f"B-B 纵剖面（Y={secB_y:,} mm，水平向=东 X）"))

    pdf_path = os.path.join(OUT, "FAB1_V2_楼层平面方案_A1.pdf")
    previews = []
    with PdfPages(pdf_path) as pdf:
        # 平面图 1:400
        for i, lv in enumerate(("B1", "1F", "2F", "RF")):
            fig, ax = new_sheet(f"A-10{i+1}", LEVEL_TITLE[lv], "1:400 (A1)")
            ox, oy = 80, 245
            draw_view(ax, views[lv], ox, oy, 400)
            # 剖切线标记
            s = 1 / 400
            ax.plot([ox + secA_x * s] * 2, [oy - 40, oy + W * s + 40], color="#C0392B", lw=0.8, ls=(0, (10, 3, 2, 3)))
            ax.text(ox + secA_x * s + 2, oy + W * s + 38, "A", color="#C0392B", fontsize=10, fontweight="bold")
            ax.plot([ox - 45, ox + L * s + 45], [oy + secB_y * s] * 2, color="#C0392B", lw=0.8, ls=(0, (10, 3, 2, 3)))
            ax.text(ox - 47, oy + secB_y * s + 2, "B", color="#C0392B", fontsize=10, fontweight="bold")
            north(ax, 790, 540); scalebar(ax, 520, 60, 400, (0, 10, 20, 50, 100))
            if lv in ("1F", "B1"):
                legend(ax, 30, 175, PROC_LEG, "工艺设备（槽位数）" if lv == "1F" else "Sub-Fab 配套（对应上层工艺）")
            notes = [fmt_(t) for t in DR["notes"][lv]]
            ax.text(300, 175, "说明", fontsize=9, fontweight="bold")
            for k_, n_ in enumerate(notes):
                ax.text(300, 169 - k_ * 6, f"{k_+1}. {n_}", fontsize=7)
            pdf.savefig(fig); fig.savefig(os.path.join(OUT, f"_preview_{lv}.png"), dpi=60); plt.close(fig)
        # 光刻区放大 1:200（范围取自参数文件）
        fig, ax = new_sheet("A-105", DR["litho_title"], "1:200 (A1)")
        clip = tuple(DR["litho_clip"])
        draw_view(ax, views["1F"], 60 - clip[0] / 200, 95, 200, clip=clip)
        for d in OBJ:
            if d["cat"] == "tool" and d["proc"] == "LIT" and clip[0] <= d["x"] <= clip[2]:
                ax.text(60 + (d["x"] - clip[0] + d["dx"] / 2) / 200, 95 + (d["y"] + d["dy"] / 2) / 200, d["id"].replace("FAB1-1F-", ""),
                        fontsize=3.4, rotation=90, ha="center", va="center")
        ax.text(360, 540, DR["litho_head"], fontsize=10, fontweight="bold")
        for k_, n_ in enumerate(DR["litho_notes"]):
            ax.text(360, 528 - k_ * 8, f"• {n_}", fontsize=7.5)
        north(ax, 790, 540); scalebar(ax, 360, 60, 200, (0, 5, 10, 20))
        pdf.savefig(fig); fig.savefig(os.path.join(OUT, "_preview_A105.png"), dpi=60); plt.close(fig)
        # 剖面
        fig, ax = new_sheet("A-201", "A-A 横剖面 / B-B 纵剖面", "A-A 1:300 · B-B 1:500")
        draw_view(ax, vA, 120, 330, 300)
        ax.text(120, 540, f"A-A 横剖面（X = {secA_x:,}，{DR['section_a_desc']}）", fontsize=11, fontweight="bold")
        draw_view(ax, vB, 110, 110, 500)
        ax.text(110, 250, f"B-B 纵剖面（Y = {secB_y:,}，{DR['section_b_desc']}）", fontsize=11, fontweight="bold")
        pdf.savefig(fig); fig.savefig(os.path.join(OUT, "_preview_A201.png"), dpi=60); plt.close(fig)
        # 说明页
        fig, ax = new_sheet("G-001", "设计依据、面积表与设计决定", "—")
        st = P["stats"]
        fa = f"{L * W / 1e6:,.0f}"; U = DR["level_use"]
        hh = lambda a, b: f"{(LV[b] - LV[a]) / 1000:.3f}"
        rows = [("层", "标高 (m)", "层高 (m)", "外包面积 (㎡)", "主要功能"),
                ("RF 屋顶层", f"{LV['RF']/1000:+.3f}", "—", fa, fmt_(U["RF"])),
                ("2F 回风夹层", f"{LV['2F']/1000:+.3f}", hh("2F", "RF"), fa, fmt_(U["2F"])),
                ("1F 主洁净室", f"{LV['1F']/1000:+.3f}", hh("1F", "2F"), fa, fmt_(U["1F"])),
                ("B1 次设备层", f"{LV['B1']/1000:+.3f}", hh("B1", "1F"), fa, fmt_(U["B1"])),
                ("基础底板", f"{LV['FDN']/1000:+.3f}", hh("FDN", "B1"), "—", fmt_(U["FDN"])),
                ("合计 GFA", "", "", f"{4 * L * W / 1e6:,.0f}", DR["gfa_note"])]
        for i, r in enumerate(rows):
            for j, c in enumerate(r):
                ax.text(30 + [0, 60, 110, 160, 220][j], 540 - i * 9, c, fontsize=8.5, fontweight="bold" if i == 0 else "normal")
        ax.text(30, 460, DR["decision_head"], fontsize=10, fontweight="bold")
        issues = P["decisions"] + ([DR["process_note"]] if DR.get("process_note") else [])
        for i, s_ in enumerate(issues):
            ax.text(30, 450 - i * 9, s_, fontsize=7.6)
        ax.text(30, 370, DR["twin_head"], fontsize=10, fontweight="bold")
        for i, s_ in enumerate(["所有对象带稳定 AssetId；1F 工艺槽位 ↔ B1 配套 ParentAssetId；2F FFU 区 ↔ 1F Bay。",
                                "FCStd / IFC4（Pset_FAB1_DT）/ DXF（XDATA FAB1_DT）/ GLB（节点名 = AssetId）使用同一 ID。"] + DR["twin_notes"]):
            ax.text(30, 360 - i * 9, "• " + s_, fontsize=7.6)
        legend(ax, 560, 540, PROC_LEG, "工艺设备分类（1F 槽位数）")
        pdf.savefig(fig); fig.savefig(os.path.join(OUT, "_preview_G001.png"), dpi=60); plt.close(fig)
    # DXF 回读审计
    qa = {}
    for f in dxf_files:
        d = ezdxf.readfile(f)
        au = d.audit()
        msp = d.modelspace()
        qa[os.path.basename(f)] = {"entities": len(msp), "audit_errors": len(au.errors), "fixes": len(au.fixes),
                                   "xdata_tagged": sum(1 for e in msp.query("LWPOLYLINE") if e.has_xdata("FAB1_DT")),
                                   "extents_mm": (lambda b: [round(b.extmin.x), round(b.extmin.y), round(b.extmax.x), round(b.extmax.y)])(ezbbox.extents(msp.query("LWPOLYLINE")))}
    json.dump(qa, open(os.path.join(OUT, "CAD_QA.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(qa, ensure_ascii=False, indent=1))
