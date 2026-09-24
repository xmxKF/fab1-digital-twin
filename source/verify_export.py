# freecadcmd：重开原生文件 → 校验与 layout.json 一致 → 导出求值几何与 IFC
import os, json, FreeCAD as App
ROOT = os.environ["FAB1_ROOT"]
lay = json.load(open(os.path.join(ROOT, "source", "layout.json"), encoding="utf-8"))
doc = App.openDocument(os.path.join(ROOT, "out", "FAB1_V2_四层方案.FCStd"))
by = {d["id"]: d for d in lay["objects"]}
ev, bad, invalid = [], [], []
for o in doc.Objects:
    if o.TypeId != "Part::Box":
        continue
    d = by.get(o.AssetId)
    bb = o.Shape.BoundBox
    if not o.Shape.isValid() or o.Shape.Volume <= 0:
        invalid.append(o.AssetId)
    e = dict(id=o.AssetId, xmin=bb.XMin, ymin=bb.YMin, zmin=bb.ZMin, xmax=bb.XMax, ymax=bb.YMax, zmax=bb.ZMax)
    ev.append(e)
    if d is None or max(abs(bb.XMin - d["x"]), abs(bb.YMin - d["y"]), abs(bb.ZMin - d["z"]), abs(bb.XLength - d["dx"]), abs(bb.YLength - d["dy"]), abs(bb.ZLength - d["dz"])) > 0.01:
        bad.append(o.AssetId)
ids = [e["id"] for e in ev]
# 父子关系 & 平面位置对齐
par_bad = [d["id"] for d in lay["objects"] if d.get("parent") and d["parent"] not in by]
align_bad = []
for d in lay["objects"]:
    if d["cat"] == "aux":
        p = by[d["parent"]]
        if abs((d["x"] + d["dx"] / 2) - (p["x"] + p["dx"] / 2)) > 1 or abs((d["y"] + d["dy"] / 2) - (p["y"] + p["dy"] / 2)) > 1:
            align_bad.append(d["id"])
# 工具在 bay 内、互不重叠
def inside(a, b):
    return a["x"] >= b["x"] and a["y"] >= b["y"] and a["x"] + a["dx"] <= b["x"] + b["dx"] and a["y"] + a["dy"] <= b["y"] + b["dy"]
tools = [d for d in lay["objects"] if d["cat"] == "tool"]
out_bay = [t["id"] for t in tools if not inside(t, by["FAB1-1F-BAY-" + t["bay"]])]
def ov(a, b):
    return a["x"] < b["x"] + b["dx"] and b["x"] < a["x"] + a["dx"] and a["y"] < b["y"] + b["dy"] and b["y"] < a["y"] + a["dy"]
overl = [(a["id"], b["id"]) for i, a in enumerate(tools) for b in tools[i + 1:] if ov(a, b)]
cols = [d for d in lay["objects"] if d["cat"] == "column" and d["level"] == "1F"]
col_hit = [(t["id"], c["id"]) for t in tools for c in cols if ov(t, c)]
json.dump(ev, open(os.path.join(ROOT, "source", "evaluated_geometry.json"), "w"), indent=0)
rep = dict(freecad=".".join(App.Version()[:3]), boxes=len(ev), layout_objects=len(lay["objects"]), unique_ids=len(set(ids)) == len(ids),
           mismatch=bad[:10], mismatch_n=len(bad), invalid_shapes=len(invalid), parent_missing=par_bad, aux_misaligned=len(align_bad),
           tools_outside_bay=out_bay, tool_overlaps=len(overl), tool_column_clash=len(col_hit))
json.dump(rep, open(os.path.join(ROOT, "out", "FreeCAD_QA.json"), "w"), ensure_ascii=False, indent=1)
print("QA", json.dumps(rep, ensure_ascii=False)[-600:])
