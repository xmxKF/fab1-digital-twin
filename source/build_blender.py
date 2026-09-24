"""Blender 4.x（bpy）：由 layout.json + FreeCAD 求值几何生成展示/孪生模型
  blender -b -P build_blender.py -- <ROOT> [--render]
输出：out/FAB1_V2_Twin.blend、web/assets/fab1_v2.glb、render/*.png
坐标：mm→m；Blender Z 向上（glTF 导出自动转 Y 向上）。对象名 = AssetId；自定义属性写入 glTF extras。
与 Blender MCP 的关系：本脚本即 MCP 会调用的 bpy 代码，可在本机 Blender 的 MCP 会话中逐段执行。
"""
import bpy, bmesh, json, os, sys, math
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = argv[0] if argv else os.environ.get("FAB1_ROOT", ".")
DO_RENDER = "--render" in argv
lay = json.load(open(os.path.join(ROOT, "source", "layout.json"), encoding="utf-8"))
ev = {e["id"]: e for e in json.load(open(os.path.join(ROOT, "source", "evaluated_geometry.json")))}
P = lay["params"]; LV = P["levels"]
S = 0.001
sys.path.insert(0, os.path.join(ROOT, "source"))
import plant_config
_CFG = plant_config.load(); BC = _CFG["blender"]
LIT_MAIN = _CFG["proc"].get("LIT", {}).get("main_len", 0) * S
LM, WM = P["L"] * S, P["W"] * S          # 外包长宽（m）
ZB, ZTOP = LV["B1"] * S, LV["RF"] * S     # 立面底/屋面标高（m）

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"


# ---------- 材质 ----------
def mat(name, rgb, rough=0.5, metal=0.0, alpha=1.0, emit=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    try:
        m.use_nodes = True  # Blender 5.x 起始终使用节点，该属性已弃用
    except Exception:
        pass
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if alpha < 1:
        b.inputs["Alpha"].default_value = alpha
        if hasattr(m, "surface_render_method"):
            m.surface_render_method = "BLENDED"
        else:
            m.blend_method = "BLEND"
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1); b.inputs["Emission Strength"].default_value = 1.5
    m.diffuse_color = (*rgb, alpha)
    return m


def hexrgb(h):
    h = h.lstrip("#"); c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x ** 2.2 for x in c)  # sRGB→linear


PROC_HEX = {"LIT": "#F4C542", "ETC": "#E56B5D", "CVD": "#6FA8E8", "ALD": "#5B7FD6", "PVD": "#8B72D1", "DIF": "#EE9A4D",
            "IMP": "#D467A8", "CMP": "#63C08A", "WET": "#4FC3CF", "MET": "#A9CF52"}
M = {
    "slab": mat("M_slab", hexrgb("#B9BDC1"), 0.8), "wall": mat("M_facade", hexrgb("#E4E7EA"), 0.45, 0.2),
    "column": mat("M_concrete", hexrgb("#9EA3A8"), 0.9), "tool_body": mat("M_tool_white", hexrgb("#EEF0F2"), 0.35),
    "aux": mat("M_aux", hexrgb("#6E8FB8"), 0.4, 0.3), "ffu": mat("M_ffu", hexrgb("#BCD3F5"), 0.4, 0, 0.85),
    "dcc": mat("M_dcc", hexrgb("#8CCBCB"), 0.4, 0.3), "rf_equip": mat("M_rf", hexrgb("#D4D7DB"), 0.4, 0.4),
    "stack": mat("M_stack", hexrgb("#A7ABB0"), 0.3, 0.8), "vertical": mat("M_vert", hexrgb("#A6D69A"), 0.6),
    "room": mat("M_room", hexrgb("#C9BEEA"), 0.6), "utility": mat("M_util", hexrgb("#E7A45C"), 0.4, 0.6),
    "stocker": mat("M_stk", hexrgb("#F29A38"), 0.4, 0.2), "ext": mat("M_glass", hexrgb("#7FB2DE"), 0.05, 0.1, 0.55),
    "oht": mat("M_oht", hexrgb("#F0A020"), 0.3, 0.7), "ground": mat("M_ground", hexrgb("#6E7A63"), 1.0),
    "road": mat("M_road", hexrgb("#55585C"), 0.9), "accent": mat("M_accent", hexrgb("#2F6FB3"), 0.3, 0.4),
    "floor_cr": mat("M_floor_cr", hexrgb("#FFF1C4"), 0.5), "floor_chase": mat("M_floor_chase", hexrgb("#D5D5D5"), 0.7),
    "floor_sup": mat("M_floor_sup", hexrgb("#DCD3F2"), 0.7), "floor_core": mat("M_floor_core", hexrgb("#CDE8C6"), 0.7),
    "floor_ib": mat("M_floor_ib", hexrgb("#F7DE9A"), 0.6), "screen": mat("M_screen", (0.02, 0.05, 0.1), 0.2, 0, 1, (0.1, 0.5, 1.0)),
}
MP = {k: mat(f"M_proc_{k}", hexrgb(v), 0.35, 0.1) for k, v in PROC_HEX.items()}


