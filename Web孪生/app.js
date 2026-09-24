// 数字孪生：GLB 模型（Blender 导出，节点名 = AssetId）+ 离散事件生产流动模拟（模拟数据）
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 0) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

// 真实模型只在本机 assets/（不入库）；公开站点回退到 assets-demo/（虚构示例数据）
async function pickAssets() { for (const b of ["assets/", "assets-demo/"]) { try { const r = await fetch(b + "twin-data.json"); if (r.ok) return [b, await r.json()]; } catch (e) {} } throw new Error("找不到孪生数据"); }
const [ASSET, data] = await pickAssets();
const M_ = data.meta;
document.title = M_.title; $("h-title").firstChild.textContent = M_.title; $("h-sub").textContent = M_.subtitle; $("h-tag").textContent = M_.tag;
$("k-wpm-label").textContent = `出片折合 WPM（目标 ${Number(M_.rate.base).toLocaleString("en-US")}）`;
Object.assign($("rate"), { min: M_.rate.min, max: M_.rate.max, step: M_.rate.step, value: M_.rate.base });
$("rate-v").textContent = `${Number(M_.rate.base).toLocaleString("en-US")} WPM`;
const PROC_HEX = { LIT: "#F4C542", ETC: "#E56B5D", CVD: "#6FA8E8", ALD: "#5B7FD6", PVD: "#8B72D1", DIF: "#EE9A4D", IMP: "#D467A8", CMP: "#63C08A", WET: "#4FC3CF", MET: "#A9CF52" };
const GROUPS = Object.keys(data.proc).filter((g) => data.proc[g].n > 0);

// 布局坐标 (x 东, y 北, z 上; m) → three (x, z, -y)
const W3 = (x, y, z) => new THREE.Vector3(x, z, -y);

/* ---------------- 三维场景 ---------------- */
const stage = $("stage");
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
stage.prepend(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(40, 1, 0.5, 4000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.maxPolarAngle = Math.PI * 0.495;
scene.add(new THREE.HemisphereLight(0xffffff, 0x8a9690, 1.7));
const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(-200, 300, 250); scene.add(sun);

function resize() {
  const r = stage.getBoundingClientRect();
  renderer.setSize(r.width, r.height, false); camera.aspect = r.width / r.height; camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);

async function loadModel() {
  const loader = new GLTFLoader();
  try { const r = await fetch(ASSET + "fab1_v2.glb"); if (r.ok && (r.headers.get("content-type") || "").indexOf("html") < 0) return await loader.parseAsync(await r.arrayBuffer(), ""); } catch (e) {}
  const j = await (await fetch(ASSET + "fab1_v2.glb.json")).json(); // 托管环境：GLB 以 base64 JSON 发布
  const bin = Uint8Array.from(atob(j.b64), (c) => c.charCodeAt(0));
  return await loader.parseAsync(bin.buffer, "");
}
const gltf = await loadModel();
const root = gltf.scene; scene.add(root);
$("loading").hidden = true;
const LEVEL = {}; root.traverse((o) => { if (o.name.startsWith("LEVEL_")) LEVEL[o.name.slice(6)] = o; });
const byId = {}; root.traverse((o) => { const id = o.userData?.asset_id; if (id && !byId[id]) byId[id] = o; });
const staticByName = {}; root.traverse((o) => { if (o.name.startsWith("STATIC_")) staticByName[o.name] = o; });
function syncBg() { scene.background = new THREE.Color(css("--canvas") || "#DDE5E7"); }
syncBg(); matchMedia("(prefers-color-scheme: dark)").addEventListener("change", syncBg);
new MutationObserver(syncBg).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

/* 状态覆盖层：每台设备顶面一块着色板（InstancedMesh，挂在 LEVEL_1F 下以随楼层展开） */
const T = data.tools; const NT = T.length; const tIndex = Object.fromEntries(T.map((t, i) => [t.id, i]));
const lampGeo = new THREE.BoxGeometry(1, 0.25, 1);
const lamps = new THREE.InstancedMesh(lampGeo, new THREE.MeshLambertMaterial({ color: 0xffffff }), NT);
const m4 = new THREE.Matrix4();
T.forEach((t, i) => {
  m4.compose(W3(t.x, t.y, t.z + 0.2), new THREE.Quaternion(), new THREE.Vector3(t.w * 0.96, 1, t.d * 0.96));
  lamps.setMatrixAt(i, m4);
});
(LEVEL["1F"] || root).add(lamps);
/* 洁净度/温度热图：每个 Bay 一块半透明地板 */
const B = data.bays;
const bayPlates = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.1, 1), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.6, depthWrite: false }), B.length);
B.forEach((b, i) => {
  m4.compose(W3((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, data.meta.levels["1F"] / 1000 + 0.12), new THREE.Quaternion(), new THREE.Vector3(b.x1 - b.x0, 1, b.y1 - b.y0));
  bayPlates.setMatrixAt(i, m4);
});
bayPlates.visible = false; (LEVEL["1F"] || root).add(bayPlates);
/* FOUP 搬送标记 */
const MAXF = 400;
const foups = new THREE.InstancedMesh(new THREE.BoxGeometry(0.9, 0.9, 0.9), new THREE.MeshLambertMaterial({ color: css("--accent") || "#C98A00" }), MAXF);
foups.count = 0; (LEVEL["1F"] || root).add(foups);

/* ---------------- 离散事件仿真 ---------------- */
class Heap { constructor() { this.a = []; } push(e) { const a = this.a; a.push(e); let i = a.length - 1; while (i) { const p = (i - 1) >> 1; if (a[p].t <= a[i].t) break; [a[p], a[i]] = [a[i], a[p]]; i = p; } }
  pop() { const a = this.a; const top = a[0]; const last = a.pop(); if (a.length) { a[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < a.length && a[l].t < a[m].t) m = l; if (r < a.length && a[r].t < a[m].t) m = r; if (m === i) break; [a[m], a[i]] = [a[i], a[m]]; i = m; } } return top; }
  peek() { return this.a[0]; } get size() { return this.a.length; } }

