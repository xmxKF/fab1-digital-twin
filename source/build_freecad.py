# FreeCAD 1.0.x 宏：由 layout.json 生成 FAB1_V2 原生模型（需 GUI 以保存颜色；可用 xvfb 无头运行）
# 用法：设置环境变量 FAB1_ROOT=包根目录，然后  freecad build_freecad.py
import os, json, sys
import FreeCAD as App
import Part

ROOT = os.environ.get("FAB1_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "source", "layout.json")
OUTDIR = os.path.join(ROOT, "out"); os.makedirs(OUTDIR, exist_ok=True)
FC = os.path.join(OUTDIR, "FAB1_V2_四层方案.FCStd")
data = json.load(open(SRC, encoding="utf-8"))
P = data["params"]

try:
    import FreeCADGui as Gui
    HAS_GUI = Gui.getMainWindow() is not None
except Exception:
    HAS_GUI = False

PROC_COL = {"LIT": (0.98, 0.84, 0.35), "ETC": (0.93, 0.45, 0.40), "CVD": (0.45, 0.70, 0.95), "ALD": (0.40, 0.55, 0.90),
            "PVD": (0.55, 0.45, 0.85), "DIF": (0.95, 0.62, 0.30), "IMP": (0.85, 0.40, 0.70), "CMP": (0.45, 0.80, 0.60),
            "WET": (0.35, 0.80, 0.85), "MET": (0.70, 0.85, 0.35)}
CAT_COL = {"slab": ((0.78, 0.78, 0.78), 0), "wall": ((0.86, 0.87, 0.89), 55), "column": ((0.55, 0.55, 0.58), 0),
           "aux": ((0.35, 0.55, 0.78), 0), "ffu": ((0.62, 0.76, 0.96), 45), "dcc": ((0.50, 0.80, 0.80), 40),
           "rf_equip": ((0.82, 0.83, 0.85), 0), "stack": ((0.62, 0.62, 0.64), 0), "vertical": ((0.62, 0.82, 0.58), 30),
           "room": ((0.76, 0.70, 0.90), 40), "utility": ((0.92, 0.70, 0.40), 35), "stocker": ((0.95, 0.60, 0.20), 0),
           "ext": ((0.55, 0.72, 0.90), 50), "zone": ((0.98, 0.93, 0.70), 85)}
ZONE_COL = {"cleanroom": (0.98, 0.93, 0.70), "chase": (0.80, 0.80, 0.80), "interbay": (0.98, 0.88, 0.55),
            "support": (0.78, 0.72, 0.92), "core": (0.62, 0.82, 0.58)}
LEVEL_NAME = {k: f"{v} {P['levels'][k] / 1000:+.3f}" for k, v in
              {"FDN": "FDN 基础底板", "B1": "B1 次设备层 Sub-Fab", "1F": "1F 主洁净室", "2F": "2F 回风夹层", "RF": "RF 屋顶机电"}.items()}
CAT_NAME = {"slab": "楼板", "wall": "墙体", "column": "结构柱", "tool": "工艺设备槽位", "aux": "Sub-Fab 配套设备",
            "zone": "空间分区", "ffu": "FFU 区", "dcc": "DCC 回风", "rf_equip": "屋顶机电", "stack": "排气烟囱",
            "vertical": "竖向交通/竖井", "room": "辅助房间", "utility": "管廊/总管", "stocker": "Stocker", "ext": "外部附属"}

doc = App.newDocument("FAB1_V2")
doc.Comment = f"FAB-1 四层楼层方案 {P['revision']} | {P['status']} | 单位 mm | 原点 西南角 ±0.000"
groups = {}


def grp(level, cat):
    if level not in groups:
        g = doc.addObject("App::DocumentObjectGroup", "L_" + level)
        g.Label = LEVEL_NAME[level]
        groups[level] = {"_": g}
    gl = groups[level]
    if cat not in gl:
        s = doc.addObject("App::DocumentObjectGroup", f"G_{level}_{cat}")
        s.Label = f"{level} · {CAT_NAME.get(cat, cat)}"
        gl["_"].addObject(s)
        gl[cat] = s
    return gl[cat]


def props(o, d):
    for k, prop, typ in (("id", "AssetId", "App::PropertyString"), ("name", "NameCN", "App::PropertyString"),
                         ("cat", "Category", "App::PropertyString"), ("level", "Level", "App::PropertyString"),
                         ("proc", "Process", "App::PropertyString"), ("parent", "ParentAssetId", "App::PropertyString"),
                         ("iso", "IsoClass", "App::PropertyString"), ("status", "DataStatus", "App::PropertyString"),
                         ("bay", "Bay", "App::PropertyString"), ("kind", "Kind", "App::PropertyString")):
        o.addProperty(typ, prop, "DigitalTwin")
        setattr(o, prop, str(d.get(k, "")))
    if "ffu_count" in d:
        o.addProperty("App::PropertyInteger", "FFUCount", "DigitalTwin"); o.FFUCount = int(d["ffu_count"])


for d in data["objects"]:
    lv = "1F" if d["cat"] == "ext" and d["level"] == "1F" else d["level"]
    lv = "ext" if False else lv
    o = doc.addObject("Part::Box", d["id"].replace("-", "_"))
    o.Label = d["id"]
    o.Length, o.Width, o.Height = d["dx"], d["dy"], d["dz"]
    o.Placement = App.Placement(App.Vector(d["x"], d["y"], d["z"]), App.Rotation())
    props(o, d)
    grp(d["level"], d["cat"]).addObject(o)
    if HAS_GUI:
        v = o.ViewObject
        if d["cat"] == "tool":
            v.ShapeColor = PROC_COL[d["proc"]]; tr = 0
        elif d["cat"] == "zone":
            v.ShapeColor = ZONE_COL.get(d.get("zone"), (0.9, 0.9, 0.9)); tr = 85
            v.DisplayMode = "Wireframe" if d.get("zone") in ("chase",) else "Flat Lines"
        elif d.get("kind") == "curtain":
            v.ShapeColor = (0.50, 0.70, 0.87); tr = 60
        else:
            c, tr = CAT_COL.get(d["cat"], ((0.8, 0.8, 0.8), 0)); v.ShapeColor = c
        v.Transparency = tr

# OHT 轨道（轨顶高度取自参数文件）
sys.path.insert(0, os.path.join(ROOT, "source")); import plant_config
zo = P["levels"]["1F"] + plant_config.load()["oht"]["height"]
og = grp("1F", "oht"); og.Label = "1F · OHT 天车轨道"
for r in data["oht"]:
    pts = [App.Vector(x, y, zo) for x, y in r["pts"]]
    if r.get("loop"):
        pts.append(pts[0])
    f = doc.addObject("Part::Feature", r["id"].replace("-", "_"))
    f.Label = r["id"]; f.Shape = Part.makePolygon(pts)
    f.addProperty("App::PropertyString", "AssetId", "DigitalTwin"); f.AssetId = r["id"]
    og.addObject(f)
    if HAS_GUI:
        f.ViewObject.LineColor = (0.95, 0.65, 0.1); f.ViewObject.LineWidth = 3

# 轴网（放在 ±0 平面，仅作参照）
ag = doc.addObject("App::DocumentObjectGroup", "Grid"); ag.Label = f"轴网 1–{len(P['grid_x'])} / A–{'ABCDEFGHIJKLMN'[len(P['grid_y']) - 1]}"
for i, x in enumerate(P["grid_x"]):
    f = doc.addObject("Part::Feature", f"AX_{i+1}"); f.Label = f"轴 {i+1}"
    f.Shape = Part.makeLine(App.Vector(x, -8000, 0), App.Vector(x, P["W"] + 8000, 0)); ag.addObject(f)
for j, y in enumerate(P["grid_y"]):
    f = doc.addObject("Part::Feature", f"AY_{'ABCDEFG'[j]}"); f.Label = f"轴 {'ABCDEFG'[j]}"
    f.Shape = Part.makeLine(App.Vector(-8000, y, 0), App.Vector(P["L"] + 8000, y, 0)); ag.addObject(f)

doc.recompute()
# 参数表（Spreadsheet）
try:
    import Spreadsheet
    sh = doc.addObject("Spreadsheet::Sheet", "Params"); sh.Label = "参数与统计"
    rows = [("项目", "值"), ("版本", P["revision"]), ("状态", P["status"]), ("外包 L×W (mm)", f"{P['L']}×{P['W']}"),
            ("标高 FDN/B1/1F/2F/RF (mm)", "/".join(str(P['levels'][k]) for k in ("FDN", "B1", "1F", "2F", "RF")))]
    rows += [(k, json.dumps(v, ensure_ascii=False)) for k, v in P["stats"].items()]
    for i, (a, b) in enumerate(rows, 1):
        sh.set(f"A{i}", "'" + str(a)); sh.set(f"B{i}", "'" + str(b))
    doc.recompute()
except Exception as e:
    print("sheet skipped", e)

doc.saveAs(FC)
print("SAVED", FC, "objects", len(doc.Objects), "gui", HAS_GUI)
if HAS_GUI:
    try:
        Gui.activeDocument().activeView().viewAxonometric(); Gui.SendMsgToActiveView("ViewFit")
        doc.save()
    except Exception as e:
        print("view", e)
    os._exit(0)
