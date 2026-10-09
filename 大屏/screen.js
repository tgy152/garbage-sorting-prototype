/* ==========================================================================
   智识固废：垃圾分类视觉识别与投放引导 · 数据大屏（静态演示版）

   分工：
     screen.js   数据、时间轴、四个部件小卡、ECharts 图表、顶栏时钟，
                 以及没有 WebGL 时的 2D 降级动画。这一部分不依赖 3D。
     scene3d.js  Three.js 三维拆解动画。它自己包了 try/catch，
                 挂了也不会影响上面这些面板。

   所有数字都来自本仓库产出文件，代码里不写死任何编造的数据。
   ========================================================================== */

/* ---------------------------------------------------------------- 数据区 */

// 四分类桶色，和方案书 / 答辩 PPT / 原型界面同一套
const BIN_COLOR = {
  recyclable: '#4E86BE',
  kitchen:    '#7C9440',
  hazardous:  '#C0563A',
  residual:   '#8E8B80',
};

// 28 张实拍照片经规则库逐部件判定后的分布，合计 263，
// 与批量识别报告的「识别部件总数 263」「未覆盖 0」一致
const BIN_DATA = [
  { key: 'recyclable', name: '可回收物', value: 164 },
  { key: 'residual',   name: '其他垃圾', value: 82  },
  { key: 'kitchen',    name: '厨余垃圾', value: 12  },
  { key: 'hazardous',  name: '有害垃圾', value: 5   },
];

// eval/out/waste_sorting-拆解引导-national-汇总.json
const GUIDE_METRICS = [
  ['复合物品识别准确率', 1.0],
  ['部件召回率',        1.0],
  ['类别判定准确率',    1.0],
  ['条件化提示覆盖率',  1.0],
  ['误投提示覆盖率',    1.0],
  ['地区标签一致性',    1.0],
];

// eval/out/waste_sorting-mock-汇总.json
const QA = { inScope: 15, outScope: 3, edge: 2, cite: 1.0, keyword: 0.9 };

// 每批新照片首次跑出来的覆盖率（README 第四节记录）
const ITER = [
  { label: '6 张',  value: 38.24, note: '原始规则库' },
  { label: '9 张',  value: 77.14, note: '换到大件场景又有缺口' },
  { label: '13 张', value: 100,   note: '补大件与废品规则组' },
  { label: '28 张', value: 93.92, note: '扩到社区与户外场景' },
];

// 奶茶 C01 的四个部件，原文出自 rules/waste_sorting.yaml
const PARTS = [
  {
    key: 'liquid',
    name: '剩余液体与珍珠',
    bin: 'kitchen',
    binName: '厨余垃圾 · 绿桶',
    prep: '倒进厨余桶并沥干；液体多先倒水槽',
    home: [0, 1.62, 0], split: [0, 1.35, 0], binPos: [-3.05, 0, 1.25],
  },
  {
    key: 'body',
    name: '杯身（PP 塑料杯）',
    bin: 'recyclable',
    binName: '可回收物 · 蓝桶',
    prep: '倒空、冲洗、沥干；有糖渍奶渍按其他垃圾',
    home: [0, 2.38, 0], split: [0, 2.55, 0], binPos: [-1.05, 0, 2.75],
  },
  {
    key: 'lid',
    name: '杯盖（PP / PS）',
    bin: 'recyclable',
    binName: '可回收物 · 蓝桶',
    prep: '冲洗、沥干，和杯身分开投',
    home: [0, 3.0, 0], split: [0, 3.6, 0], binPos: [-1.05, 0, 2.75],
  },
  {
    key: 'straw',
    name: '吸管与封口膜',
    bin: 'residual',
    binName: '其他垃圾 · 灰桶',
    prep: '直接投放',
    home: [0.14, 3.34, 0.1], split: [1.25, 3.5, 0.2], binPos: [3.05, 0, 1.25],
  },
];

// 四个桶的真实桶位。这件物品不产生有害垃圾，但桶位照实摆出来，
// 正好说明是逐部件判定：不是每件垃圾都会用到四个桶。
const BINS = [
  { key: 'kitchen',    name: '厨余垃圾', x: -3.05, z: 1.25 },
  { key: 'recyclable', name: '可回收物', x: -1.05, z: 2.75 },
  { key: 'hazardous',  name: '有害垃圾', x:  1.05, z: 2.75 },
  { key: 'residual',   name: '其他垃圾', x:  3.05, z: 1.25 },
];

