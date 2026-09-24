#!/usr/bin/env bash
# 全流程：布局 → FreeCAD 原生模型 → 校验/求值几何 → IFC → DXF/PDF → Blender（.blend/GLB/渲染）→ 孪生数据
set -e
export FAB1_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FC_BIN="${FC_BIN:-freecad}"; FCCMD="${FCCMD:-freecadcmd}"; BLENDER="${BLENDER:-blender}"
python3 "$FAB1_ROOT/source/make_layout.py"
rm -f "$FAB1_ROOT/out/FAB1_V2_四层方案.FCStd"
${XVFB:-} "$FC_BIN" "$FAB1_ROOT/source/build_freecad.py"
rm -f "$FAB1_ROOT"/out/*.FCBak
"$FCCMD" "$FAB1_ROOT/source/verify_export.py"
python3 "$FAB1_ROOT/source/export_ifc.py"
python3 "$FAB1_ROOT/source/export_drawings.py"
"$BLENDER" -b -P "$FAB1_ROOT/source/build_blender.py" -- "$FAB1_ROOT" ${RENDER:-}
python3 "$FAB1_ROOT/source/build_twin_data.py"
