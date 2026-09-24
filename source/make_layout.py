"""楼层方案布局生成器（概念方案，非施工图）
几何全部由厂区参数文件驱动（见 plant_config.py），本脚本不含任何厂区规格。
单位 mm；原点=建筑西南角外皮、室外地坪 ±0.000；+X 东，+Y 项目北，+Z 上。
输出 layout.json：所有对象为轴对齐长方体（min 角点 + 尺寸），供 FreeCAD / DXF / Blender / Web 共用。
"""
import json, os
import plant_config

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "layout.json")
C = plant_config.load()
E, FB = C["envelope"], C["fab"]

L, W = E["L"], E["W"]
end, pitch = E["grid_x_end"], E["grid_x_pitch"]
NM, MOD = FB["n_modules"], FB["module"]
fabA = [end, end + NM * MOD]
fabB = [L - end - NM * MOD, L - end]
core = [fabA[1], fabB[0]]
assert core[1] - core[0] == FB["core_width"], "L 与 端跨/模块数/核心宽度 不闭合"
corr, spw = FB["corridor"], FB["spine"]
spine = [(W - spw) / 2, (W + spw) / 2]

P = {
    "revision": C["meta"]["revision"],
    "status": C["meta"]["status"],
    "units": "mm",
    "L": L, "W": W,
    "levels": E["levels"],
    "grade": E["grade"],
    "parapet": E["parapet"],
    "ext_wall": E["ext_wall"], "partition": E["partition"],
    "slab": E["slab"],
    "col_B1": E["col_B1"], "col_up": E["col_up"],
    "grid_x": None, "grid_y": list(range(0, W + 1, E["grid_y_pitch"])),
    "fabA": fabA, "core": core, "fabB": fabB,
    "south_bay": [corr, int(spine[0])], "spine": [int(spine[0]), int(spine[1])], "north_bay": [int(spine[1]), W - corr],
    "module": MOD, "chase": FB["chase"],
    "decisions": C["meta"].get("decisions", []),
}
gx = [0, end]
while gx[-1] < L - end:
    gx.append(gx[-1] + pitch)
gx.append(L)
P["grid_x"] = gx
assert abs(gx[-2] - (L - end)) < 1, "X 轴网不闭合"

LV = P["levels"]
objs = []


def add(id, cat, level, x, y, z, dx, dy, dz, **kw):
    o = dict(id=id, cat=cat, level=level, x=round(x), y=round(y), z=round(z),
             dx=round(dx), dy=round(dy), dz=round(dz))
    o.update(kw)
    o.setdefault("status", "assumption")
    objs.append(o)
    return o


NEXT = {"B1": "1F", "1F": "2F", "2F": "RF"}

# ---------------- 结构：楼板 / 外墙 / 柱 ----------------
add("FAB1-FDN-SLAB", "slab", "FDN", 0, 0, LV["FDN"], L, W, LV["B1"] - LV["FDN"], name="基础底板", status="drawing")
floors = [("B1", LV["B1"], LV["1F"]), ("1F", LV["1F"], LV["2F"]), ("2F", LV["2F"], LV["RF"])]
for lv, z0, z1 in floors:
    t = P["slab"][lv] if lv != "B1" else 0
    if lv != "B1":
        add(f"FAB1-{lv}-SLAB", "slab", lv, 0, 0, z0 - t, L, W, t, name=f"{lv} 楼板" + ("（华夫板）" if lv == "1F" else ""), status="drawing")
    h = z1 - z0 - (P["slab"].get(NEXT[lv], 0))
    ew = P["ext_wall"]
    # Twin-Fab：南北外墙按 FAB-A / 连接段 / FAB-B 三段，连接段为玻璃幕墙
    for seg, (sx0, sx1), kind, nm in (("A", (0, core[0]), "solid", "FAB-A"), ("C", core, "curtain", "连接段玻璃幕墙"),
                                      ("B", (core[1], L), "solid", "FAB-B")):
        add(f"FAB1-{lv}-WALL-S-{seg}", "wall", lv, sx0, 0, z0, sx1 - sx0, ew, h, name=f"南外墙 {nm}", face="S", kind=kind)
        add(f"FAB1-{lv}-WALL-N-{seg}", "wall", lv, sx0, W - ew, z0, sx1 - sx0, ew, h, name=f"北外墙 {nm}", face="N", kind=kind)
    add(f"FAB1-{lv}-WALL-W", "wall", lv, 0, ew, z0, ew, W - 2 * ew, h, name="西外墙", face="W", kind="solid")
    add(f"FAB1-{lv}-WALL-E", "wall", lv, L - ew, ew, z0, ew, W - 2 * ew, h, name="东外墙", face="E", kind="solid")
