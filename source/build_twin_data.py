"""生成数字孪生网页用的精简数据 web/assets/twin-data.json（全部仿真参数为演示假设，取自厂区参数文件）"""
import json, os
import plant_config

ROOT = os.environ.get("FAB1_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
lay = json.load(open(os.path.join(ROOT, "source", "layout.json"), encoding="utf-8"))
CFG = plant_config.load(); SIMC, WEB = CFG["sim"], CFG["web"]
P = lay["params"]; S = 0.001
tools, bays, aux = [], [], {}
for d in lay["objects"]:
    if d["cat"] == "tool":
        tools.append({"id": d["id"], "p": d["proc"], "b": d["bay"], "f": d["fab"], "x": round((d["x"] + d["dx"] / 2) * S, 3),
                      "y": round((d["y"] + d["dy"] / 2) * S, 3), "z": round((d["z"] + d["dz"]) * S, 3),
                      "w": round(d["dx"] * S, 3), "d": round(d["dy"] * S, 3), "iso": d["iso"], "n": d["name"], "st": d["status"]})
    elif d["cat"] == "aux":
        aux[d["parent"]] = {"id": d["id"], "n": d["name"], "z": round((d["z"] + d["dz"]) * S, 3)}
    elif d["id"].startswith("FAB1-1F-BAY-"):
        bays.append({"id": d["id"][-3:], "p": d["proc"], "iso": d["iso"], "x0": d["x"] * S, "y0": d["y"] * S, "x1": (d["x"] + d["dx"]) * S, "y1": (d["y"] + d["dy"]) * S})
n = {}
for t in tools:
    n[t["p"]] = n.get(t["p"], 0) + 1
# 简化路线：12 个“层模块”，每个工序步代表若干真实工序（真实路线 >1,000 步，此处不复现）
DEP = ["CVD", "ALD", "PVD", "DIF"]
route = []
for m in range(12):
    route += [DEP[m % 4], "LIT", "MET", "ETC", "WET"]
    if m < 4:
        route.append("IMP")
    if m >= 2:
        route.append("CMP")
    route.append("MET")
V = {g: route.count(g) for g in n}
base = SIMC["base_wpm"]
lam = base / SIMC["lot_size"] / (30 * 24)  # WPM → lot/h
U = SIMC["u_target"]
pt = {g: round(U[g] * n[g] / (lam * V[g]), 3) for g in n}  # 反推：基准投片速率时达到目标负荷
out = {
    "meta": {"rev": P["revision"], "status": "模拟数据 · 非实测", "levels": P["levels"], "L": P["L"] * S, "W": P["W"] * S,
             "spine": [P["spine"][0] * S, P["spine"][1] * S], "oht_z": (P["levels"]["1F"] + CFG["oht"]["height"]) * S, "stats": P["stats"],
             "note": f"工序时间按 {base:,} WPM 时各设备组目标负荷反推，仅用于演示流动与瓶颈，不代表真实工艺节拍。",
             "note_extra": WEB.get("note_extra", "").format(n_tools=len(tools)),
             "title": WEB["title"], "subtitle": WEB["subtitle"], "tag": WEB["tag"],
             "views": WEB["views"], "explode": WEB["explode"],
             "rate": {"base": base, "min": SIMC["rate_min"], "max": SIMC["rate_max"], "step": SIMC["rate_step"]}},
    "proc": {k: {"name": v["name"], "iso": v["iso"], "n": n.get(k, 0), "visits": V.get(k, 0), "pt_h": pt.get(k, 0), "u_target": U.get(k)} for k, v in P["proc"].items()},
    "route": route, "tools": tools, "bays": bays, "aux": aux,
    "sim": {"lot_size": SIMC["lot_size"], "base_wpm": base, "transfer_h": SIMC["transfer_h"], "mtbf_h": SIMC["mtbf_h"], "mttr_h": SIMC["mttr_h"], "warmup_days": SIMC["warmup_days"]},
}
os.makedirs(os.path.join(ROOT, "web", "assets"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "web", "assets", "twin-data.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(route), "steps", V, pt)
# 托管网页不支持 .glb 类型时使用的 base64 副本
import base64
g = os.path.join(ROOT, "web", "assets", "fab1_v2.glb")
if os.path.exists(g):
    json.dump({"b64": base64.b64encode(open(g, "rb").read()).decode()}, open(g + ".json", "w"))
