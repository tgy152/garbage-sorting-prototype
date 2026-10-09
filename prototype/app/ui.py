"""Gradio 界面。

页签对应参赛材料里需要证明的几件事：
    拍照识别 → 作品核心功能，也是"小切口"的落点
    问答辅助 → 解释类别判定依据，功能演示视频的主体素材
    知识库   → 场景数据来源与可维护性
    效果验证 → 方案书「测试与验证」章节的数据来源
    方案素材 → 架构图 / 配置快照 / 场景定义，可直接粘进方案书附录
    计算校核 → 上一版（暖通课程设计）场景的规则校核，保留用于演示可插拔设计
"""

from __future__ import annotations

import base64
import io
import json
from html import escape
from pathlib import Path

import gradio as gr
import pandas as pd
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app import render
from app.checker import load_engine
from app.config import Settings, get_settings
from app.disassembler import WasteDisassembler, load_disassembler
from app.scenes import list_scene_ids
from app.service import SceneService
from app.vision import MockVisionBackend, build_vision_backend

# 作品名称，会同时出现在浏览器标签页与页面主标题
APP_TITLE = "智识固废：垃圾分类视觉识别与投放引导 · 原型演示"

# 主题向 Organic 锚点靠拢：全站人文衬线、大圆角、暖中性色
# Fraunces 是锚点限定的显示衬线，本机未安装，走 Google Fonts；
# 加载失败时自动回退到本机已安装的 Noto Serif SC，不影响使用。
FONT_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&display=swap">
"""

# 样式通过 <head> 注入，不走 gr.Blocks(css=...)。
# 原因：Gradio 会把 css= 传入的选择器重写成带作用域前缀的形式，例如
#   .gradio-container .tabs .tab-container:not(.visually-hidden) button
# 会被改成
#   .gradio-container.gradio-container-5-50-0-dev0 .contain .gradio-container .tabs ...
# 其中 `.contain .gradio-container` 这层在真实 DOM 里并不存在，规则因此失效。
# 只有一部分规则侥幸保留了未加前缀的副本所以看起来正常，带 :not() 的则完全失效。
# 直接写进 <head> 可以绕开这个改写。

# PWA 声明：让页面可以被"添加到主屏幕"，以独立窗口运行。
PWA_HEAD = """
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#3A4032">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<!-- 用 black 不用 black-translucent：后者会让页面顶到状态栏底下，
     首屏标题被刘海和状态栏压住。black 是不透明状态栏，内容从它下面开始。 -->
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="垃圾投放引导">
<link rel="icon" type="image/png" sizes="192x192" href="/pwa/icon-192.png">
<link rel="apple-touch-icon" href="/pwa/apple-touch-icon.png">
<script>
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
      navigator.serviceWorker.register('/sw.js').catch(function () {});
    });
  }
  // 一键安装：浏览器肯把安装事件交给我们时，首屏的「安装到手机」直接弹系统安装框。
  // 拿不到事件的情况（iOS、微信内置浏览器、局域网 http 地址）就让链接照常跳到 /app，
  // 那一页会分情况说明该怎么装。
  window.__installPrompt = null;
  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    window.__installPrompt = event;
  });
  document.addEventListener('click', function (event) {
    var node = event.target;
    var link = node && node.closest ? node.closest('a[href="/app"]') : null;
    if (!link || !window.__installPrompt) return;
    event.preventDefault();
    var prompt = window.__installPrompt;
    window.__installPrompt = null;
    prompt.prompt();
  }, true);
