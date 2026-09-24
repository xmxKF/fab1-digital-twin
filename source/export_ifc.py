# 普通 Python（pip install ifcopenshell numpy）：由 layout.json 生成 IFC4
import os, json
ROOT = os.environ.get("FAB1_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
lay = json.load(open(os.path.join(ROOT, "source", "layout.json"), encoding="utf-8"))
import plant_config
META = plant_config.load()["meta"]
rep = {}
# IFC4 导出（ifcopenshell.api，按楼层 IfcBuildingStorey 组织，属性集 Pset_FAB1_DT 携带 AssetId）
try:
    import ifcopenshell, ifcopenshell.api as api, ifcopenshell.guid
    f = api.run("project.create_file", version="IFC4")
    prj = api.run("root.create_entity", f, ifc_class="IfcProject", name=META["short_name"] + " " + lay["params"]["revision"])
    api.run("unit.assign_unit", f, length={"is_metric": True, "raw": "MILLIMETERS"})
    ctx = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name=META["site_name"])
    bld = api.run("root.create_entity", f, ifc_class="IfcBuilding", name=META["building_name"])
    api.run("aggregate.assign_object", f, relating_object=prj, products=[site])
    api.run("aggregate.assign_object", f, relating_object=site, products=[bld])
    storeys = {}
    for lvname, z in lay["params"]["levels"].items():
        st = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=lvname)
        st.Elevation = float(z)
        api.run("aggregate.assign_object", f, relating_object=bld, products=[st])
        storeys[lvname] = st
    CLS = {"slab": "IfcSlab", "wall": "IfcWall", "column": "IfcColumn", "tool": "IfcBuildingElementProxy", "aux": "IfcBuildingElementProxy",
           "rf_equip": "IfcBuildingElementProxy", "stack": "IfcChimney", "stocker": "IfcBuildingElementProxy", "vertical": "IfcSpace",
           "room": "IfcSpace", "zone": "IfcSpace", "utility": "IfcBuildingElementProxy", "ext": "IfcBuildingElementProxy",
           "ffu": "IfcBuildingElementProxy", "dcc": "IfcBuildingElementProxy"}
    import numpy as np
    n = 0
    for d in lay["objects"]:
        cls = CLS.get(d["cat"], "IfcBuildingElementProxy")
        e = api.run("root.create_entity", f, ifc_class=cls, name=d["id"])
        e.Description = d.get("name", "")
        m = np.eye(4); m[0][3], m[1][3], m[2][3] = d["x"], d["y"], d["z"]
        api.run("geometry.edit_object_placement", f, product=e, matrix=m, is_si=False)
        prof = f.createIfcRectangleProfileDef("AREA", None, f.createIfcAxis2Placement2D(f.createIfcCartesianPoint((d["dx"] / 2, d["dy"] / 2))), float(d["dx"]), float(d["dy"]))
        solid = f.createIfcExtrudedAreaSolid(prof, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))), f.createIfcDirection((0.0, 0.0, 1.0)), float(d["dz"]))
        rep_ = f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
        api.run("geometry.assign_representation", f, product=e, representation=rep_)
        st = storeys["1F" if d["level"] not in storeys else d["level"]]
        if cls == "IfcSpace":
            api.run("aggregate.assign_object", f, relating_object=st, products=[e])
        else:
            api.run("spatial.assign_container", f, relating_structure=st, products=[e])
        ps = api.run("pset.add_pset", f, product=e, name="Pset_FAB1_DT")
        api.run("pset.edit_pset", f, pset=ps, properties={k: str(v) for k, v in d.items() if k in ("id", "cat", "proc", "bay", "parent", "iso", "status", "name")})
        n += 1
    p = os.path.join(ROOT, "out", "FAB1_V2_四层方案.ifc")
    f.write(p)
    g = ifcopenshell.open(p)
    rep["ifc_schema"] = g.schema; rep["ifc_elements_written"] = n
    rep["ifc_storeys"] = [s.Name for s in g.by_type("IfcBuildingStorey")]
    rep["ifc_products"] = len(g.by_type("IfcProduct"))
except Exception as e:
    import traceback
    rep["ifc_error"] = traceback.format_exc()[-800:]
json.dump(rep, open(os.path.join(ROOT, "out", "IFC_QA.json"), "w"), ensure_ascii=False, indent=1)
print(rep)