const SIM = data.sim, ROUTE = data.route, PT = Object.fromEntries(GROUPS.map((g) => [g, data.proc[g].pt_h]));
let rng = mulberry(20260924);
function mulberry(a) { return () => { a |= 0; a = (a + 0x6d2b79f5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const expo = (m) => -Math.log(1 - rng()) * m;
let S;
function initSim() {
  rng = mulberry(20260924);
  S = { t: 0, ev: new Heap(), lots: new Map(), nextLot: 1, wpm: +$("rate").value, done: [], busy: {}, busyAcc: Object.fromEntries(GROUPS.map((g) => [g, 0])),
    tool: T.map((t) => ({ state: "idle", q: [], lot: null, since: 0, busyH: 0, downUntil: 0 })), moves: [], log: [] };
  S.ev.push({ t: 0, k: "rel" });
  T.forEach((t, i) => S.ev.push({ t: expo(SIM.mtbf_h), k: "fail", i }));
}
const lotInterval = () => (SIM.lot_size * 30 * 24) / S.wpm;
function pickTool(g, fromIdx) {
  let best = -1, bw = Infinity;
  for (const i of G[g]) {
    const s = S.tool[i]; if (s.state === "down") continue;
    const w = s.q.length + (s.lot ? 1 : 0) + rng() * 0.01;
    if (w < bw) { bw = w; best = i; }
  }
  return best < 0 ? G[g][Math.floor(rng() * G[g].length)] : best;
}
const G = Object.fromEntries(GROUPS.map((g) => [g, []])); T.forEach((t, i) => G[t.p].push(i));
function send(lot, from) {
  if (lot.step >= ROUTE.length) { lot.out = S.t; S.done.push({ t: S.t, ct: S.t - lot.in }); S.lots.delete(lot.id); if (S.animate && from >= 0) addMove(from, -1); return; }
  const g = ROUTE[lot.step]; const to = pickTool(g, from);
  const dt = from < 0 ? 0.05 : SIM.transfer_h * (0.7 + 0.6 * rng());
  S.ev.push({ t: S.t + dt, k: "arr", lot, i: to });
  if (S.animate && from >= 0) addMove(from, to, dt);
}
function start(i) {
  const s = S.tool[i]; if (s.state !== "idle" || !s.q.length) return;
  const lot = s.q.shift(); s.lot = lot; setState(i, "run");
  const g = T[i].p; const d = PT[g] * (0.85 + 0.3 * rng());
  S.ev.push({ t: S.t + d, k: "fin", i, lot });
}
function setState(i, st) {
  const s = S.tool[i];
  if (s.state === "run") s.busyH += S.t - s.since, S.busyAcc[T[i].p] += S.t - s.since;
  s.state = st; s.since = S.t;
}
function step(e) {
  S.t = e.t;
  if (e.k === "rel") {
    const lot = { id: S.nextLot++, step: 0, in: S.t }; S.lots.set(lot.id, lot); send(lot, -1);
    S.ev.push({ t: S.t + lotInterval() * (0.9 + 0.2 * rng()), k: "rel" });
  } else if (e.k === "arr") {
    const s = S.tool[e.i];
    if (s.state === "down") { const j = pickTool(T[e.i].p, e.i); S.tool[j].q.push(e.lot); start(j); return; }
    s.q.push(e.lot); start(e.i);
  } else if (e.k === "fin") {
    const s = S.tool[e.i]; if (s.lot !== e.lot) return; // 已因故障中断
    s.lot = null; setState(e.i, "idle"); e.lot.step++; send(e.lot, e.i); start(e.i);
  } else if (e.k === "fail") {
    down(e.i, expo(SIM.mttr_h), false);
    S.ev.push({ t: S.t + expo(SIM.mtbf_h) + SIM.mttr_h, k: "fail", i: e.i });
  } else if (e.k === "fix") {
    const s = S.tool[e.i]; if (s.state !== "down" || S.t + 1e-6 < s.downUntil) return;
    setState(e.i, "idle"); if (S.animate) log(`${T[e.i].id} 恢复`); start(e.i);
  }
}
function down(i, dur, manual) {
  const s = S.tool[i];
  if (s.state === "down") { s.downUntil = Math.max(s.downUntil, S.t + dur); S.ev.push({ t: s.downUntil, k: "fix", i }); return; }
  if (s.lot) { s.q.unshift(s.lot); s.lot = null; }
  setState(i, "down"); s.downUntil = S.t + dur;
  const q = s.q.splice(0); q.forEach((lot) => { const j = pickTool(T[i].p, i); S.tool[j].q.push(lot); start(j); });
  S.ev.push({ t: s.downUntil, k: "fix", i });
  if (S.animate || manual) log(`${T[i].id} ${manual ? "人工注入" : "随机"}停机 ${fmt(dur, 1)} h`, "down");
}
function runUntil(t) { while (S.ev.size && S.ev.peek().t <= t) step(S.ev.pop()); S.t = t; }

/* 搬送动画路径：设备 → 本 bay 通道 → 中央主通道 → 目的 bay 通道 → 设备（OHT 高度） */
const spineY = (data.meta.spine[0] + data.meta.spine[1]) / 2, zO = data.meta.oht_z;
const bayOf = Object.fromEntries(B.map((b) => [b.id, b]));
function pathPts(i) { const t = T[i], b = bayOf[t.b]; const ax = (b.x0 + b.x1) / 2; return [[t.x, t.y], [ax, t.y], [ax, spineY]]; }
function addMove(a, b, dt = SIM.transfer_h) {
  const pa = pathPts(a); const pts = b < 0 ? [...pa, [2, spineY]] : [...pa, ...pathPts(b).reverse()];
  const v = pts.map(([x, y]) => W3(x, y, zO)); const seg = []; let L = 0;
  for (let k = 1; k < v.length; k++) { const d = v[k].distanceTo(v[k - 1]); seg.push(d); L += d; }
  S.moves.push({ t0: S.t, t1: S.t + dt, v, seg, L });
}
function log(msg, cls) {
  const d = Math.floor(S.t / 24), h = S.t % 24;
  S.log.unshift(`D${d} ${String(Math.floor(h)).padStart(2, "0")}:${String(Math.floor((h % 1) * 60)).padStart(2, "0")}  ${msg}`);
  S.log.length = Math.min(S.log.length, 40);
  $("log").innerHTML = S.log.slice(0, 12).map((s) => `<div>${s}</div>`).join("");
}

/* ---------------- 视图与交互 ---------------- */
const VIEWS = M_.views;
let camAnim = null;
function goView(k) { const [p, tg] = VIEWS[k]; camAnim = { p0: camera.position.clone(), t0: controls.target.clone(), p1: new THREE.Vector3(...p), t1: new THREE.Vector3(...tg), s: performance.now() };
  setCut(k === "cut" || k === "top" || k === "litho"); if (k === "top" || k === "litho") showLevel("1F"); else if (k === "ext") showLevel("ALL"); }
camera.position.set(...VIEWS.ext[0]); controls.target.set(...VIEWS.ext[1]);
function setCut(on) {
  for (const [n, o] of Object.entries(staticByName)) {
    if (/(facade|curtain)_[SE]$/.test(n) || n === "STATIC_RF_slab" || n === "STATIC_RF_wall" || n === "STATIC_facade_accent" || n.startsWith("STATIC_mullion_")) o.visible = !on;
  }
}
let curLv = "ALL";
function showLevel(lv) {
  curLv = lv;
  for (const [k, o] of Object.entries(LEVEL)) o.visible = lv === "ALL" || k === lv || (k === "FDN" && lv === "B1") || (k === "EXT" && lv === "ALL");
  if (lv !== "ALL") setCut(true);
  document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lv === lv)));
}
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => showLevel(b.dataset.lv)));
$("v-ext").onclick = () => goView("ext"); $("v-cut").onclick = () => goView("cut"); $("v-top").onclick = () => goView("top"); $("v-litho").onclick = () => goView("litho");
const EXPL = M_.explode;
let exploded = false;
$("t-explode").onclick = (e) => { exploded = !exploded; e.target.setAttribute("aria-pressed", String(exploded)); e.target.textContent = exploded ? "楼层合拢" : "楼层展开";
  for (const [k, o] of Object.entries(LEVEL)) o.position.y = exploded ? (EXPL[k] || 0) : 0; if (exploded) setCut(true); };