</script>
"""

# 动效：GSAP + ScrollTrigger，两个文件放在 app/static/ 由 /static 挂出去，
# 不依赖 CDN，断网也能跑。没有加载成功时下面的脚本直接返回，页面照常显示。
GSAP_HEAD = """
<script src="/static/gsap.min.js"></script>
<script src="/static/ScrollTrigger.min.js"></script>
<script>
/*
  原型页的动效只做两件事，都在"给操作反馈"的范围内：
    1) 首屏入场：标题、说明、标签、按钮按次序到位
    2) 结果出现：识别 / 问答 / 评测产出的面板插进来时，轻轻推上来
  Gradio 每次都是重建节点，所以用 MutationObserver 接，而不是绑在某个元素上。
  系统开了"减少动态效果"时全部跳过。
*/
(function () {
  window.__gsapHeadRan = true;
  try {
  /* ---------------- 动画部分 ----------------
     Gradio 注入 head 时会调整 <script> 顺序，这段可能比 gsap 先执行，
     所以整块包进 initMotion()，等 gsap 到位再调用，不在解析期依赖它。 */
  function initMotion() {
  if (window.__protoMotionReady) return;
  window.__protoMotionReady = true;
  if (window.ScrollTrigger) gsap.registerPlugin(ScrollTrigger);

  function boot() {
    gsap.defaults({ ease: "power2.out", duration: 0.6 });

    var seen = new WeakSet();

    function enterHero(nodes) {
      if (!nodes.length) return;
      gsap.from(nodes, { y: 18, autoAlpha: 0, stagger: 0.06, clearProps: 'all' });
    }
    function pop(node) {
      if (!node || seen.has(node)) return;
      seen.add(node);
      gsap.from(node, { y: 14, autoAlpha: 0, duration: 0.45, clearProps: 'all' });
    }

    // Gradio 会在首屏挂好之后重建节点，所以每个新插入的子树都过一遍这里
    function handle(root) {
      if (!root || root.nodeType !== 1) return;
      var cls = root.classList;
      if (cls && cls.contains('hero')) {
        enterHero(root.querySelectorAll('h1, p, .tags span, .cta'));
        return;
      }
      if (cls && (cls.contains('panel') || cls.contains('empty') || cls.contains('list'))) {
        pop(root);
        return;
      }
      if (!root.querySelectorAll) return;
      var hero = root.querySelector('.hero');
      if (hero) enterHero(hero.querySelectorAll('h1, p, .tags span, .cta'));
      Array.prototype.forEach.call(root.querySelectorAll('.panel, .empty'), pop);
    }

    // 脚本在 <head> 里执行，此刻 body 可能还没建出来；用 documentElement 做观察根最稳
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () { handle(document.body); });
    } else {
      handle(document.body);
    }
    new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        Array.prototype.forEach.call(m.addedNodes, handle);
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  // 系统要求减少动态效果就不注册任何动画
  var mm = gsap.matchMedia();
  mm.add(
    { motion: "(prefers-reduced-motion: no-preference)", reduce: "(prefers-reduced-motion: reduce)" },
    function (ctx) {
      if (ctx.conditions.reduce) return;
      boot();
    }
  );
  }

  /* ---------------------------------------------------------------
     键盘快捷键。答辩 PPT 里是 ← → 翻页、F 全屏，这里按同一套习惯
     给原型配一套：方向键切换页签、数字键直达、F 全屏、R 重播动效。
     在输入框里打字时不抢键。
     --------------------------------------------------------------- */
  function tabButtons() {
    var list = document.querySelectorAll('.tab-nav button, button[role="tab"]');
    return Array.prototype.slice.call(list);
  }
  function currentTab(list) {
    for (var i = 0; i < list.length; i++) {
      if (list[i].getAttribute('aria-selected') === 'true' ||
          list[i].classList.contains('selected')) return i;
    }
    return -1;
  }
  function switchTab(step) {
    var list = tabButtons();
    if (!list.length) return;
    var i = currentTab(list);
    var next = i < 0 ? 0 : (i + step + list.length) % list.length;
    list[next].click();
  }
  function toggleFullscreen() {
    if (document.fullscreenElement) { document.exitFullscreen(); }
    else if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen();
    }
  }
  function replayHero() {
    if (!window.gsap) { withGsap(); return; }
    var hero = document.querySelector('.hero');
    if (!hero) return;
    gsap.from(hero.querySelectorAll('h1, p, .tags span, .cta'), {
      y: 18, autoAlpha: 0, stagger: 0.06, clearProps: 'all'
    });
  }

  // gsap 到没到位都可能，两种都接上：已经在就直接跑，没在就轮询 + load 事件兜底
  function withGsap() {
    if (!window.gsap || window.__protoMotionReady) return;
    initMotion();
  }
  if (window.gsap) {
    withGsap();
  } else {
    var tries = 0;
    var timer = setInterval(function () {
      if (window.gsap) { clearInterval(timer); withGsap(); }
      else if (++tries > 50) { clearInterval(timer); }
    }, 100);
    window.addEventListener('load', withGsap);
  }

  function withHint() {
    var hint = document.createElement('div');
    hint.id = 'kb-hint';
    hint.innerHTML = '<b>F</b> 全屏　<b>← →</b> 切页签　<b>1–5</b> 直达　<b>R</b> 重播动效';
    document.body.appendChild(hint);
    // 常驻 7 秒后淡出，鼠标移到窗口底部再出现一次
    var timer = setTimeout(function () { hint.classList.add('gone'); }, 7000);
    document.addEventListener('mousemove', function (e) {
      if (e.clientY > window.innerHeight - 90) {
        hint.classList.remove('gone');
        clearTimeout(timer);
        timer = setTimeout(function () { hint.classList.add('gone'); }, 4000);
      }
    });
  }

  function ready(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  ready(withHint);

  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    /* 输入法正在拼字时一律不抢键：
       中文输入法的 keyCode 是 229，且 isComposing 为 true，
       这时候 preventDefault 会把候选字吃掉。 */
    if (e.isComposing || e.keyCode === 229) return;
    /* 焦点在输入类控件里（含嵌套在组件内部的输入框）也不抢键 */
    var t = e.target;
    if (t && t.closest && t.closest('input, textarea, select, [contenteditable="true"], [contenteditable=""]')) return;

    var k = e.key;
    if (k === 'f' || k === 'F') { toggleFullscreen(); e.preventDefault(); }
    else if (k === 'r' || k === 'R') { replayHero(); e.preventDefault(); }
    else if (k === 'ArrowRight' || k === 'PageDown') { switchTab(1); e.preventDefault(); }
    else if (k === 'ArrowLeft' || k === 'PageUp') { switchTab(-1); e.preventDefault(); }
    else if (k >= '1' && k <= '9') {
      var list = tabButtons();
      var idx = parseInt(k, 10) - 1;
      if (list[idx]) { list[idx].click(); e.preventDefault(); }
    }
  }, true);
  } catch (err) {
    window.__gsapHeadError = String(err && err.message ? err.message : err);
  }
})();
</script>
"""

STYLE_HEAD = FONT_HEAD + PWA_HEAD + GSAP_HEAD + "\n<style>\n" + render.PAGE_CSS + "\n</style>\n"

ORGANIC_THEME = gr.themes.Base(
    font=[
        "Noto Serif SC",
        "Fraunces",
        "Source Han Serif SC",
        "Songti SC",
        "Georgia",
        "serif",
    ],
    font_mono=["IBM Plex Mono", "Consolas", "monospace"],
    radius_size=gr.themes.sizes.radius_xxl,
    spacing_size=gr.themes.sizes.spacing_lg,
    text_size=gr.themes.sizes.text_md,
    primary_hue=gr.themes.colors.lime,
    neutral_hue=gr.themes.colors.stone,
)

ARCHITECTURE_MERMAID = """```mermaid
flowchart TB
    subgraph 用户层
        U1[学生 / 社区住户<br/>日常投放者]
        U2[保洁物业 / 志愿者<br/>值守与二次分拣]
    end

    subgraph 应用层
        UI[Gradio 交互界面]
        T1[拍照识别与投放引导]
        T2[问答辅助]
        T3[知识库管理]
        T4[效果验证]
        UI --> T1 & T2 & T3 & T4
    end

    subgraph 服务层
        VIS[视觉识别层<br/>画面 → 部件清单]
        DIS[拆解引导引擎<br/>部件 → 分步投放指令]
        SVC[检索与问答编排]
    end

    subgraph 算法层
        V1[多模态大模型<br/>通义千问-VL / GLM-4V]
        V2[离线预置场景]
        R1[复合垃圾拆解规则]
        R2[单一物品判定规则]
        R3[地区标准标签切换]
        RET[检索后端<br/>本地索引 / Dify 数据集]
        GEN[生成后端<br/>大模型 / 离线模拟]
    end

    subgraph 数据层
        D1[规则库 YAML<br/>教师与环卫人员可维护]
        D2[分类知识库<br/>总则 / 拆解原则 / 误投清单]
        D3[评测集与 ground truth]
    end

    用户层 --> 应用层
    T1 --> VIS --> V1
    VIS --> V2
    VIS --> DIS
    DIS --> R1 & R2 & R3
    R1 & R2 & R3 --> D1
    T2 --> SVC --> RET
    SVC --> GEN
    RET --> D2
    T4 --> D3
```"""


def _scene_choices(settings: Settings) -> list[str]:
    ids = list_scene_ids(settings.scenes_dir)
    if not ids:
        return [settings.scene_id]
    if settings.scene_id in ids:
        ids = [settings.scene_id] + [i for i in ids if i != settings.scene_id]
    return ids


def _dropdown_value(choices: list, preferred: str | None):
    """安全构造下拉选项：当 preferred 不在选项中时退回第一项或 None。

    Gradio 会在 value 不属于 choices 时告警，并且前端可能因此渲染异常，
    所以这里统一做一次校验。
    """
    values = [item[1] if isinstance(item, (tuple, list)) else item for item in choices]
    if preferred in values:
        return preferred
    return values[0] if values else None


def _pick_free_port(host: str, preferred: int, attempts: int = 12) -> int:
    """返回一个可用的端口；优先使用配置端口，被占用时向后顺延。"""
    import socket

    for offset in range(attempts):
        candidate = preferred + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
            except OSError:
                continue
        return candidate
    return preferred


def _render_answer(answer) -> tuple[str, str]:
    """返回 (带引用的回答 markdown, 元信息 markdown)。"""
    body = answer.text
    if answer.citations:
        body += "\n\n---\n\n**引用来源**\n\n"
        body += "\n".join(citation.to_markdown() for citation in answer.citations)

    meta = (
        f"后端 `{answer.backend}` ｜ 检索 {answer.retrieval_ms:.0f} ms ｜ "
        f"生成 {answer.generation_ms:.0f} ms ｜ 总计 {answer.latency_ms:.0f} ms ｜ "
        f"引用 {len(answer.citations)} 条 ｜ {'已拒答' if answer.refused else '正常回答'}"
    )
    return body, meta


def build_demo() -> gr.Blocks:
    settings = get_settings()
    scene_ids = _scene_choices(settings)
    services: dict[str, SceneService] = {}
    engine_cache: dict[str, object] = {}
    disassembler_cache: dict[str, WasteDisassembler | None] = {}
    vision_cache: dict[str, object] = {}

    def get_service(scene_id: str) -> SceneService:
        if scene_id not in services:
            services[scene_id] = SceneService(settings, scene_id)
        return services[scene_id]

    def get_engine(scene_id: str):
        """没有对应规则库的场景返回 None，界面上给出提示。"""
        if scene_id not in engine_cache:
            rule_path = settings.rules_dir / f"{scene_id}.yaml"
            engine_cache[scene_id] = (
                load_engine(settings.rules_dir, scene_id) if rule_path.exists() else None
            )
        return engine_cache[scene_id]

    def get_disassembler(scene_id: str) -> WasteDisassembler | None:
        """没有拆解规则库的场景返回 None，界面上给出提示。"""
        if scene_id not in disassembler_cache:
            rule_path = settings.rules_dir / f"{scene_id}.yaml"
            candidate = load_disassembler(settings.rules_dir, scene_id) if rule_path.exists() else None
            disassembler_cache[scene_id] = (
                candidate if candidate is not None and candidate.composites else None
            )
        return disassembler_cache[scene_id]

    def get_vision(scene_id: str):
        if scene_id not in vision_cache:
            vision_cache[scene_id] = build_vision_backend(settings)
        return vision_cache[scene_id]

    def scenario_options() -> list[tuple[str, str]]:
        """预置场景选项始终来自离线场景文件。

        即使当前用真实视觉模型，下拉也保持有内容，
        切回 mock 模式时可直接选用，不用重新启动。
        """
        return MockVisionBackend(settings.vision_scenarios_path).options()

    def scenario_label() -> str:
        if settings.resolved_vision_backend == "mock":
            return "离线预置场景（当前生效）"
        return "离线预置场景（当前用真实视觉模型，此项仅在 mock 模式生效）"

    get_service(scene_ids[0])
    # 构建时就把下拉选项填好，避免在 demo.load 触发前为空导致校验失败
    _default_disassembler = get_disassembler(scene_ids[0])
    _default_vision = get_vision(scene_ids[0])
    default_scenarios = scenario_options()
    default_regions = (
        _default_disassembler.region_options() if _default_disassembler else []
    )

    def status_markdown(scene_id: str) -> str:
        """状态条：用彩色胶囊替代长串项目符号，一行扫完。"""
        service_status = get_service(scene_id).status()
        pills: list[tuple[str, str]] = [
            (str(service_status.get("场景", scene_id)), "info"),
        ]

        llm = str(service_status.get("生成后端", ""))
        pills.append((f"问答生成 · {llm.split('：')[-1]}", "ok" if "✅" in llm else "bad"))

        vision = get_vision(scene_id)
        vision_ok, vision_message = vision.health()
        pills.append((f"视觉 · {vision_message}", "ok" if vision_ok else "warn"))

        disassembler = get_disassembler(scene_id)
        if disassembler:
            pills.append(
                (
                    f"规则库 · {len(disassembler.composites)} 类复合 + "
                    f"{len(disassembler.singles)} 类单品",
                    "ok",
                )
            )
        else:
            pills.append(("规则库 · 未配置", "neutral"))

        pills.append((f"运行模式 · {settings.app_mode}", "neutral"))
        return render.status_html(pills)

    def on_scene_change(scene_id: str):
        scene = get_service(scene_id).scene
        disassembler = get_disassembler(scene_id)
        scenario_choices = scenario_options()
        region_choices = disassembler.region_options() if disassembler else []
        return (
            status_markdown(scene_id),
            gr.update(choices=scene.sample_questions or [], value=None),
            f"### {scene.name}\n\n{scene.welcome}",
            gr.update(
                choices=scenario_choices,
                value=_dropdown_value(scenario_choices, None),
            ),
            gr.update(
                choices=region_choices,
                value=_dropdown_value(region_choices, settings.region),
            ),
        )

    # ---------- 计算校核 ----------

    # ---------- 拍照识别与投放引导 ----------

    def run_vision(image_path, scenario_id, region, bin_type, scene_id: str):
        disassembler = get_disassembler(scene_id)
        if disassembler is None:
            return (
                render.empty_html("当前场景未配置拆解规则库"),
                render.empty_html(
                    "请在 rules/<场景ID>.yaml 中定义 composites 与 singles"
                ),
                "",
                [],
            )

        vision = get_vision(scene_id)
        try:
            result = vision.analyze(image_path, hint=scenario_id or "")
        except Exception as exc:  # noqa: BLE001
            return (
                render.empty_html("识别失败"),
                render.empty_html(
                    f"{exc}。请检查 VISION_API_KEY / VISION_BASE_URL / VISION_MODEL，"
                    "或把 VISION_BACKEND 设为 mock 先用预置场景跑通流程"
                ),
                "",
                [],
            )

        guidance = disassembler.guide(result, region, bin_type or "")

        vision_html = render.vision_html(result, result.note)

        overview_pills: list[tuple[str, str]] = [
            (f"部件 {len(guidance.all_parts)} 项", "info"),
            ("复合垃圾" if guidance.is_composite else "单一物品", "info"),
        ]
        if guidance.has_conditional:
            overview_pills.append(("含条件判定", "warn"))
        if guidance.has_pitfall:
            overview_pills.append(("含误投提示", "warn"))
        if guidance.unmatched:
            overview_pills.append((f"未匹配 {len(guidance.unmatched)} 项", "bad"))
        else:
            overview_pills.append(("规则全覆盖", "ok"))
        if guidance.mismatches:
            overview_pills.append((f"混投 {len(guidance.mismatches)} 项", "bad"))
        overview_html = render.status_html(overview_pills)

        out_dir = settings.export_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = result.scenario_id or "识别结果"
        guide_path = out_dir / f"{stem}-投放引导.md"
        detail_path = out_dir / f"{stem}-拆解明细.csv"
        guide_path.write_text(
            f"# 投放引导：{guidance.summary}\n\n{guidance.to_markdown()}\n",
            encoding="utf-8",
        )
        pd.DataFrame(
            [
                {
                    "部件": part.part,
                    "类别": part.category_label,
                    "桶色": part.bin_color,
                    "投放前处理": "；".join(part.prep),
                    "条件说明": part.conditional,
                    "常见误投": part.pitfall,
                    "来源": part.source,
                }
                for part in guidance.all_parts
            ]
        ).to_csv(detail_path, index=False, encoding="utf-8-sig")

        return vision_html, render.guidance_html(guidance), overview_html, [
            str(guide_path),
            str(detail_path),
        ]

    # ---------- 计算校核（暖通场景）----------

    def run_check(file_value, scene_id: str):
        engine = get_engine(scene_id)
        if engine is None:
            return (
                pd.DataFrame(),
                "该场景未配置规则库。请在 `rules/<场景ID>.yaml` 中定义校核规则。",
                "-",
                [],
            )

        if file_value:
            csv_path = Path(file_value)
        else:
            csv_path = settings.samples_dir / "学生计算表_示例.csv"

        if not csv_path.exists():
            return pd.DataFrame(), f"找不到文件：{csv_path}", "-", []

        try:
            frame = engine.load_csv(csv_path)
        except Exception as exc:  # noqa: BLE001
            return pd.DataFrame(), f"读取失败：{exc}", "-", []

        report = engine.check_frame(frame)
        scores = report.room_scores(engine.penalty)

        headline = "\n".join(
            [
                f"### 校核结果：{csv_path.name}",
                "",
                f"- 校核房间：**{report.rows_checked}** 间 ｜ 校核项：**{report.total_checks}** 项次",
                f"- 一次通过率：**{report.pass_rate * 100:.1f}%**",
                f"- 错误 **{report.error_count}** 处 ｜ 警告 **{report.warning_count}** 处",
                f"- 错误密度：**{report.error_density}** 处/房间",
                f"- 完全无错房间：**{report.clean_rooms} / {report.rows_checked}**",
            ]
        )
        if report.missing_fields:
            headline += "\n\n**缺失字段（相关规则未参与校核）**：" + "、".join(
                report.missing_fields[:8]
            )

        score_lines = ["", "**各房间得分**", "", "| 房间 | 得分 |", "| --- | --- |"]
        for room_id, score in scores.items():
            score_lines.append(f"| {room_id} | {score} |")
        headline += "\n".join(score_lines)

        ranking = report.error_ranking()
        if ranking:
            ranking_lines = ["", "**错因排行（教学重点）**", "", "| 规则 | 检查项 | 触发次数 |", "| --- | --- | --- |"]
            ranking_lines += [f"| {rid} | {title} | {count} |" for rid, title, count in ranking]
            headline += "\n".join(ranking_lines)

        out_dir = settings.export_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = csv_path.stem
        detail_path = out_dir / f"{stem}-校核明细.csv"
        report_path = out_dir / f"{stem}-校核报告.md"
        report.to_frame().to_csv(detail_path, index=False, encoding="utf-8-sig")
        report_path.write_text(report.to_markdown(), encoding="utf-8")

        display = report.to_frame()
        if not display.empty:
            display = display[
                ["房间编号", "房间名称", "级别", "规则编号", "检查项", "应有取值", "实际取值", "常见错因", "改正建议"]
            ]

        status = (
            f"共 {report.rows_checked} 间房、{report.total_checks} 项次 ｜ "
            f"错误 {report.error_count}、警告 {report.warning_count} ｜ "
            f"{'✅ 全部房间通过' if report.error_count == 0 else '❌ 存在问题，见下方明细'}"
        )
        return display, headline, status, [str(detail_path), str(report_path)]

    # ---------- 问答 ----------

    def respond(message: str, history: list[dict], scene_id: str):
        message = (message or "").strip()
        history = history or []
        if not message:
            return history, "", "", "请输入问题。"

        service = get_service(scene_id)
        past = [
            {"role": turn["role"], "content": turn["content"]}
            for turn in history
            if turn.get("role") in {"user", "assistant"} and turn.get("content")
        ]
        try:
            answer = service.answer(message, past)
        except Exception as exc:  # noqa: BLE001
            # 现场演示时模型侧可能超时或额度用尽，这里兜底成可读提示，
            # 而不是把异常直接抛到对话面板上。
            body = (
                "这次没能拿到模型回答。\n\n"
                f"错误信息：`{exc}`\n\n"
                "可以检查 `.env` 里的 `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`，"
                "或把 `APP_MODE` 改回 `mock`，用离线答案先把流程讲完。"
            )
            updated = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": body},
            ]
            return (
                updated,
                "",
                "_模型调用失败_",
                f"_已处理，共 {len(updated) // 2} 轮对话_",
            )

        body, meta = _render_answer(answer)

        updated = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": body},
        ]
        return updated, "", meta, f"_已处理，共 {len(updated) // 2} 轮对话_"

    def ask_sample(question: str, history: list[dict], scene_id: str):
        return respond(question, history, scene_id)

    def clear_chat():
        return [], "", "", ""

    # ---------- 知识库 ----------

    def upload_files(files, scene_id: str):
        if not files:
            return "未选择文件。", status_markdown(scene_id)
        service = get_service(scene_id)
        saved = service.import_documents([str(path) for path in files])
        return (
            f"已导入 {len(saved)} 个文件：{', '.join(saved)}\n\n点击「重建索引」后生效。",
            status_markdown(scene_id),
        )

    def rebuild(scene_id: str):
        service = get_service(scene_id)
        meta = service.rebuild_index()
        detail = "\n".join(f"- {key}：{value}" for key, value in meta.items())
        return f"### 索引已重建\n\n{detail}", status_markdown(scene_id)

    # ---------- 效果验证 ----------

    def run_eval(limit, scene_id: str):
        from eval.run_eval import (
            evaluate_one,
            load_eval_set,
            render_chart,
            render_report,
            resolve_eval_set,
            summarize,
        )

        service = get_service(scene_id)
        records = load_eval_set(resolve_eval_set(scene_id))
        if limit:
            records = records[: int(limit)]

        rows = [evaluate_one(service, record) for record in records]
        frame = pd.DataFrame(rows)
        summary = summarize(frame)

        stem = f"{scene_id}-{settings.app_mode}-ui"
        out_dir = settings.eval_out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        detail_path = out_dir / f"{stem}-明细.csv"
        chart_path = out_dir / f"{stem}-指标图.png"
        report_path = out_dir / f"{stem}-报告.md"
        summary_path = out_dir / f"{stem}-汇总.json"

        frame.to_csv(detail_path, index=False, encoding="utf-8-sig")
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        chart_ok = render_chart(summary, chart_path)
        report_path.write_text(render_report(summary, frame), encoding="utf-8")

        downloads = [str(detail_path), str(summary_path), str(report_path)]
        if chart_ok:
            downloads.append(str(chart_path))
        return frame, render.metrics_html(summary), downloads

    # ---------- 方案素材 ----------

    def export_scene(scene_id: str) -> str:
        return get_service(scene_id).export_scene_card()

    def export_config() -> str:
        return json.dumps(settings.public_summary(), ensure_ascii=False, indent=2)

    with gr.Blocks(
        title=APP_TITLE,
        theme=ORGANIC_THEME,
        head=STYLE_HEAD,
    ) as demo:
        gr.HTML(
            render.hero_html(
                APP_TITLE,
                "拍一张照片，自动拆解出每一部分该投哪个桶、投之前要做什么，"
                "并指出最容易投错的地方。聚焦四类投放点：宿舍楼 / 教学楼 / 食堂 / 快递点。",
                [
                    "复合垃圾拆解",
                    "条件化判定",
                    "混投检查",
                    "四地区口径",
                    "规则库可维护",
                ],
                # 首屏入口：作品介绍页原来只藏在「⑤ 方案素材」页签里，
                # 手机上既找不到也点不准，所以提到首屏做成 44px 按钮。
                [
                    ("作品介绍页", "/landing/"),
                    ("数据大屏", "/screen/"),
                    ("安装到手机", "/app"),
                    ("扫码分享", "/share"),
                ],
            )
        )

        with gr.Row():
            scene_dropdown = gr.Dropdown(
                choices=scene_ids, value=scene_ids[0], label="场景", scale=1
            )
            with gr.Column(scale=3):
                status_box = gr.HTML(status_markdown(scene_ids[0]))

        with gr.Tabs():
            with gr.Tab("① 拍照识别"):
                gr.Markdown(
                    "上传或拍摄一张垃圾照片，系统会先识别出画面中**所有需要分别投放的部件**，"
                    "再按规则库拆解成「投哪个桶 + 投之前做什么」的分步引导，"
                    "并指出最容易投错的地方。\n\n"
                    "> 复合垃圾（奶茶、外卖、泡面桶）是本功能的重点。"
                    "现有查询工具只回答「某物属于哪一类」，"
                    "不回答「要拆成几部分、投之前先做什么」。"
                )
                with gr.Row():
                    with gr.Column(scale=1):
                        waste_image = gr.Image(
                            label="垃圾照片",
                            type="filepath",
                            sources=["upload", "webcam"],
                            height=280,
                        )
                        with gr.Row():
                            mock_scenario = gr.Dropdown(
                                choices=default_scenarios,
                                value=_dropdown_value(default_scenarios, None),
                                label=scenario_label(),
                            )
                            region_dropdown = gr.Dropdown(
                                choices=default_regions,
                                value=_dropdown_value(default_regions, settings.region),
                                label="地区标准",
                            )
                            bin_dropdown = gr.Dropdown(
                                choices=[
                                    ("不指定（只做投放引导）", ""),
                                    ("可回收物桶（蓝）", "recyclable"),
                                    ("有害垃圾桶（红）", "hazardous"),
                                    ("厨余垃圾桶（绿）", "kitchen"),
                                    ("其他垃圾桶（灰）", "residual"),
                                ],
                                value="",
                                label="这是哪个桶（选了就做混投检查）",
                            )
                        vision_button = gr.Button("识别并生成投放引导", variant="primary")
                        vision_overview = gr.HTML(
                            '<div class="footnote">选择照片或直接点按钮使用离线预置场景</div>'
                        )
                    with gr.Column(scale=2):
                        vision_result = gr.HTML(
                            '<div class="empty">等待识别<br>'
                            "上传照片后这里会显示识别到的部件</div>"
                        )
                        guidance_result = gr.HTML(render.empty_html())
                vision_files = gr.Files(label="下载引导产出", interactive=False)

                vision_button.click(
                    run_vision,
                    [waste_image, mock_scenario, region_dropdown, bin_dropdown, scene_dropdown],
                    [vision_result, guidance_result, vision_overview, vision_files],
                )

            with gr.Tab("② 问答辅助"):
                scene_intro = gr.Markdown("")
                with gr.Row():
                    with gr.Column(scale=3):
                        chatbot = gr.Chatbot(
                            type="messages", height=420, label="对话", show_copy_button=True
                        )
                        message_box = gr.Textbox(
                            placeholder="例如：外卖餐盒需要洗干净再扔吗？",
                            label="问题",
                            lines=2,
                            max_lines=10,
                        )
                        with gr.Row():
                            send_button = gr.Button("发送", variant="primary")
                            clear_button = gr.Button("清空对话")
                        sample_dropdown = gr.Dropdown(
                            choices=[], label="试试示例问题", value=None
                        )
                    with gr.Column(scale=2):
                        meta_box = gr.Markdown("_等待提问_")
                        hint_box = gr.Markdown(
                            "回答里会附上引用来源，方便核对答案有没有依据。"
                        )

                send_button.click(
                    respond,
                    [message_box, chatbot, scene_dropdown],
                    [chatbot, message_box, meta_box, hint_box],
                )
                message_box.submit(
                    respond,
                    [message_box, chatbot, scene_dropdown],
                    [chatbot, message_box, meta_box, hint_box],
                )
                clear_button.click(clear_chat, None, [chatbot, message_box, meta_box, hint_box])
                sample_dropdown.change(
                    ask_sample,
                    [sample_dropdown, chatbot, scene_dropdown],
                    [chatbot, message_box, meta_box, hint_box],
                )

            with gr.Tab("③ 知识库"):
                gr.Markdown(
                    "把当地分类目录、投放点管理规定、往届误投统计上传到这里，"
                    "点「重建索引」后就能被检索到。支持 `.md` `.txt` `.csv` `.json` `.pdf` 五种格式。"
                )
                file_input = gr.File(label="上传文档", file_count="multiple", type="filepath")
                with gr.Row():
                    upload_button = gr.Button("导入到当前场景")
                    rebuild_button = gr.Button("重建索引", variant="primary")
                upload_status = gr.Markdown("")
                index_status = gr.Markdown("")

                upload_button.click(
                    upload_files, [file_input, scene_dropdown], [upload_status, index_status]
                )
                rebuild_button.click(rebuild, [scene_dropdown], [upload_status, index_status])

            with gr.Tab("④ 效果验证"):
                gr.Markdown(
                    "运行自建评测集，自动产出方案书「测试与验证」章节需要的指标与图表。\n\n"
                    "拆解引导的评测请在命令行运行：`python eval/run_waste_eval.py`"
                )
                with gr.Row():
                    limit_box = gr.Number(value=0, precision=0, label="限制题数（0 = 全部）")
                    eval_button = gr.Button("运行问答评测", variant="primary")
                eval_summary = gr.HTML(render.empty_html("还没有运行评测"))
                eval_table = gr.Dataframe(
                    headers=["题号", "类型", "问题", "是否拒答", "判定正确", "总耗时(ms)"],
                    interactive=False,
                    wrap=True,
                )
                eval_files = gr.Files(label="下载评测产出", interactive=False)
                eval_button.click(
                    run_eval, [limit_box, scene_dropdown], [eval_table, eval_summary, eval_files]
                )

            with gr.Tab("⑤ 方案素材"):
                gr.Markdown(
                    "### 作品介绍页\n\n"
                    "给评委看的独立页面，与原型共用同一个服务："
                    "在当前地址后加 `/landing/` 即可打开，也可以用短地址 `/info`。"
                    "公网演示时把这两个地址发给评委，他们点开就能看。"
                )
                gr.HTML(
                    render.cta_html(
                        [
                            ("打开作品介绍页", "/landing/"),
                            ("打开数据大屏", "/screen/"),
                            ("安装到手机", "/app"),
                            ("生成手机二维码", "/share"),
                        ],
                        "primary,ghost,ghost,ghost",
                    )
                )
                gr.Markdown("")
                gr.Markdown("### 系统架构图\n\n可直接复制到 draw.io 或方案书。")
                gr.Markdown(ARCHITECTURE_MERMAID)
                with gr.Row():
                    scene_button = gr.Button("导出场景定义")
                    config_button = gr.Button("导出配置快照")
                material_box = gr.Code(label="导出结果", language="markdown", lines=22)
                scene_button.click(export_scene, [scene_dropdown], [material_box])
                config_button.click(export_config, None, [material_box])

        scene_dropdown.change(
            on_scene_change,
            [scene_dropdown],
            [status_box, sample_dropdown, scene_intro, mock_scenario, region_dropdown],
        )
        demo.load(
            on_scene_change,
            [scene_dropdown],
            [status_box, sample_dropdown, scene_intro, mock_scenario, region_dropdown],
        )

    return demo


def _qr_data_uri(url: str) -> str:
    """把二维码内嵌成 data URI。

    不走文件、不额外发请求，页面在哪个地址打开，二维码就指向哪个地址，
    因此隧道地址每次变化都不需要重新生成或替换图片。
    """
    try:
        import qrcode
    except ImportError:  # 缺依赖时不影响其它页面
        return ""
    buffer = io.BytesIO()
    qrcode.make(url).save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _share_card(title: str, note: str, url: str) -> str:
    qr = _qr_data_uri(url)
    picture = (
        f'<img class="qr" src="{qr}" alt="{escape(title)}的二维码" width="220" height="220">'
        if qr
        else '<p class="warn">未安装 qrcode，无法生成二维码。执行 pip install qrcode[pil] 后重试。</p>'
    )
    return (
        '<section class="card">'
        f"<h2>{escape(title)}</h2>"
        f"<p class=\"note\">{escape(note)}</p>"
        f"{picture}"
        f'<a class="url" href="{escape(url, quote=True)}">{escape(url)}</a>'
        "</section>"
    )


def share_page_html(base: str) -> str:
    """返回「扫码打开」页。

    base 取自请求本身（Host 头），所以本页在哪个地址被打开，
    展示的链接与二维码就是这个地址，不存在"二维码指向旧隧道"的问题。
    """
    prototype = f"{base}/"
    landing = f"{base}/landing/"
    screen = f"{base}/screen/"
    is_local = "127.0.0.1" in base or "localhost" in base
    banner = (
        '<p class="banner">这是电脑上的本机地址，手机扫码打不开。'
        "请改用公网地址打开本页（双击 <code>公网访问.cmd</code>），二维码会自动换成公网地址。</p>"
        if is_local
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>扫码打开 · 智识固废：垃圾分类视觉识别与投放引导</title>
<style>
  :root {{
    --soil: #3A4032; --sand: #E8DCC7; --ink: #2E2A20;
    --ink-2: #6B5F49; --rule: rgba(110, 90, 60, .24);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 40px 20px 64px;
    background: var(--soil); color: var(--sand);
    font-family: "Noto Serif SC", "Songti SC", Georgia, serif;
    -webkit-font-smoothing: antialiased;
  }}
  header, main {{ max-width: 720px; margin: 0 auto; }}
  h1 {{ font-size: 27px; line-height: 1.4; margin: 0 0 10px; font-weight: 600; }}
  header p {{ margin: 0 0 8px; color: #CFC3AA; font-size: 15px; line-height: 1.8; }}
  .banner {{
    background: rgba(192, 142, 58, .22); border: 1px solid rgba(192, 142, 58, .5);
    border-radius: 14px; padding: 14px 16px; margin: 18px 0 0;
    font-size: 14px; line-height: 1.75; color: #F0E4CE;
  }}
  .banner code {{ background: rgba(0,0,0,.22); border-radius: 5px; padding: 1px 5px; }}
  .cards {{ display: grid; gap: 20px; margin-top: 28px; }}
  .card {{
    background: var(--sand); color: var(--ink);
    border-radius: 22px; padding: 26px 24px 24px;
    box-shadow: 0 16px 40px rgba(0, 0, 0, .28);
    text-align: center;
  }}
  .card h2 {{ font-size: 19px; margin: 0 0 8px; font-weight: 600; }}
  .card .note {{ margin: 0 0 18px; color: var(--ink-2); font-size: 14px; line-height: 1.75; }}
  .qr {{ width: 220px; height: 220px; display: block; margin: 0 auto 16px;
         border-radius: 14px; background: #fff; padding: 10px; }}
  .url {{
    display: inline-block; word-break: break-all;
    color: var(--ink); font-size: 14px; line-height: 1.7;
    background: rgba(58, 64, 50, .08); border: 1px solid var(--rule);
    border-radius: 999px; padding: 9px 18px; text-decoration: none;
  }}
  .warn {{ color: #8A3B12; font-size: 14px; }}
  footer {{ max-width: 720px; margin: 30px auto 0; color: #B9AE95; font-size: 13px; line-height: 1.85; }}
  footer a {{ color: #D9CDB4; }}
</style>
</head>
<body>
<header>
  <h1>扫码在手机上打开</h1>
  <p>本页的链接和二维码按你此刻访问的地址实时生成，换了地址也不用重做二维码。</p>
  {banner}
</header>
<main class="cards">
  {_share_card("原型演示", "拍照识别与投放引导，答辩现场演示用这个。", prototype)}
  {_share_card("作品介绍页", "给评委看的独立页面：问题、方案、实测数据与迭代过程。", landing)}
  {_share_card("数据大屏", "覆盖率、判定准确率与四套口径，一屏看完实测结果。", screen)}
</main>
<footer>
  <p>想装到手机上？打开 <a href="/app">安装引导</a>，安卓可一键安装，iPhone 有分步说明。</p>
  <p>微信内直接扫码可能被拦截，用系统相机或浏览器扫即可。</p>
  <p>识别需要联网：照片要送到云端多模态模型，断网时只会看到一张说明页。</p>
</footer>
</body>
</html>
"""


