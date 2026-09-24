# 厂房数字孪生：参数化建模 + 生产流动仿真

用一份参数文件驱动整条流程：生成厂房楼层布局，再输出 FreeCAD 原生模型、IFC4、分层 DXF / A1 PDF 图纸和 Blender 模型，最后得到一个浏览器可用的数字孪生网页（Three.js + 离散事件仿真）。

> 本仓库只含代码与**虚构的示例参数**。在线演示页面中的尺寸、布局、设备数量均为虚构，不代表任何真实厂区。

在线演示：https://xmxkf.github.io/fab1-digital-twin/

## 网页功能

- 楼层切换、剖切、俯视、局部放大视角、楼层展开
- 点选设备：资产 ID、Bay、洁净等级、实时状态、当前 lot、队列与负荷、下层配套设备关联
- 离散事件仿真：简化再入路线、就近 / 最短队列派工、随机故障（MTBF/MTTR）、搬送动画；开页前预热至稳态
- 场景：调节投片速率、单机故障、设备组批量停机；KPI 为滚动 30 天出片、WIP、周期时间、可用率、设备组负荷
- 着色模式：设备状态 / 洁净度 / 温度（均为模拟数据）

## 目录

| 路径 | 内容 |
|---|---|
| `Web孪生/` | 网页（`index_local.html` 离线版，three.js 0.160 已放在 `vendor/`；`index.html` 走 CDN） |
| `Web孪生/assets-demo/` | 示例参数生成的模型与数据 |
| `source/config/plant.example.json` | 示例参数（结构说明见文件内各字段） |
| `source/*.py` | 建模与导出流程 |

## 本机运行网页

需要 Python。双击 `Web孪生/启动孪生.cmd`，或在 `Web孪生/` 下执行：

```bash
python -m http.server 8765
# 浏览器打开 http://localhost:8765/index_local.html
```

网页优先读取 `Web孪生/assets/`（本机自有数据，不入库），没有时回退到 `assets-demo/`。

## 用自己的参数重建

1. 复制 `source/config/plant.example.json` 为 `source/config/plant.json`，改成自己的参数。该文件已被 `.gitignore` 排除，不会提交。也可用环境变量 `FAB1_CONFIG` 指定任意路径。
2. 安装依赖：FreeCAD 1.x、Blender 4.x / 5.x，以及 `pip install ezdxf matplotlib ifcopenshell numpy`。
3. 运行流程（Linux / WSL 示例；Windows 可逐条执行）：

```bash
FC_BIN=freecad FCCMD=freecadcmd BLENDER=blender RENDER=--render source/run_all.sh
```

顺序：布局 → FreeCAD 原生模型 → 重开校验并导出求值几何 → IFC → DXF/PDF → Blender（.blend / GLB / 渲染）→ 孪生数据。输出在 `out/`、`web/assets/`、`render/`。把 `web/assets/` 下的文件复制到 `Web孪生/assets/`，网页就会改用你的数据。

## 数据与 ID

所有对象带稳定的 AssetId。FCStd（属性组 `DigitalTwin`）、IFC4（`Pset_FAB1_DT`）、DXF（XDATA `FAB1_DT`）、GLB（节点名）使用同一套 ID；上层工艺设备与下层配套设备之间用 `ParentAssetId` 关联。

## 仿真边界

工序时间按基准投片速率下各设备组的目标负荷反推，只用于演示流动、瓶颈与场景对比，不代表真实工艺节拍或产能结论。未接入任何生产系统。