/* ------------------------------------------------------------ 时间轴 */

const CYCLE = 12.0;
const T_SPLIT = 1.6;        // 开始拆
const T_SPLIT_END = 3.4;    // 拆完
const T_RESET = 9.4;        // 开始复位
const T_RESET_END = 10.6;   // 复位完成

// 第 i 个部件什么时候飞、什么时候到
function flyWindow(i) {
  return [3.4 + i * 1.3, 3.4 + i * 1.3 + 1.05];
}

function easeInOut(e) {
  return e < 0.5 ? 4 * e * e * e : 1 - Math.pow(-2 * e + 2, 3) / 2;
}
function easeOut(e) { return 1 - Math.pow(1 - e, 3); }
function lerp(a, b, e) { return a + (b - a) * e; }
function lerp3(a, b, e) {
  return [lerp(a[0], b[0], e), lerp(a[1], b[1], e), lerp(a[2], b[2], e)];
}

// 时间轴是纯函数：3D 渲染和 2D 降级动画共用它，两个渲染器不会各走各的
function sample(t) {
  const assembled = t < T_SPLIT || t > T_RESET_END;

  const parts = PARTS.map(function (p, i) {
    const w = flyWindow(i);
    let pos;
    let scale = 1;
    let visible = true;
    let phase = 'assembled';

    if (t < T_SPLIT) {
      pos = p.home.slice();
    } else if (t < T_SPLIT_END) {
      phase = 'split';
      const e = easeInOut((t - T_SPLIT) / (T_SPLIT_END - T_SPLIT));
      pos = lerp3(p.home, p.split, e);
    } else if (t < T_RESET) {
      if (t < w[0]) {
        phase = 'wait';
        pos = p.split.slice();
      } else if (t < w[1]) {
        phase = 'fly';
        const e = easeOut((t - w[0]) / (w[1] - w[0]));
        pos = lerp3(p.split, [p.binPos[0], 1.35, p.binPos[2]], e);
        pos[1] += Math.sin(Math.PI * e) * 0.85;
        scale = 1 - 0.62 * e;
        visible = e < 0.97;
      } else {
        phase = 'landed';
        pos = [p.binPos[0], 1.35, p.binPos[2]];
        scale = 0.38;
        visible = false;
      }
    } else {
      phase = 'reset';
      const e = easeInOut((t - T_RESET) / (T_RESET_END - T_RESET));
      pos = lerp3([p.binPos[0], 1.35, p.binPos[2]], p.home, e);
      scale = lerp(0.38, 1, e);
    }

    return {
      index: i, pos: pos, scale: scale, visible: visible,
      phase: phase, flying: phase === 'fly',
    };
  });

  // 桶口脉冲：由"最近一次落进来的时刻"推出来，同样是纯函数
  const pulses = {};
  BINS.forEach(function (b) {
    let last = -Infinity;
    PARTS.forEach(function (p, i) {
      if (p.bin !== b.key) return;
      const arrive = flyWindow(i)[1];
      if (arrive <= t) last = Math.max(last, arrive);
    });
    if (last === -Infinity) last -= CYCLE;   // 本轮还没轮到，用上一轮的落点
    pulses[b.key] = Math.max(0, 1 - (t - last) / 1.0);
  });

  return { parts: parts, pulses: pulses, assembled: assembled };
}

/* ------------------------------------------------------- 1920×1080 缩放 */

const stage = document.getElementById('stage');
const box = document.querySelector('.stage3d');

function fitStage() {
  const w = window.innerWidth || 1920;
  const h = window.innerHeight || 1080;
  const s = Math.min(w / 1920, h / 1080);
  stage.style.transform = 'scale(' + s + ')';
  stage.style.left = (w - 1920 * s) / 2 + 'px';
  stage.style.top = (h - 1080 * s) / 2 + 'px';
}

/* 快捷键：F 全屏、R 重播拆解动画。和大屏右下角的提示一致，
   原型页（Gradio）用的是同一套习惯。 */
function toggleFullscreen() {
  if (document.fullscreenElement) {
    document.exitFullscreen();
  } else if (document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen();
  }
}

document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const tag = e.target && e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
  if (e.key === 'f' || e.key === 'F') {
    toggleFullscreen();
    e.preventDefault();
  } else if (e.key === 'r' || e.key === 'R') {
    window.__screenRestart();
    e.preventDefault();
  }
});

/* --------------------------------------------------------- 四个部件小卡 */