_APP_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>安装到手机 · 智识固废：垃圾分类视觉识别与投放引导</title>
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="#3A4032">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="垃圾投放引导">
<link rel="icon" type="image/png" sizes="192x192" href="/pwa/icon-192.png">
<link rel="apple-touch-icon" href="/pwa/apple-touch-icon.png">
<style>
  :root {
    --soil: #3A4032; --sand: #E8DCC7; --ink: #2E2A20;
    --ink-2: #6B5F49; --rule: rgba(110, 90, 60, .24);
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 40px 20px 72px;
    background: var(--soil); color: var(--sand);
    font-family: "Noto Serif SC", "Songti SC", Georgia, serif;
    -webkit-font-smoothing: antialiased;
  }
  header, main { max-width: 720px; margin: 0 auto; }
  h1 { font-size: 27px; line-height: 1.4; margin: 0 0 10px; font-weight: 600; }
  header > p { margin: 0; color: #CFC3AA; font-size: 15px; line-height: 1.8; }
  .card {
    background: var(--sand); color: var(--ink);
    border-radius: 22px; padding: 24px; margin-top: 20px;
    box-shadow: 0 16px 40px rgba(0, 0, 0, .28);
  }
  .card h2 { font-size: 19px; margin: 0 0 10px; font-weight: 600; }
  .card p { margin: 0 0 10px; color: var(--ink-2); font-size: 14.5px; line-height: 1.8; }
  .card p:last-child { margin-bottom: 0; }
  .status { display: flex; align-items: flex-start; gap: 12px; }
  .dot { flex: 0 0 12px; width: 12px; height: 12px; border-radius: 50%; margin-top: 7px; }
  .dot.ok { background: #606C38; }
  .dot.warn { background: #C08E3A; }
  .dot.bad { background: #C66B3D; }
  .status strong { display: block; font-size: 16px; margin-bottom: 4px; }
  .status span { color: var(--ink-2); font-size: 14px; line-height: 1.75; }
  .big {
    display: block; width: 100%; margin-top: 18px;
    min-height: 54px; padding: 15px 22px;
    border: none; border-radius: 999px; cursor: pointer;
    background: #3A4032; color: var(--sand);
    font-family: inherit; font-size: 16.5px; font-weight: 600;
    box-shadow: 0 12px 28px rgba(0, 0, 0, .26);
    transition: transform 320ms cubic-bezier(.32,.72,.28,1);
  }
  .big:hover { transform: translateY(-2px); }
  .big:active { transform: translateY(0); }
  .steps { counter-reset: n; list-style: none; padding: 0; margin: 0; }
  .steps li {
    counter-increment: n; position: relative;
    padding: 0 0 14px 38px;
    color: var(--ink-2); font-size: 14.5px; line-height: 1.8;
  }
  .steps li:last-child { padding-bottom: 0; }
  .steps li::before {
    content: counter(n);
    position: absolute; left: 0; top: 2px;
    width: 24px; height: 24px; border-radius: 50%;
    background: rgba(58, 64, 50, .12);
    color: var(--ink); font-size: 13px; line-height: 24px; text-align: center;
  }
  .steps b { color: var(--ink); }
  .tag {
    display: inline-block; margin-left: 8px; padding: 2px 10px;
    border-radius: 999px; background: rgba(96, 108, 56, .22);
    color: #3B4A18; font-size: 12px; font-weight: 600;
  }
  .card.dim { opacity: .62; }
  .qr { width: 190px; height: 190px; display: block; margin: 4px auto 14px;
        border-radius: 14px; background: #fff; padding: 10px; }
  .url {
    display: block; text-align: center; word-break: break-all;
    color: var(--ink); font-size: 13.5px; line-height: 1.7;
    background: rgba(58, 64, 50, .08); border: 1px solid var(--rule);
    border-radius: 999px; padding: 10px 16px; text-decoration: none;
  }
  footer { max-width: 720px; margin: 26px auto 0; color: #B9AE95; font-size: 13px; line-height: 1.9; }
  footer a { color: #D9CDB4; }
  [hidden] { display: none !important; }
</style>
</head>
<body>
<header>
  <h1>安装到手机</h1>
  <p>装完之后桌面会多一个图标，点开是全屏运行，没有浏览器地址栏和标签页。</p>
</header>

<main>
  <section class="card">
    <div class="status">
      <span class="dot warn" id="status-dot"></span>
      <div>
        <strong id="status-title">正在检测…</strong>
        <span id="status-text"></span>
      </div>
    </div>
    <button class="big" id="install-btn" hidden>安装到手机</button>
  </section>

  <section class="card" id="steps-android">
    <h2>安卓手机<span class="tag" id="tag-android" hidden>你的手机</span></h2>
    <ol class="steps">
      <li>用 <b>Chrome</b> 或 <b>Edge</b> 打开本页。微信里打开的不算，点右上角「···」选「在浏览器打开」。</li>
      <li>点上面的「安装到手机」。如果没有这个按钮，点浏览器菜单里的<b>「安装应用」</b>或<b>「添加到主屏幕」</b>。</li>
      <li>确认后回桌面，图标就在那里了。首次打开会有一两秒的白屏，是应用在启动。</li>
    </ol>
  </section>

  <section class="card" id="steps-ios">
    <h2>iPhone / iPad<span class="tag" id="tag-ios" hidden>你的手机</span></h2>
    <ol class="steps">
      <li>必须用 <b>Safari</b> 打开本页。用微信打开的不行。</li>
      <li>点屏幕底部的<b>分享按钮</b>（方框加一个向上的箭头）。</li>
      <li>在列表里选<b>「添加到主屏幕」</b>，右上角点「添加」。</li>
    </ol>
    <p>iOS 不给网页提供一键安装的入口，只能走上面这三步，这是系统的限制。</p>
  </section>

  <section class="card" id="steps-installed" hidden>
    <h2>已经装好了</h2>
    <p>你现在就是在安装后的应用里打开的，桌面图标可以直接用。</p>
    <p>换了一台手机、或者想给评委装一个，把下面的二维码给他们扫一下即可。</p>
  </section>

  <section class="card">
    <h2>扫码装到另一台手机</h2>
    <p>二维码指向你此刻访问的这个地址，隧道地址变了回来重新开本页就行。</p>
    <img class="qr" src="__QR__" alt="当前地址的二维码" width="190" height="190">
    <a class="url" href="__BASE__/">__BASE__/</a>
  </section>
</main>

<footer>
  <p>识别要调用云端多模态模型，所以应用必须联网使用；断网时会显示一张说明页，不会白屏。</p>
  <p>作品介绍页：<a href="/landing/">__BASE__/landing/</a>，短地址 <a href="/info">/info</a>。</p>
</footer>

<script>
(function () {
  var ua = navigator.userAgent;
  var isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.maxTouchPoints > 1 && /Macintosh/.test(ua));
  var isAndroid = /Android/.test(ua);
  var isWeChat = /MicroMessenger/i.test(ua);
  var standalone =
    window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true;
  // 安装与 Service Worker 都要求安全上下文；局域网 IP 属于不安全来源，装不了。
  var secure =
    location.protocol === 'https:' ||
    location.hostname === 'localhost' ||
    location.hostname === '127.0.0.1';

  var dot = document.getElementById('status-dot');
  var title = document.getElementById('status-title');
  var text = document.getElementById('status-text');
  var btn = document.getElementById('install-btn');
  var stepsAndroid = document.getElementById('steps-android');
  var stepsIos = document.getElementById('steps-ios');

  function set(kind, heading, detail) {
    dot.className = 'dot ' + kind;
    title.textContent = heading;
    text.textContent = detail;
  }

  // 只显示当前设备用得上的那套步骤：两套一起摆出来，用户得先猜哪套是自己。
  // 认不出平台（桌面浏览器）时两套都留着。
  stepsAndroid.hidden = true;
  stepsIos.hidden = true;
  if (isIOS) {
    stepsIos.hidden = false;
    document.getElementById('tag-ios').hidden = false;
  } else if (isAndroid) {
    stepsAndroid.hidden = false;
    document.getElementById('tag-android').hidden = false;
  } else {
    stepsAndroid.hidden = false;
    stepsIos.hidden = false;
  }

  if (standalone) {
    set('ok', '已安装', '你正在安装后的应用里使用。');
    document.getElementById('steps-installed').hidden = false;
    stepsAndroid.hidden = true;
    stepsIos.hidden = true;
    return;
  }

  if (!secure) {
    set('bad', '这个地址装不了',
        '安装要求 https 地址。你现在用的是局域网或本机地址，请改用公网地址（双击 公网访问.cmd）打开本页。');
    return;
  }

  if (isWeChat) {
    set('bad', '微信里装不了',
        '点右上角「···」，选「在浏览器打开」，再从浏览器里安装。');
    return;
  }

  if (isIOS) {
    set('warn', '需要手动添加', 'iOS 没有一键安装，按下面的三步用 Safari 添加。');
    return;
  }

  // Android / 桌面版 Chrome、Edge：等系统把安装事件交给我们
  set('warn', '可以先看看下面的步骤', '正在等待浏览器就绪，稍等一秒会出现「安装到手机」。');

  var deferred = null;
  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferred = event;
    set('ok', '这台设备可以直接安装', '点下面的按钮，系统会弹出安装确认。');
    btn.hidden = false;
  });

  btn.addEventListener('click', function () {
    if (!deferred) return;
    btn.disabled = true;
    deferred.prompt();
    deferred.userChoice.then(function () { deferred = null; btn.disabled = false; });
  });

  window.addEventListener('appinstalled', function () {
    set('ok', '安装完成', '回桌面看看，图标应该已经在了。');
    btn.hidden = true;
  });
})();
</script>
</body>
</html>
"""


def app_page_html(base: str) -> str:
    """返回「安装到手机」引导页。

    PWA 的安装入口不能只写在文档里：iOS 没有一键安装的 API，
    安卓要等 beforeinstallprompt，局域网地址根本不满足安装条件。
    这些分支都在页面里判断并当场说清楚，用户不用去猜为什么装不上。
    """
    safe_base = escape(base.rstrip("/"), quote=True)
    return (
        _APP_PAGE.replace("__QR__", _qr_data_uri(safe_base + "/"))
        .replace("__BASE__", safe_base)
    )


def main() -> None:
    """启动服务：一个端口同时提供原型与作品介绍页。

    作品页挂在 /landing，原型挂在站点根。共用一个端口意味着
    内网穿透只需要一条隧道，对外也只需要分享一个链接；
    作品页里指向原型的链接用相对路径 "/"，因此不会因为隧道地址变化而失效。
    """
    import threading
    import webbrowser

    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    settings = get_settings()
    demo = build_demo()

    # 端口被占用时自动顺延，避免"打不开"却看不出原因
    port = _pick_free_port(settings.gradio_server_name, settings.gradio_server_port)
    if port != settings.gradio_server_port:
        print(
            f"[提示] 端口 {settings.gradio_server_port} 已被占用，"
            f"改用 {port}；浏览器会自动打开 http://{settings.gradio_server_name}:{port}"
        )

    landing_dir = settings.project_root.parent / "landing"
    pwa_dir = settings.project_root.parent / "pwa"
    # GSAP 动画库放在 app/static/ 下，从这里挂出去给页面用
    static_dir = settings.project_root / "app" / "static"
    # 数据大屏是独立的静态页面，挂在 /screen 下，跟着原型一起就能打开，
    # 不用再单独起一个服务；手机上通过隧道地址也能看。
    screen_dir = settings.project_root.parent / "大屏"
    api = FastAPI(title=APP_TITLE, docs_url=None, redoc_url=None)

    # ---------- PWA：manifest、Service Worker、图标 ----------
    # sw.js 必须挂在站点根目录，作用域才能覆盖整站；否则只能控制子路径。
    if pwa_dir.exists():
        api.mount("/pwa", StaticFiles(directory=str(pwa_dir)), name="pwa")

        @api.get("/manifest.webmanifest", include_in_schema=False)
        def _manifest() -> FileResponse:  # pragma: no cover - 路由
            return FileResponse(
                pwa_dir / "manifest.webmanifest",
                media_type="application/manifest+json",
            )

        @api.get("/sw.js", include_in_schema=False)
        def _service_worker() -> FileResponse:  # pragma: no cover - 路由
            return FileResponse(
                pwa_dir / "sw.js",
                media_type="application/javascript",
                headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
            )
    else:
        print(f"[提醒] 未找到 PWA 目录：{pwa_dir}，无法安装为应用")

    # GSAP：/static 提供动画库文件
    if static_dir.exists():
        api.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    else:
        print(f"[提醒] 未找到静态资源目录：{static_dir}，页面动效将不可用")

    # 先注册 /landing，再挂载站点根，保证静态路由优先匹配
    if landing_dir.exists():
        api.mount(
            "/landing",
            StaticFiles(directory=str(landing_dir), html=True),
            name="landing",
        )

        @api.get("/landing")
        def _landing_index() -> RedirectResponse:  # pragma: no cover - 路由
            return RedirectResponse(url="/landing/")
    else:
        print(f"[提醒] 未找到作品介绍页目录：{landing_dir}，/landing 将不可用")

    # /info 是 /landing/ 的短别名：口播和手输时短一点，不容易记错。
    @api.get("/info", include_in_schema=False)
    def _info_alias() -> RedirectResponse:  # pragma: no cover - 路由
        return RedirectResponse(url="/landing/")

    # 数据大屏：/screen/ 打开入口页，静态资源（vendor、css、js）同目录提供
    if screen_dir.exists():
        api.mount(
            "/screen",
            StaticFiles(directory=str(screen_dir), html=True),
            name="screen",
        )

        @api.get("/screen")
        def _screen_index() -> RedirectResponse:  # pragma: no cover - 路由
            return RedirectResponse(url="/screen/")
    else:
        print(f"[提醒] 未找到数据大屏目录：{screen_dir}，/screen 将不可用")

    # /share 现场生成二维码：二维码指向"你正在访问的这个地址"，
    # 所以隧道地址变了也不用重新出图，扫码即可。
    @api.get("/share", response_class=HTMLResponse, include_in_schema=False)
    def _share(request: Request) -> HTMLResponse:  # pragma: no cover - 路由
        return HTMLResponse(share_page_html(str(request.base_url).rstrip("/")))

    # /app 是安装引导：安卓一键装、iOS 手动添加、微信与局域网地址为什么装不了，
    # 都在这一页当场判断清楚。
    @api.get("/app", response_class=HTMLResponse, include_in_schema=False)
    def _app(request: Request) -> HTMLResponse:  # pragma: no cover - 路由
        return HTMLResponse(app_page_html(str(request.base_url).rstrip("/")))

    # 方案书与答辩 PPT 的成品文件：手机扫到链接就能直接在浏览器里看 PDF，
    # 不用再传文件。只暴露白名单里的三个文件，不做目录挂载，
    # 免得把源码和中间产物一起发出去了。
    files_root = settings.project_root.parent
    deliverable_files = {
        "report": (
            files_root / "方案书" / "2026AIC-智识固废：垃圾分类视觉识别与投放引导-作品方案.pdf",
            "2026AIC-智识固废：垃圾分类视觉识别与投放引导-作品方案.pdf",
        ),
        "deck": (
            files_root / "答辩PPT" / "2026AIC-答辩PPT.pdf",
            "2026AIC-答辩PPT.pdf",
        ),
        "deck-html": (
            files_root / "答辩PPT-单文件版.html",
            "答辩PPT-单文件版.html",
        ),
    }

    @api.get("/files/{name}", include_in_schema=False)
    def _deliverable(name: str):  # pragma: no cover - 路由
        hit = deliverable_files.get(name)
        if hit is None or not hit[0].exists():
            return RedirectResponse(url="/")
        media = "application/pdf" if hit[0].suffix == ".pdf" else "text/html"
        return FileResponse(hit[0], media_type=media, filename=hit[1])

    api = gr.mount_gradio_app(
        api,
        demo,
        path="/",
        show_api=False,
        show_error=True,
        auth=settings.gradio_auth,
    )

    base = f"http://{settings.gradio_server_name}:{port}"
    print(f"[服务] 原型：  {base}/")
    if landing_dir.exists():
        print(f"[服务] 作品页：{base}/landing/")

    if settings.gradio_inbrowser:
        threading.Timer(2.5, lambda: webbrowser.open(f"{base}/")).start()

    uvicorn.run(
        api,
        host=settings.gradio_server_name,
        port=port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