# ---------- 几何工具 ----------
def box_bm(bm, x, y, z, dx, dy, dz):
    v = [bm.verts.new((x + a * dx, y + b * dy, z + c * dz)) for c in (0, 1) for b in (0, 1) for a in (0, 1)]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([v[i] for i in f])


def mesh_from_boxes(name, boxes, mats=None):
    """boxes: [(x,y,z,dx,dy,dz,mat_index)] in metres"""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for b in boxes:
        n0 = len(bm.faces)
        box_bm(bm, *b[:6])
        bm.faces.ensure_lookup_table()
        for f in bm.faces[n0:]:
            f.material_index = b[6] if len(b) > 6 else 0
    bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in (mats or []):
        me.materials.append(m)
    return me


cols = {}


def coll(name, parent=None):
    if name in cols:
        return cols[name]
    c = bpy.data.collections.new(name)
    (parent or scene.collection).children.link(c)
    cols[name] = c
    return c


level_empty = {}


def lvl(level):
    if level not in level_empty:
        e = bpy.data.objects.new(f"LEVEL_{level}", None)
        coll("FAB1").objects.link(e)
        e["level"] = level
        level_empty[level] = e
    return level_empty[level]


def obj(name, me, level, props=None, collname=None):
    o = bpy.data.objects.new(name, me)
    coll(collname or f"{level}", coll("FAB1")).objects.link(o)
    o.parent = lvl(level)
    for k, v in (props or {}).items():
        if v not in (None, ""):
            o[k] = v
    return o


G = lambda d: ev[d["id"]]
OBJ = lay["objects"]

# ---------- 静态合并几何（按层 × 类别） ----------
static = {}
for d in OBJ:
    e = G(d)
    x, y, z = e["xmin"] * S, e["ymin"] * S, e["zmin"] * S
    dx, dy, dz = (e["xmax"] - e["xmin"]) * S, (e["ymax"] - e["ymin"]) * S, (e["zmax"] - e["zmin"]) * S
    lv = "EXT" if d["cat"] == "ext" else d["level"]
    if d["cat"] in ("slab", "wall", "column", "vertical", "room", "utility", "dcc", "ffu"):
        key = (lv, d["cat"] if not (d["cat"] == "wall" and d.get("face")) else ("curtain_" if d.get("kind") == "curtain" else "facade_") + d["face"])
        h = dz
        if d["cat"] in ("room", "vertical"):
            h = min(dz, 4.0)  # 房间以 4 m 高体块示意，避免遮挡
        if d["cat"] == "ffu":
            z = LV["2F"] * S - P["slab"]["2F"] * S - 0.75; h = 0.7  # FFU 实际挂在 1F 顶棚
        static.setdefault(key, []).append((x, y, z, dx, dy, h))
    elif d["cat"] == "zone":
        mk = {"cleanroom": 0, "chase": 1, "support": 2, "core": 3, "interbay": 4}[d.get("zone", "cleanroom")]
        static.setdefault((lv, "floorzone"), []).append((x, y, z + 0.005 * (1 + mk), dx, dy, 0.02, mk))
zmats = [M["floor_cr"], M["floor_chase"], M["floor_sup"], M["floor_core"], M["floor_ib"]]
for (lv, cat), boxes in static.items():
    if cat == "floorzone":
        me = mesh_from_boxes(f"ME_{lv}_{cat}", boxes, zmats)
    else:
        mm = M["wall"] if cat.startswith("facade") else M["ext"] if cat.startswith("curtain") else M.get(cat, M["slab"])
        if lv == "FDN":
            mm = M["column"]
        me = mesh_from_boxes(f"ME_{lv}_{cat}", [b + (0,) for b in boxes], [mm])
    obj(f"STATIC_{lv}_{cat}", me, "1F" if lv == "EXT" else lv, {"category": cat, "static": 1, "level": lv})