const partsBox = document.getElementById('parts');
const partCards = PARTS.map(function (p) {
  const el = document.createElement('div');
  el.className = 'part';
  el.style.borderLeftColor = BIN_COLOR[p.bin];
  el.innerHTML =
    '<div class="nm">' + p.name + '</div>' +
    '<div class="bin" style="color:' + BIN_COLOR[p.bin] + '">' + p.binName + '</div>' +
    '<div class="prep">' + p.prep + '</div>';
  partsBox.appendChild(el);
  return el;
});

/* ------------------------------------------------------------ ECharts */

const TEXT_COLOR = '#E8DCC7';
const DIM_COLOR = '#9C9280';
const FAINT_LINE = 'rgba(232,220,199,.15)';
const MONO = 'IBM Plex Mono, Consolas, monospace';
const charts = [];

function makeChart(id, option) {
  const chart = echarts.init(document.getElementById(id), null, { renderer: 'canvas' });
  chart.setOption(option);
  charts.push(chart);
  return chart;
}

// 分桶分布：环形图 + 中心总数
makeChart('c-bins', {
  backgroundColor: 'transparent',
  tooltip: { trigger: 'item', formatter: '{b}：{c} 个部件（{d}%）' },
  legend: {
    orient: 'vertical', right: 2, top: 'middle',
    itemWidth: 9, itemHeight: 9, itemGap: 12,
    textStyle: { color: DIM_COLOR, fontSize: 13 },
    // 大屏是常驻展示，数值不能只藏在 tooltip 里，直接写进图例
    formatter: function (name) {
      const hit = BIN_DATA.filter(function (d) { return d.name === name; })[0];
      return hit ? name + '　' + hit.value : name;
    },
  },
  series: [{
    type: 'pie',
    radius: ['52%', '78%'],
    center: ['33%', '52%'],
    itemStyle: { borderColor: '#0B0E08', borderWidth: 2 },
    label: { show: false },
    emphasis: { scale: true, scaleSize: 6 },
    data: BIN_DATA.map(function (d) {
      return { value: d.value, name: d.name, itemStyle: { color: BIN_COLOR[d.key] } };
    }),
  }],
  graphic: [
    { type: 'text', left: '33%', top: '43%', style: {
        text: '263', fill: TEXT_COLOR, font: '500 30px ' + MONO, textAlign: 'center' } },
    { type: 'text', left: '33%', top: '57%', style: {
        text: '识别部件', fill: DIM_COLOR, font: '13px sans-serif', textAlign: 'center' } },
  ],
});

// 拆解引导评测：六项都是 1.000
makeChart('c-guide', {
  backgroundColor: 'transparent',
  grid: { left: 4, right: 52, top: 6, bottom: 2, containLabel: true },
  xAxis: { type: 'value', max: 1.04, show: false },
  yAxis: {
    type: 'category',
    inverse: true,
    data: GUIDE_METRICS.map(function (m) { return m[0]; }),
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: DIM_COLOR, fontSize: 12.5 },
  },
  series: [{
    type: 'bar',
    barWidth: 9,
    itemStyle: {
      borderRadius: [0, 5, 5, 0],
      color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
        { offset: 0, color: 'rgba(192,142,58,.35)' },
        { offset: 1, color: '#6E7B42' },
      ]),
    },
    label: {
      show: true, position: 'right', color: TEXT_COLOR,
      fontSize: 12.5, fontFamily: MONO,
      formatter: function (p) { return p.value.toFixed(3); },
    },
    data: GUIDE_METRICS.map(function (m) { return m[1]; }),
  }],
});