let mode = "state"; $("mode").onchange = (e) => { mode = e.target.value; bayPlates.visible = mode !== "state"; lamps.visible = mode === "state"; buildLegend(); };

/* 选取 */
const ray = new THREE.Raycaster(); const ptr = new THREE.Vector2(); let sel = null; const selBox = new THREE.Box3Helper(new THREE.Box3(), 0xd2463c); selBox.visible = false; scene.add(selBox);
const linkLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), new THREE.LineBasicMaterial({ color: 0xd2463c })); linkLine.visible = false; scene.add(linkLine);
let downXY = null;
renderer.domElement.addEventListener("pointerdown", (e) => (downXY = [e.clientX, e.clientY]));
renderer.domElement.addEventListener("pointerup", (e) => {
  if (!downXY || Math.hypot(e.clientX - downXY[0], e.clientY - downXY[1]) > 5) return;
  const r = renderer.domElement.getBoundingClientRect();
  ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(ptr, camera);
  const hits = ray.intersectObjects(root.children, true).filter((h) => visibleChain(h.object));
  for (const h of hits) {
    if (h.object === lamps && h.instanceId != null) { select(T[h.instanceId].id); return; }
    let o = h.object; while (o && !o.userData?.asset_id) o = o.parent;
    if (o && o.userData.asset_id && /-(1F|B1|RF)-/.test(o.userData.asset_id)) { select(o.userData.asset_id); return; }
  }
});
function visibleChain(o) { while (o) { if (!o.visible) return false; o = o.parent; } return true; }
function select(id) { sel = id; renderInspector(); }
function renderInspector() {
  if (!sel) return;
  const o = byId[sel]; const u = o?.userData || {}; const i = tIndex[sel];
  let parentTool = null; if (u.parent && tIndex[u.parent] != null) parentTool = u.parent;
  const ti = i != null ? i : parentTool ? tIndex[parentTool] : null;
  const rows = [["资产 ID", sel], ["名称", u.name || "—"], ["楼层 / Bay", `${u.level || "—"} / ${u.bay || "—"}`]];
  if (u.iso) rows.push(["洁净等级", u.iso]);
  if (ti != null) {
    const s = S.tool[ti]; const util = (s.busyH + (s.state === "run" ? S.t - s.since : 0)) / Math.max(S.t - S.t0, 1);
    rows.push(["状态", `<span class="pill" style="background:${stateColor(s.state)}">${stateName(s.state)}</span>`]);
    rows.push(["当前 lot", s.lot ? `L${String(s.lot.id).padStart(5, "0")} · 第 ${s.lot.step + 1}/${ROUTE.length} 步` : "—"]);
    rows.push(["队列 / 负荷", `${s.q.length} lot · ${fmt(util * 100, 0)}%`]);
    const ax = data.aux[T[ti].id]; rows.push(["关联", i != null ? (ax ? ax.id : "—") : T[ti].id]);
  }
  rows.push(["数据来源", u.status || "assumption"]);
  $("insp").innerHTML = `<dl>${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  if (o) { selBox.box.setFromObject(o); selBox.visible = true; }
  if (ti != null && data.aux[T[ti].id]) {
    const t = T[ti]; const a = new THREE.Vector3(), b = new THREE.Vector3();
    (LEVEL["1F"] || root).localToWorld(a.copy(W3(t.x, t.y, t.z)));
    (LEVEL["B1"] || root).localToWorld(b.copy(W3(t.x, t.y, data.aux[t.id].z)));
    linkLine.geometry.setFromPoints([a, b]); linkLine.visible = true;
  } else linkLine.visible = false;
}
const stateName = (s) => ({ run: "加工中", idle: "待料", down: "停机" })[s];
const stateColor = (s) => ({ run: css("--run"), idle: css("--idle"), down: css("--down") })[s];

/* 场景控制 */
const SPEEDS = [[0.02, "1 秒 = 1.2 分钟"], [0.05, "1 秒 = 3 分钟"], [0.1, "1 秒 = 6 分钟"], [0.5, "1 秒 = 30 分钟"], [2, "1 秒 = 2 小时"], [8, "1 秒 = 8 小时"], [24, "1 秒 = 1 天"]];
let speed = 0.1, paused = false;
$("speed").oninput = (e) => { [speed] = SPEEDS[+e.target.value]; $("speed-v").textContent = SPEEDS[+e.target.value][1]; };
$("rate").oninput = (e) => { S.wpm = +e.target.value; $("rate-v").textContent = `${fmt(S.wpm)} WPM`; log(`投片速率调整为 ${fmt(S.wpm)} WPM`); };
$("b-pause").onclick = (e) => { paused = !paused; e.target.textContent = paused ? "继续" : "暂停"; };
$("b-fail").onclick = () => { const up = G.LIT.filter((i) => S.tool[i].state !== "down"); if (up.length) { const i = up[Math.floor(rng() * up.length)]; down(i, 12, true); select(T[i].id); } };
$("b-lit25").onclick = () => { const up = G.LIT.filter((i) => S.tool[i].state !== "down"); for (let k = 0; k < Math.round(G.LIT.length / 4) && up.length; k++) down(up.splice(Math.floor(rng() * up.length), 1)[0], 48, true); log("光刻组约 25% 停机 48 h（场景注入）", "down"); };
$("b-reset").onclick = () => boot();

/* ---------------- 仪表 ---------------- */
$("bars").innerHTML = GROUPS.map((g) => `<span class="nm" title="${data.proc[g].name}">${g}</span><div class="bar"><span id="u-${g}"></span><em style="left:${data.proc[g].u_target * 100}%"></em></div><span class="pct" id="p-${g}">—</span>`).join("");
function buildLegend() {
  const el = $("legend");
  if (mode === "state") el.innerHTML = [["run", "加工中"], ["idle", "待料"], ["down", "停机"]].map(([k, n]) => `<span><i style="background:${stateColor(k)}"></i>${n}</span>`).join("") + `<span><i style="background:${css("--accent")}"></i>FOUP 搬送</span>`;
  else if (mode === "particle") el.innerHTML = `<span><i style="background:#3FA7D6"></i>≤ ISO 4</span><span><i style="background:#7BC96F"></i>ISO 5</span><span><i style="background:#E0A21B"></i>接近上限</span><span><i style="background:#D2463C"></i>超限</span>`;
  else el.innerHTML = `<span><i style="background:#3F7FD6"></i>21.9</span><span><i style="background:#7BC96F"></i>22.0</span><span><i style="background:#E0A21B"></i>22.1</span><span><i style="background:#D2463C"></i>≥22.2</span>`;
}
buildLegend();
const col = new THREE.Color();
function paint() {
  if (mode === "state") {
    for (let i = 0; i < NT; i++) { col.set(stateColor(S.tool[i].state)); lamps.setColorAt(i, col); }
    lamps.instanceColor.needsUpdate = true;
  } else {
    const tt = S.t;
    B.forEach((b, i) => {
      const n = B.indexOf(b); const wave = Math.sin(tt * 0.21 + n * 1.7) * 0.5 + Math.sin(tt * 0.047 + n) * 0.5;
      const downs = G[b.p].filter((k) => T[k].b === b.id && S.tool[k].state === "down").length;
      let c;
      if (mode === "particle") { const lim = b.iso === "ISO 4" ? 10000 : 100000; const v = lim * (0.25 + 0.2 * wave + 0.35 * downs); b._v = v; c = v > lim ? "#D2463C" : v > lim * 0.7 ? "#E0A21B" : b.iso === "ISO 4" ? "#3FA7D6" : "#7BC96F"; }
      else { const v = 22.0 + 0.08 * wave + 0.05 * downs; b._v = v; c = v >= 22.15 ? "#D2463C" : v >= 22.05 ? "#E0A21B" : v >= 21.95 ? "#7BC96F" : "#3F7FD6"; }
      bayPlates.setColorAt(i, col.set(c));
    });
    bayPlates.instanceColor.needsUpdate = true;
  }
}
function kpis() {
  const win = 720; const recent = S.done.filter((d) => d.t > S.t - win);
  const span = Math.min(win, S.t - S.t0);
  $("k-wpm").innerHTML = span > 48 ? `${fmt((recent.length * SIM.lot_size * 720) / span)}` : "—";
  $("k-wip").innerHTML = `${fmt(S.lots.size)}<small>lot</small>`;
  $("k-ct").innerHTML = recent.length ? `${fmt(recent.reduce((a, d) => a + d.ct, 0) / recent.length / 24, 1)}<small>天</small>` : "—";
  const dn = S.tool.filter((s) => s.state === "down").length;
  $("k-av").innerHTML = `${fmt((1 - dn / NT) * 100, 1)}%<small>${dn} 台</small>`;
  const el = Math.max(S.t - S.t0, 1);
  for (const g of GROUPS) {
    let busy = 0; for (const i of G[g]) { const s = S.tool[i]; busy += s.busyH + (s.state === "run" ? S.t - s.since : 0); }
    const u = busy / (el * G[g].length);
    const span_ = $("u-" + g); span_.style.width = `${Math.min(u, 1) * 100}%`; span_.className = u > 0.92 ? "crit" : u > 0.85 ? "hot" : "";
    $("p-" + g).textContent = `${fmt(u * 100)}%`;
  }
  const d = Math.floor(S.t / 24), h = S.t % 24;
  $("clock").textContent = `D${d} ${String(Math.floor(h)).padStart(2, "0")}:${String(Math.floor((h % 1) * 60)).padStart(2, "0")}${paused ? " · 已暂停" : ""}`;
  if (sel) renderInspector();
}
function resetStats() { S.t0 = S.t; S.tool.forEach((s) => { s.busyH = 0; if (s.state === "run") s.since = S.t; }); }

/* ---------------- 启动：预热至稳态 ---------------- */
function boot() {
  initSim(); S.animate = false;
  const warm = SIM.warmup_days * 24; runUntil(warm - 720); resetStats(); runUntil(warm);
  S.animate = true; S.moves = []; S.log = [];
  log(`已预热 ${SIM.warmup_days} 天至稳态；以下为模拟事件`);
  kpis(); paint();
}
boot();
$("note").textContent = `${M_.note} 工艺路线为 ${ROUTE.length} 个简化工序步（${M_.rev}）。${M_.note_extra || ""}`;

let last = performance.now(), acc = 0;
const tmp = new THREE.Vector3();
function frame(now) {
  const dt = Math.min((now - last) / 1000, 0.1); last = now;
  if (!paused) { runUntil(S.t + dt * speed); }
  // FOUP 动画
  S.moves = S.moves.filter((m) => m.t1 > S.t);
  let n = 0;
  if (speed <= 2) for (const m of S.moves) {
    if (n >= MAXF) break; const f = Math.max(0, Math.min(1, (S.t - m.t0) / (m.t1 - m.t0))); let dist = f * m.L, k = 0;
    while (k < m.seg.length - 1 && dist > m.seg[k]) { dist -= m.seg[k]; k++; }
    tmp.copy(m.v[k]).lerp(m.v[k + 1], m.seg[k] ? Math.min(dist / m.seg[k], 1) : 0);
    m4.makeTranslation(tmp.x, tmp.y, tmp.z); foups.setMatrixAt(n++, m4);
  }
  foups.count = n; foups.instanceMatrix.needsUpdate = true;
  acc += dt; if (acc > 0.25) { acc = 0; paint(); kpis(); }
  if (camAnim) { const f = Math.min((now - camAnim.s) / 900, 1), e = f < 0.5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2;
    camera.position.lerpVectors(camAnim.p0, camAnim.p1, e); controls.target.lerpVectors(camAnim.t0, camAnim.t1, e); if (f >= 1) camAnim = null; }
  controls.update(); renderer.render(scene, camera); requestAnimationFrame(frame);
}
resize(); requestAnimationFrame(frame);
window.__twin = { S, T, select };