# 外立面细部：蓝色竖向装饰带 + 北/南立面横向分隔线
acc = []
cx0, cx1 = P["core"][0] * S, P["core"][1] * S
acc_h = ZTOP + P["parapet"] * S - ZB  # 立面底到女儿墙顶
for x in sorted(BC["accent_x"] + [cx0 - 2.4, cx1 + 1.2]):  # 两座体块各自收边（Twin-Fab）
    acc.append((x, -0.25, ZB, 1.2, 0.25, acc_h))
for zz in (0.0, LV["1F"] * S, LV["2F"] * S):
    for a, b in ((0, cx0), (cx1, LM)):
        acc.append((a, -0.12, zz, b - a, 0.12, 0.35)); acc.append((a, WM, zz, b - a, 0.12, 0.35))
obj("STATIC_facade_accent", mesh_from_boxes("ME_accent", [a + (0,) for a in acc], [M["accent"]]), "1F", {"static": 1})
# 连接段幕墙竖梃（1.5 m 间距），按立面分对象，剖切时随幕墙一起隐藏
for face, yy in (("S", -0.1), ("N", WM)):
    mul = [(x, yy, ZB, 0.12, 0.1, ZTOP - ZB, 0) for x in [cx0 + 1.5 * k for k in range(1, int((cx1 - cx0) / 1.5))]]
    obj(f"STATIC_mullion_curtain_{face}", mesh_from_boxes(f"ME_mullion_{face}", mul, [M["accent"]]), "1F", {"static": 1})

# ---------- 工艺设备（共享网格，按外包尺寸） ----------
mesh_cache = {}


def tool_mesh(proc, dx, dy, dz, face):
    key = (proc, round(dx, 3), round(dy, 3), round(dz, 3), face)
    if key in mesh_cache:
        return mesh_cache[key]
    b = [(0, 0, 0, dx, dy, dz * 0.82, 0),                               # 主体
         (dx * 0.08, dy * 0.08, dz * 0.82, dx * 0.84, dy * 0.84, dz * 0.18, 1)]  # 顶部工艺色模块
    lp_x = dx - 0.02 if face == "E" else -0.33
    for k in range(2 if dy < 6 else 3):                                   # 朝通道的装载端口
        b.append((lp_x, dy * (0.18 + 0.28 * k), 0.85, 0.35, 0.5, 0.35, 1))
    b.append(((dx - 0.03) if face == "E" else -0.02, dy * 0.75, 1.3, 0.05, 0.45, 0.35, 2))  # 屏幕
    if proc == "LIT":  # 扫描机主体与涂胶显影分色
        ml = LIT_MAIN if LIT_MAIN else dy * 0.64  # 扫描机主体长度（参数文件），其余为涂胶显影
        b = [(0, 0, 0, dx, ml, dz, 0), (0.1, ml + 0.1, 0, dx - 0.2, dy - ml - 0.2, dz * 0.75, 1), (0.2, 0.3, dz, dx - 0.4, 2.0, 0.25, 1),
             ((dx - 0.03) if face == "E" else -0.02, 6.5, 1.3, 0.05, 0.45, 0.35, 2)]
    me = mesh_from_boxes(f"ME_tool_{proc}_{len(mesh_cache)}", b, [M["tool_body"], MP[proc], M["screen"]])
    mesh_cache[key] = me
    return me