// 问答评测：用一条堆叠条表示 20 道题的构成，下面挂两个比率。
// 用条形而不是环形，是为了跟左边"分桶分布"的环形区分开，避免看串。
makeChart('c-qa', {
  backgroundColor: 'transparent',
  tooltip: { trigger: 'item', formatter: '{b}：{c} 题' },
  grid: { left: 2, right: 2, top: 8, height: 30, containLabel: false },
  xAxis: { type: 'value', max: 20, show: false },
  yAxis: {
    type: 'category', data: ['题'],
    axisLine: { show: false }, axisTick: { show: false }, axisLabel: { show: false },
  },
  series: [
    {
      name: '范围内', type: 'bar', stack: 'qa', barWidth: 26,
      itemStyle: { color: '#6E7B42', borderRadius: [7, 0, 0, 7] },
      label: { show: true, position: 'inside', color: '#0B0E08',
               fontSize: 13, fontWeight: 600, formatter: '{c}' },
      data: [QA.inScope],
    },
    {
      name: '范围外拒答', type: 'bar', stack: 'qa', barWidth: 26,
      itemStyle: { color: '#C08E3A' },
      label: { show: true, position: 'inside', color: '#0B0E08',
               fontSize: 13, fontWeight: 600, formatter: '{c}' },
      data: [QA.outScope],
    },
    {
      name: '边界样本', type: 'bar', stack: 'qa', barWidth: 26,
      itemStyle: { color: '#8E8B80', borderRadius: [0, 7, 7, 0] },
      label: { show: true, position: 'inside', color: '#0B0E08',
               fontSize: 13, fontWeight: 600, formatter: '{c}' },
      data: [QA.edge],
    },
  ],
  graphic: [
    { type: 'text', left: 4, top: 50, style: {
        text: '15 题范围内', fill: '#93A860', font: '12.5px sans-serif' } },
    { type: 'text', left: 104, top: 50, style: {
        text: '3 题范围外拒答', fill: '#C08E3A', font: '12.5px sans-serif' } },
    { type: 'text', left: 216, top: 50, style: {
        text: '2 题边界', fill: '#9C9280', font: '12.5px sans-serif' } },
    { type: 'text', left: 4, top: 86, style: {
        text: '引用来源命中率', fill: DIM_COLOR, font: '13px sans-serif' } },
    { type: 'text', right: 6, top: 79, style: {
        text: QA.cite.toFixed(3), fill: TEXT_COLOR, font: '500 26px ' + MONO, textAlign: 'right' } },
    { type: 'text', left: 4, top: 132, style: {
        text: '检索关键词覆盖率', fill: DIM_COLOR, font: '13px sans-serif' } },
    { type: 'text', right: 6, top: 125, style: {
        text: QA.keyword.toFixed(3), fill: '#C08E3A', font: '500 26px ' + MONO, textAlign: 'right' } },
    { type: 'text', left: 4, top: 170, style: {
        text: '本轮唯一没有满分的一项', fill: '#7A7264', font: '12px sans-serif' } },
  ],
});

// 覆盖率迭代：38.24% → 77.14% → 100%
makeChart('c-iter', {
  backgroundColor: 'transparent',
  grid: { left: 4, right: 16, top: 30, bottom: 2, containLabel: true },
  tooltip: {
    trigger: 'axis',
    formatter: function (ps) {
      const i = ps[0].dataIndex;
      return ITER[i].label + '照片：' + ITER[i].value + '%<br>' + ITER[i].note;
    },
  },
  xAxis: {
    type: 'category',
    data: ITER.map(function (d) { return d.label; }),
    axisLine: { lineStyle: { color: FAINT_LINE } },
    axisTick: { show: false },
    axisLabel: { color: DIM_COLOR, fontSize: 12.5 },
  },
  yAxis: {
    type: 'value', min: 0, max: 110,
    splitLine: { lineStyle: { color: 'rgba(232,220,199,.07)' } },
    axisLabel: { color: DIM_COLOR, fontSize: 11.5, formatter: '{value}%' },
  },
  series: [{
    type: 'line',
    symbolSize: 9,
    lineStyle: { color: '#C08E3A', width: 2 },
    itemStyle: { color: '#C08E3A', borderColor: '#0B0E08', borderWidth: 2 },
    areaStyle: {
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(192,142,58,.34)' },
        { offset: 1, color: 'rgba(192,142,58,0)' },
      ]),
    },
    label: {
      show: true, position: 'top', color: TEXT_COLOR,
      fontSize: 12.5, fontFamily: MONO,
      formatter: function (p) { return p.value + '%'; },
    },
    data: ITER.map(function (d) { return d.value; }),
  }],
});

/* -------------------------------------------------------------- 时钟 */

function tick() {
  const d = new Date();
  const pad = function (n) { return String(n).padStart(2, '0'); };
  document.getElementById('clock-time').textContent =
    pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
  document.getElementById('clock-date').textContent =
    d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' · 数据为静态快照';
}

/* --------------------------------------------------- 没有 WebGL 时的降级 */