add("FAB1-RF-SLAB", "slab", "RF", 0, 0, LV["RF"] - P["slab"]["RF"], L, W, P["slab"]["RF"], name="屋面板", status="drawing")
# 屋面：两座体块各自围合女儿墙/设备围护，连接段屋面不设
pp = P["parapet"]; cx0, cx1 = core
for s, (x, y, dx, dy) in {"S-A": (0, 0, cx0, 300), "N-A": (0, W - 300, cx0, 300), "W": (0, 300, 300, W - 600), "AE": (cx0 - 300, 300, 300, W - 600),
                          "S-B": (cx1, 0, L - cx1, 300), "N-B": (cx1, W - 300, L - cx1, 300), "E": (L - 300, 300, 300, W - 600), "BW": (cx1, 300, 300, W - 600)}.items():
    add(f"FAB1-RF-PARAPET-{s}", "wall", "RF", x, y, LV["RF"], dx, dy, pp, name="女儿墙/屋面设备围护", kind="solid")

# 柱：B1 满轴网；1F/2F 仅落在 chase 线与核心筒/端部（大跨假设）
cb = P["col_B1"]
for i, x in enumerate(gx):
    for j, y in enumerate(P["grid_y"]):
        e_ = P["ext_wall"]; cx = min(max(x, e_ + cb / 2), L - e_ - cb / 2); cy = min(max(y, e_ + cb / 2), W - e_ - cb / 2)
        add(f"FAB1-B1-COL-{i+1:02d}{'ABCDEFGHIJKLMN'[j]}", "column", "B1", cx - cb / 2, cy - cb / 2, LV["B1"], cb, cb, LV["1F"] - P["slab"]["1F"] - LV["B1"], name=f"B1 柱 {i+1}/{'ABCDEFGHIJKLMN'[j]}")
up_x = sorted(set([0, L] + [fabA[0] + MOD * k for k in range(NM + 1)] + [fabB[0] + MOD * k for k in range(NM + 1)]))
cu = P["col_up"]
for lv, z0, z1 in floors[1:]:
    for x in up_x:
        i = gx.index(x) if x in gx else -1
        for j, y in enumerate(P["grid_y"]):
            e_ = P["ext_wall"]; cx = min(max(x, e_ + cu / 2), L - e_ - cu / 2); cy = min(max(y, e_ + cu / 2), W - e_ - cu / 2)
            add(f"FAB1-{lv}-COL-{i+1:02d}{'ABCDEFGHIJKLMN'[j]}", "column", lv, cx - cu / 2, cy - cu / 2, z0, cu, cu,
                z1 - z0 - P["slab"][NEXT[lv]], name=f"{lv} 柱 {i+1}/{'ABCDEFGHIJKLMN'[j]}")