for d in OBJ:
    e = G(d)
    x, y, z = e["xmin"] * S, e["ymin"] * S, e["zmin"] * S
    dx, dy, dz = (e["xmax"] - e["xmin"]) * S, (e["ymax"] - e["ymin"]) * S, (e["zmax"] - e["zmin"]) * S
    props = {k: d.get(k) for k in ("id", "name", "cat", "proc", "bay", "fab", "parent", "iso", "status", "level")}
    props = {("asset_" + k if k in ("id",) else k): v for k, v in props.items()}
    if d["cat"] == "tool":
        o = obj(d["id"], tool_mesh(d["proc"], dx, dy, dz, d.get("face", "E")), "1F", props, "1F_tools")
        o.location = (x, y, z)
    elif d["cat"] == "aux":
        key = ("aux", round(dx, 3), round(dy, 3), round(dz, 3), d["proc"])
        if key not in mesh_cache:
            mesh_cache[key] = mesh_from_boxes(f"ME_aux_{len(mesh_cache)}", [(0, 0, 0, dx, dy, dz, 0), (0.1, 0.1, dz, dx - 0.2, 0.3, 0.2, 1),
                                                                            (dx / 2 - 0.15, dy / 2 - 0.15, dz, 0.3, 0.3, (LV["1F"] - LV["B1"]) * S - 0.4 - dz - 0.1, 2)],
                                              [M["aux"], MP[d["proc"]], M["utility"]])  # 竖向 hookup 管束
        o = obj(d["id"], mesh_cache[key], "B1", props, "B1_aux"); o.location = (x, y, z)
    elif d["cat"] in ("stocker",):
        me = mesh_from_boxes(f"ME_{d['id']}", [(0, 0, 0, dx, dy, dz, 0), (0.2, -0.05, 0.8, dx - 0.4, 0.06, dz - 1.6, 1)], [M["stocker"], M["ext"]])
        o = obj(d["id"], me, "1F", props, "1F_amhs"); o.location = (x, y, z)
    elif d["cat"] == "rf_equip":
        kind = d.get("kind")
        if kind == "CT":
            b = [(0, 0, 0, dx, dy, dz * 0.8, 0), (dx * 0.1, dy * 0.1, dz * 0.8, dx * 0.8, dy * 0.8, dz * 0.2, 1)]
        elif kind == "SCRUBBER":
            b = [(0, 0, 0, dx, dy, dz * 0.6, 0), (dx * 0.25, dy * 0.2, dz * 0.6, dx * 0.5, dy * 0.6, dz * 0.4, 0)]
        else:
            b = [(0, 0, 0, dx, dy, dz, 0), (0.3, -0.05, 0.4, 1.2, 0.05, dz - 0.8, 1), (dx - 1.5, -0.05, 0.4, 1.2, 0.05, dz - 0.8, 1)]
        key = ("rf", kind, round(dx, 2), round(dy, 2))
        if key not in mesh_cache:
            mesh_cache[key] = mesh_from_boxes(f"ME_rf_{len(mesh_cache)}", b, [M["rf_equip"], M["column"]])
        o = obj(d["id"], mesh_cache[key], "RF", props, "RF_equip"); o.location = (x, y, z)
        if kind == "CT":
            bpy.ops.mesh.primitive_cylinder_add(radius=dx * 0.36, depth=1.2, location=(x + dx / 2, y + dy / 2, z + dz + 0.4))
            c = bpy.context.active_object; c.name = d["id"] + "_fan"; c.data.materials.append(M["column"])
            for cl in c.users_collection:
                cl.objects.unlink(c)
            coll("RF_equip").objects.link(c); c.parent = lvl("RF")
    elif d["cat"] == "stack":
        bpy.ops.mesh.primitive_cylinder_add(radius=dx / 2, depth=dz, vertices=24, location=(x + dx / 2, y + dy / 2, z + dz / 2))
        c = bpy.context.active_object; c.name = d["id"]; c.data.materials.append(M["stack"])
        for cl in c.users_collection:
            cl.objects.unlink(c)
        coll("RF_equip").objects.link(c); c.parent = lvl("RF")
        for k, v in props.items():
            if v:
                c[k] = v
    elif d["cat"] == "ext":
        b = [(0, 0, 0, dx, dy, dz, 0)]
        me = mesh_from_boxes(f"ME_{d['id']}", b, [M["ext"]])
        o = obj(d["id"], me, "EXT", props, "EXT"); o.location = (x, y, z)

# ---------- OHT 轨道（管状网格） ----------
zo = (LV["1F"] + _CFG["oht"]["height"]) * S
for r in lay["oht"]:
    pts = [(p[0] * S, p[1] * S, zo) for p in r["pts"]]
    cu = bpy.data.curves.new(r["id"], "CURVE"); cu.dimensions = "3D"
    sp = cu.splines.new("POLY"); sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1)
    sp.use_cyclic_u = bool(r.get("loop"))
    cu.bevel_depth = 0.09 if r["id"] == "OHT-MAIN" else 0.06; cu.bevel_resolution = 1
    o = bpy.data.objects.new(r["id"], cu); coll("1F_amhs").objects.link(o)
    o.data.materials.append(M["oht"])
# 转网格并合并
bpy.ops.object.select_all(action="DESELECT")
ohts = [o for o in coll("1F_amhs").objects if o.type == "CURVE"]
for o in ohts:
    o.select_set(True)
bpy.context.view_layer.objects.active = ohts[0]
bpy.ops.object.convert(target="MESH")
bpy.ops.object.join()
oht = bpy.context.active_object; oht.name = "OHT_TRACK"; oht.parent = lvl("1F"); oht["category"] = "oht"