// 用 DOM 画一套 2D 示意图：四张部件卡按时间轴飞向四个桶。
// 版式和数据面板都不受影响，屏幕上会多一行说明。
function start2D(reason) {
  if (document.getElementById('fb')) return;

  const fb = document.createElement('div');
  fb.className = 'fb';
  fb.id = 'fb';

  const note = document.createElement('div');
  note.className = 'fb-note';
  note.textContent = '当前浏览器未启用 WebGL，三维演示已换成 2D 示意（数据面板不受影响）';
  fb.appendChild(note);

  const binRow = document.createElement('div');
  binRow.className = 'fb-bins';
  const binEls = {};
  BINS.forEach(function (b) {
    const el = document.createElement('div');
    el.className = 'fb-bin';
    el.style.borderColor = BIN_COLOR[b.key];
    el.style.color = BIN_COLOR[b.key];
    el.textContent = b.name;
    binRow.appendChild(el);
    binEls[b.key] = el;
  });
  fb.appendChild(binRow);

  const chipEls = PARTS.map(function (p) {
    const el = document.createElement('div');
    el.className = 'fb-chip';
    el.style.borderLeftColor = BIN_COLOR[p.bin];
    el.innerHTML = '<b>' + p.name + '</b><i>→ ' + p.binName + '</i>';
    fb.appendChild(el);
    return el;
  });

  box.appendChild(fb);

  function frame() {
    requestAnimationFrame(frame);
    const t = window.__screenNowT();
    const st = sample(t);
    const w = box.clientWidth;
    const h = box.clientHeight;
    const binX = {};
    BINS.forEach(function (b, i) {
      binX[b.key] = w * (0.125 + i * 0.25);
    });

    st.parts.forEach(function (s, i) {
      const el = chipEls[i];
      const p = PARTS[i];
      const fromX = w * 0.5;
      const fromY = h * (0.18 + i * 0.09);
      const toX = binX[p.bin];
      const toY = h * 0.78;

      let x = fromX;
      let y = fromY;
      let scale = 1;
      let opacity = 1;

      if (s.phase === 'fly') {
        const e = easeOut(Math.min(1, Math.max(0, (t - flyWindow(i)[0]) / (flyWindow(i)[1] - flyWindow(i)[0]))));
        x = lerp(fromX, toX, e);
        y = lerp(fromY, toY, e) - Math.sin(Math.PI * e) * 46;
        scale = 1 - 0.3 * e;
        opacity = 1 - 0.25 * e;
      } else if (s.phase === 'landed') {
        x = toX; y = toY; scale = 0.85; opacity = 0;
      } else if (s.phase === 'reset') {
        const e = easeInOut(Math.min(1, Math.max(0, (t - T_RESET) / (T_RESET_END - T_RESET))));
        x = lerp(toX, fromX, e);
        y = lerp(toY, fromY, e);
        scale = 0.85 + 0.15 * e;
        opacity = e;
      }

      el.style.opacity = opacity;
      el.style.transform =
        'translate(-50%,-50%) translate(' + x + 'px,' + y + 'px) scale(' + scale + ')';
      partCards[i].classList.toggle('on', s.flying);
    });

    BINS.forEach(function (b) {
      const el = binEls[b.key];
      const k = 1 + st.pulses[b.key] * 0.08;
      el.style.transform = 'scale(' + k + ')';
      el.classList.toggle('on', st.pulses[b.key] > 0.2);
    });
  }

  frame();
  window.addEventListener('resize', function () {
    charts.forEach(function (c) { c.resize(); });
  });
}

/* -------------------------------------------------------------- 启动 */

function boot() {
  fitStage();
  tick();
  setInterval(tick, 1000);

  window.addEventListener('resize', function () {
    fitStage();
    charts.forEach(function (c) { c.resize(); });
    if (window.__screenRelayout3D) window.__screenRelayout3D();
  });

  document.getElementById('hint').addEventListener('click', function () {
    window.__screenRestart();
  });

  // scene3d.js 已经跑完了：它成功就什么都不用做，失败就换成 2D
  const ok = window.__scene3dOk === true;
  if (!ok) {
    start2D(window.__scene3dError || '未启用 WebGL');
    const hint = document.getElementById('hint');
    hint.textContent = '按 F11 全屏 · 当前为 2D 示意模式（浏览器未启用 WebGL）';
  }
}

let animStart = performance.now() / 1000;

// 两个渲染器都通过它取当前时间，重播时只需要把它拨回 0
function nowT() { return (performance.now() / 1000 - animStart) % CYCLE; }

window.__screenNowT = nowT;
window.__screenRestart = function () { animStart = performance.now() / 1000; };
window.screenBoot = boot;