# ---------------- 1F 主洁净室 ----------------
z1F = LV["1F"]; H1 = LV["2F"] - P["slab"]["2F"] - z1F
PROC = C["proc"]
TL, OH = C["tool_layout"], C["oht"]
chase = P["chase"]
tools = []
oht = []
for fab, (fx0, fx1), bays in (("A", fabA, FB["bays_A"]), ("B", fabB, FB["bays_B"])):
    for k in range(NM):
        # 模块网格线：FAB-A 自西向东，FAB-B 自东向西（镜像，最后一个模块靠核心）
        if fab == "A":
            g0 = fx0 + MOD * k; bx0 = g0 + chase / 2; bx1 = g0 + MOD - chase / 2
        else:
            g0 = fx1 - MOD * k; bx1 = g0 - chase / 2; bx0 = g0 - MOD + chase / 2
        cx0_ = g0 - chase / 2
        for side, (y0, y1) in (("S", P["south_bay"]), ("N", P["north_bay"])):
            proc = bays[side][k]
            pr = PROC[proc]
            name, (tx, ty, th), pitch_, iso = pr["name"], pr["env"], pr["pitch"], pr["iso"]
            bay_id = f"{fab}{side}{k+1}"
            add(f"FAB1-1F-BAY-{bay_id}", "zone", "1F", bx0, y0, z1F, bx1 - bx0, y1 - y0, H1,
                name=f"Bay {bay_id} {name}", proc=proc, iso=iso, zone="cleanroom")
            add(f"FAB1-1F-CHS-{bay_id}", "zone", "1F", cx0_, y0, z1F, chase, y1 - y0, H1,
                name=f"Chase {bay_id}", zone="chase", iso="ISO 6-7")
            n = int((y1 - y0 - TL["end_clear"]) // pitch_)
            off = (y1 - y0 - n * pitch_) / 2
            for r, rx in enumerate((bx0 + TL["edge_gap"], bx1 - TL["edge_gap"] - tx)):
                for m in range(n):
                    ty0 = y0 + off + m * pitch_ + (pitch_ - ty) / 2
                    idx = r * n + m + 1
                    tid = f"FAB1-1F-{proc}-{bay_id}-{idx:02d}"
                    t = add(tid, "tool", "1F", rx, ty0, z1F, tx, ty, th, name=f"{name} {bay_id}-{idx:02d}",
                            proc=proc, bay=bay_id, fab=fab, iso=iso, face=("E" if r == 0 else "W"),
                            status=pr.get("status", "assumption"))
                    tools.append(t)
            # OHT 支线：沿 aisle 中心 U 形回路
            ax = (bx0 + bx1) / 2; hg, eo = OH["half_gap"], OH["end_off"]
            if side == "S":
                oht.append({"id": f"OHT-{bay_id}", "pts": [[ax - hg, P["spine"][0]], [ax - hg, y0 + eo], [ax + hg, y0 + eo], [ax + hg, P["spine"][0]]]})
            else:
                oht.append({"id": f"OHT-{bay_id}", "pts": [[ax - hg, P["spine"][1]], [ax - hg, y1 - eo], [ax + hg, y1 - eo], [ax + hg, P["spine"][1]]]})
# 中央主通道（interbay）+ 主 OHT 环线 + stocker
sp0, sp1 = P["spine"]
ew = P["ext_wall"]; rw = FB["end_room_w"]
spx0, spx1 = ew + rw, L - ew - rw
add("FAB1-1F-SPINE", "zone", "1F", spx0, sp0, z1F, spx1 - spx0, sp1 - sp0, H1, name="中央主通道 / Interbay AMHS", zone="interbay", iso="ISO 5")
mi, lo = OH["main_inset"], OH["loop_off"]
oht.insert(0, {"id": "OHT-MAIN", "loop": True, "pts": [[spx0 + mi, sp0 + lo], [spx1 - mi, sp0 + lo], [spx1 - mi, sp1 - lo], [spx0 + mi, sp1 - lo]]})
ST = C["stockers"]; sdx, sdy, sdz = ST["size"]
for fab, xs in (("A", [fabA[0] + MOD * k + MOD / 2 for k in ST["modules"]]), ("B", [fabB[1] - MOD * k - MOD / 2 for k in ST["modules"]])):
    for i, x in enumerate(xs):
        add(f"FAB1-1F-STK-{fab}{i+1}", "stocker", "1F", x - sdx / 2, sp0 + ST["y_off"], z1F, sdx, sdy, sdz,
            name=f"Stocker {fab}{i+1}", fab=fab)
# 周边与端部
add("FAB1-1F-COR-S", "zone", "1F", ew, ew, z1F, L - 2 * ew, corr - ew, H1, name="南侧灰区服务走廊", zone="support")
add("FAB1-1F-COR-N", "zone", "1F", ew, W - corr, z1F, L - 2 * ew, corr - ew, H1, name="北侧灰区服务走廊", zone="support")
for side, rid, y, dy, nm in C["end_rooms"]:
    x = ew if side == "W" else L - ew - rw
    add(f"FAB1-1F-{rid}", "room", "1F", x, y, z1F, rw, dy, H1, name=nm, zone="support")
add("FAB1-1F-CORE", "zone", "1F", core[0], corr, z1F, core[1] - core[0], W - 2 * corr, H1, name="Twin-Fab 连接段 / 核心筒（南北玻璃幕墙）", zone="core")
# 楼梯/电梯（竖向交通）：各层均设
for sid, x, y, dx, dy, nm in C["vertical"]:
    for lv, z0, z1 in floors:
        add(f"FAB1-{lv}-{sid}", "vertical", lv, x, y, z0, dx, dy, z1 - z0 - P["slab"][NEXT[lv]], name=nm)

# ---------------- B1 次设备层 Sub-Fab ----------------
B1C = C["b1"]
zB = LV["B1"]
for t in tools:
    big = t["proc"] in B1C["aux_big"]
    ax, ay = B1C["aux_big_size"] if big else B1C["aux_size"]
    kind = B1C["aux_kind"].get(t["proc"], B1C["aux_kind_default"])
    add(t["id"].replace("-1F-", "-B1-AUX-"), "aux", "B1", t["x"] + (t["dx"] - ax) / 2, t["y"] + (t["dy"] - ay) / 2, zB,
        ax, ay, B1C["aux_h"], name=f"{kind} ← {t['id']}", parent=t["id"], proc=t["proc"], fab=t["fab"], bay=t["bay"])
add("FAB1-B1-TRUNK", "utility", "B1", spx0, sp0, LV["1F"] - P["slab"]["1F"] - B1C["trunk_below_1F"], spx1 - spx0, sp1 - sp0, B1C["trunk_h"],
    name="主管廊（PCW/UPW/CDA/N2/排气/电缆桥架）", zone="utility")
for rid, x, y, dx, dy, nm in B1C["rooms"]:
    add(f"FAB1-B1-{rid}", "room", "B1", x, y, zB, dx, dy, B1C["room_h"], name=nm, zone="utility")

# ---------------- 2F 回风夹层 / FFU ----------------
F2 = C["f2"]
z2 = LV["2F"]
ffu_total = 0
for o in list(objs):
    if o["cat"] == "zone" and o["level"] == "1F" and o["id"].startswith("FAB1-1F-BAY-"):
        cov = F2["ffu_cov"].get(o["iso"], F2["ffu_cov_default"])
        n = int(o["dx"] * o["dy"] / 1e6 * cov / F2["ffu_unit_m2"])
        ffu_total += n
        add(o["id"].replace("-1F-BAY-", "-2F-FFU-"), "ffu", "2F", o["x"], o["y"], z2, o["dx"], o["dy"], F2["ffu_h"],
            name=f"FFU 区 {o['id'][-3:]}（覆盖率 {int(cov*100)}%，约 {n} 台）", ffu_count=n, coverage=cov, parent=o["id"])
for o in list(objs):
    if o["cat"] == "zone" and o["id"].startswith("FAB1-1F-CHS-"):
        add(o["id"].replace("-1F-CHS-", "-2F-DCC-"), "dcc", "2F", o["x"], o["y"], z2, o["dx"], o["dy"], F2["dcc_h"],
            name=f"干盘管 DCC/回风 {o['id'][-3:]}", parent=o["id"])
EX = F2["exh"]
add("FAB1-2F-EXH", "utility", "2F", spx0, sp0 + EX["y_off"], z2 + EX["z_off"], spx1 - spx0, EX["dy"], EX["dz"], name="工艺排气总管（酸/碱/VOC/一般）", zone="utility")

# ---------------- RF 屋顶机电 ----------------
R = C["rf"]
zR = LV["RF"]
xs_rf = [x for x in range(R["x_start"], R["x_end"], R["x_step"]) if not (R["skip"][0] < x < R["skip"][1])]
i = 0
for yy in R["mau_rows"]:
    for x in xs_rf:
        i += 1
        add(f"FAB1-RF-MAU-{i:02d}", "rf_equip", "RF", x, yy, zR, *R["mau_size"], name=f"MAU 外气空调箱 {i:02d}", kind="MAU")
j = 0
for yy in R["ahu_rows"]:
    for x in xs_rf:
        j += 1
        add(f"FAB1-RF-AHU-{j:02d}", "rf_equip", "RF", x, yy, zR, *R["ahu_size"], name=f"AHU 空调箱 {j:02d}", kind="AHU")
for k, (x, kind) in enumerate(R["scrubbers"]):
    add(f"FAB1-RF-SCR-{k+1:02d}", "rf_equip", "RF", x, R["scr_y"], zR, *R["scr_size"], name=f"{kind}洗涤塔 {k+1:02d}", kind="SCRUBBER")
    add(f"FAB1-RF-STK-{k+1:02d}", "stack", "RF", x + R["stack_dx"], R["stack_y"], zR, *R["stack_size"], name=f"{kind}排气烟囱 {k+1:02d}", kind="STACK")

# ---------------- 外部附属 ----------------
for oid, lv, x, y, z, dx, dy, dz, nm, st in C.get("ext", []):
    add(oid, "ext", lv, x, y, z, dx, dy, dz, name=nm, status=st)

# ---------------- 统计 ----------------
cnt = {}
for t in tools:
    cnt[t["proc"]] = cnt.get(t["proc"], 0) + 1
stats = {
    "floor_area_each_m2": L * W / 1e6,
    "gfa_4_levels_m2": 4 * L * W / 1e6,
    "cleanroom_bays_m2": round(sum(o["dx"] * o["dy"] for o in objs if o["id"].startswith("FAB1-1F-BAY-")) / 1e6),
    "interbay_m2": round((spx1 - spx0) * spw / 1e6),
    "chase_m2": round(sum(o["dx"] * o["dy"] for o in objs if o["id"].startswith("FAB1-1F-CHS-")) / 1e6),
    "tool_slots_1F": len(tools), "tool_slots_by_proc": cnt,
    "aux_B1": sum(1 for o in objs if o["cat"] == "aux"),
    "ffu_est": ffu_total, "object_count": len(objs),
    "rf_equip": {k: sum(1 for o in objs if o.get("kind") == k) for k in ("AHU", "MAU", "SCRUBBER", "STACK")},
}
P["stats"] = stats
P["decisions"] = [s.format(**stats) for s in P["decisions"]]
P["proc"] = {k: {"name": v["name"], "env": v["env"], "pitch": v["pitch"], "iso": v["iso"]} for k, v in PROC.items()}
json.dump({"params": P, "objects": objs, "oht": oht}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
print(json.dumps(stats, ensure_ascii=False, indent=1))