# ---------- 场地 ----------
ground = mesh_from_boxes("ME_ground", [(-120, -80, -0.3, LM + 240, WM + 160, 0.3, 0), (-60, -25, -0.02, LM + 120, 12, 0.03, 1), (-60, WM + 15, -0.02, LM + 120, 12, 0.03, 1),
                                        (-60, -25, -0.02, 12, WM + 52, 0.03, 1), (LM + 48, -25, -0.02, 12, WM + 52, 0.03, 1)], [M["ground"], M["road"]])
g = bpy.data.objects.new("SITE_ground", ground); coll("SITE").objects.link(g)
# 建筑标识
SG = BC["sign"]
bpy.ops.object.text_add(location=(-0.5, SG["y"], SG["z"]), rotation=(math.pi / 2, 0, -math.pi / 2))
t = bpy.context.active_object; t.data.body = SG["text"]; t.data.size = SG["size"]; t.data.extrude = 0.15
t.data.materials.append(M["accent"]); t.name = "SIGN_FAB1"
bpy.ops.object.convert(target="MESH")
for cl in t.users_collection:
    cl.objects.unlink(t)
coll("EXT").objects.link(t); t.parent = lvl("EXT")

# ---------- 保存 / 导出 ----------
os.makedirs(os.path.join(ROOT, "out"), exist_ok=True); os.makedirs(os.path.join(ROOT, "web", "assets"), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "out", "FAB1_V2_Twin.blend"))
glb = os.path.join(ROOT, "web", "assets", "fab1_v2.glb")
bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", export_extras=True, export_apply=True, use_visible=False,
                          export_yup=True, export_cameras=False, export_lights=False)
stats = {"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes), "tools": len(coll("1F_tools").objects),
         "aux": len(coll("B1_aux").objects), "glb_bytes": os.path.getsize(glb)}
print("BLENDER_STATS", json.dumps(stats))
json.dump(stats, open(os.path.join(ROOT, "out", "Blender_QA.json"), "w"), indent=1)

# ---------- 渲染 ----------
if DO_RENDER:
    rd = os.path.join(ROOT, "render"); os.makedirs(rd, exist_ok=True)
    scene.render.engine = "CYCLES"; scene.cycles.device = "CPU"; scene.cycles.samples = 48
    try:
        scene.cycles.use_denoising = False
    except Exception:
        pass
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    scene.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in scene.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    w = bpy.data.worlds.new("W"); scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    if bg is None:
        bg = nt.nodes.new("ShaderNodeBackground"); wo = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
        nt.links.new(bg.outputs[0], wo.inputs[0])
    bg.inputs[0].default_value = (0.78, 0.84, 0.92, 1); bg.inputs[1].default_value = 0.9
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN")); scene.collection.objects.link(sun)
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(-35)); sun.data.angle = math.radians(3)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam")); scene.collection.objects.link(cam); scene.camera = cam
    cam.data.lens = 35; cam.data.clip_end = 3000

    def look(loc, tgt):
        cam.location = loc
        cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()

    def hide(names_pred, flag):
        for o in bpy.data.objects:
            if names_pred(o):
                o.hide_render = flag

    # 1) 外观（西南鸟瞰，类设计图视角）
    CAM = BC["cameras"]
    look(*CAM["ext"]); scene.render.filepath = os.path.join(rd, "01_外观_西南鸟瞰.png"); bpy.ops.render.render(write_still=True)
    # 2) 剖切：隐藏南立面、屋面板、2F 楼板及屋面设备的东半侧 → 类设计图右半剖视
    cut = lambda o: (o.name.startswith("STATIC_") and any(k in o.name for k in ("facade_S", "facade_E", "curtain_S")) or o.name in ("STATIC_RF_slab", "STATIC_RF_wall"))
    hide(cut, True)
    look(*CAM["cut"]); scene.render.filepath = os.path.join(rd, "02_剖切_四层.png"); bpy.ops.render.render(write_still=True)
    # 3) 1F 洁净室俯视（隐藏 2F 以上）
    hide(lambda o: o.parent and o.parent.name in ("LEVEL_2F", "LEVEL_RF"), True)
    hide(lambda o: o.name.startswith("STATIC_2F") or o.name.startswith("STATIC_RF") or o.name == "STATIC_facade_accent" or o.name.startswith("STATIC_mullion") or o.name == "SIGN_FAB1", True)
    look(*CAM["top"]); scene.render.filepath = os.path.join(rd, "03_1F_洁净室_光刻区.png"); bpy.ops.render.render(write_still=True)
    print("RENDERED")
