"""前端渲染层：按 frontend-design 技能的 Organic 锚点实现。

================================================================
CONTEXT（上下文）
================================================================
目标用户（三类人共用一个界面）：
  · 在校学生：站在宿舍楼 / 教学楼 / 食堂 / 快递点的桶边，
    手里拿着垃圾，只有几秒钟做决定；
  · 宿舍管理员与保洁人员：需要按「桶」的视角看结果，
    关心的是"这一桶里哪些投错了"；
  · 环保社团志愿者：值守时反复被问同样的问题，
    需要能直接照着念的引导。

核心任务：拍一张照片 → 得到「拆成几部分、每部分投哪个桶、投之前做什么」；
标记桶位后 → 再得到「这一桶里哪些投错了」。

应用特点：信息密度高（一张照片 15~20 个部件）、决策时间极短、
容错低（投错要保洁二次分拣）、必须可信（分类口径随城市变化，要写清依据）。

一句话问题陈述：
  站在桶边的人只有几秒钟，但分类规则是有条件、分城市、要拆解的：
  界面必须在几秒内把「拆几部分、每部分去哪、先做什么」讲清楚。

================================================================
ANCHOR（美学锚点）
================================================================
**Organic（有机）**

为什么是它，而不是安全选项：
  垃圾分类的物理终点是自然循环：厨余回到土壤，可回收物回到生产线。
  Organic 的大地色系直接对应这条物质链。而把它用在一个高密度、
  要快速决策的分拣工具上，是一种有意为之的张力：用最"慢"的视觉语言，
  承载最"急"的操作场景。技能本身举的例子就是「Organic trading terminal」
  把有机审美用在看似该用工业风的密集数据工具上。

刻意避开的两件事：
  1. **不用绿色**。几乎所有环保产品都用"环保绿"，这个符号已经失效。
     这里用 ochre / terracotta / clay / moss / sage 五种土色。
  2. **不用奶油白**。锚点明确禁止 #F0-F8 暖纸色。内容面用 sand #E8DCC7，
      页面底用深苔 #3A4032，像一块标本纸摊在土壤上。

Token 对照（严格取自锚点定义）：
  表面  : sage #8B9D83 · clay #B08B6E · terracotta #C66B3D
          ochre #C08E3A · moss #606C38
          浅色面 : sand #E8DCC7 · oat #D4B895        （绝不使用奶油白）
  字体  : 人文衬线，Fraunces（锚点限定）+ 本机 Noto Serif SC
          全站只用衬线，不使用任何无衬线字体
  结构  : 圆角 16~32px，绝不出现直角矩形
  质感  : SVG feTurbulence 颗粒，1~3% 不透明度
  动效  : 300~500ms 缓动；首屏元素带呼吸感

================================================================
DIFFERENTIATOR（签名动作）
================================================================
**地层条（Strata Bar）**
每个识别结果顶部出现一条按类别数量比例分割的有机曲线带，像一段土壤剖面：
段宽严格等于该类别在本次结果中的占比，段与段之间是手绘感的曲线边界而非直线，
切换照片时以 420ms 缓动重新分配宽度。

它是「分类构成」的可视化，也是这个页面的签名：
用户不必读数字就知道"这堆东西里可回收占了大头"。
对着一张有 20 件物品的混投照片，这是最先要传达的信息。

================================================================
CONTENT DISCIPLINE（内容纪律，技能 §2）
================================================================
· 屏幕上每个字符串都是真实信息：识别出的部件名、规则库给出的类别、
  真实的计数与耗时。没有虚构数据。
· 不使用 Unicode 符号充当图标，类别标记是手写的内联 SVG 矢量图标。
· 标准操作使用标准文案（发送 / 清空对话 / 重建索引），不做主题化替换。
· 不使用无人索要的装饰性小标题，不做"AI 腔"的文案。
"""

from __future__ import annotations

from html import escape

# ---------- Organic 锚点的类别色 ----------
# fill: 锚点色本身，用于色块与图标描边
# ink : 同色系压深，保证在 sand #E8DCC7 上达到可读对比度
# soft: 低透明度铺底
CATEGORY_COLORS: dict[str, dict[str, str]] = {
    "recyclable": {  # ochre 赭石
        "fill": "#C08E3A",
        "ink": "#7A5620",
        "soft": "rgba(192, 142, 58, .20)",
        "name": "赭石",
    },
    "hazardous": {  # terracotta 赤陶
        "fill": "#C66B3D",
        "ink": "#8A3F1D",
        "soft": "rgba(198, 107, 61, .20)",
        "name": "赤陶",
    },
    "kitchen": {  # moss 苔绿
        "fill": "#606C38",
        "ink": "#465126",
        "soft": "rgba(96, 108, 56, .20)",
        "name": "苔绿",
    },
    "residual": {  # clay 陶土
        "fill": "#B08B6E",
        "ink": "#6B5038",
        "soft": "rgba(176, 139, 110, .22)",
        "name": "陶土",
    },
    "liquid": {  # sage 鼠尾草
        "fill": "#8B9D83",
        "ink": "#4C5B45",
        "soft": "rgba(139, 157, 131, .22)",
        "name": "鼠尾草",
    },
}

FALLBACK = {
    "fill": "#8B9D83",
    "ink": "#4C5B45",
    "soft": "rgba(139, 157, 131, .22)",
    "name": "未分类",
}

CATEGORY_ORDER = ("recyclable", "hazardous", "kitchen", "residual", "liquid")


def _c(category: str) -> dict[str, str]:
    return CATEGORY_COLORS.get(category, FALLBACK)


# ---------- 手写 SVG 图标（真实图标，不是 Unicode 符号）----------
_ICON_PATHS = {
    "recyclable": (
        '<path d="M20.5 12a8.5 8.5 0 1 1-2.6-6.1"/>'
        '<path d="M20.8 4.6v4.2h-4.2"/>'
    ),
    "hazardous": (
        '<path d="M12 3.6 21.2 19.4H2.8Z"/>'
        '<path d="M12 9.4v4.3"/>'
        '<path d="M12 16.4v.1"/>'
    ),
    "kitchen": (
        '<path d="M20.2 3.8C10.4 3.8 4.6 9.6 4.6 19.4c9.8 0 15.6-5.8 15.6-15.6Z"/>'
        '<path d="M16.4 7.6 7.6 16.4"/>'
    ),
    "residual": (
        '<path d="M4.6 6.8h14.8"/>'
        '<path d="M9.4 6.8V4.9h5.2v1.9"/>'
        '<path d="M6.6 6.8 8 20.2h8L17.4 6.8"/>'
    ),
    "liquid": '<path d="M12 3.4s5.8 6.6 5.8 10.6a5.8 5.8 0 0 1-11.6 0c0-4 5.8-10.6 5.8-10.6Z"/>',
}


def icon_svg(category: str, size: int = 19) -> str:
    """真实矢量图标：描边色随类别，线条末端圆角，贴合 Organic 的手感。"""
    color = _c(category)["ink"]
    body = _ICON_PATHS.get(category, _ICON_PATHS["residual"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.7" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


# ---------- 颗粒质感：SVG feTurbulence，1~3% ----------
# 注意 data URI 里的 # 必须转义成 %23
_GRAIN = (
    "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' "
    "width='160' height='160'%3E%3Cfilter id='g'%3E%3CfeTurbulence "
    "type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E"
    '%3C/filter%3E%3Crect width=%22160%22 height=%22160%22 filter=%22url(%23g)%22/%3E%3C/svg%3E")'
)


PAGE_CSS = f"""
/* ============================================================
   Organic 设计令牌
   ============================================================ */
:root {{
    --soil: #3A4032;      /* 页面底：深苔土壤 */
    --soil-2: #454B3B;
    --sand: #E8DCC7;      /* 内容面：锚点允许的浅色面 */
    --oat: #D4B895;       /* 次级面 */
    --clay: #B08B6E;
    --ink: #2E2A20;       /* 正文：深土色，非纯黑 */
    --ink-2: #6B5F49;
    --ink-3: #6B5D45;     /* 三级文字：在沙面上 4.73:1 */
    --on-page: #D2C7AE;   /* 页面底上的正文：深苔底必须配浅字 */
    --moss: #606C38;
    --sage: #8B9D83;
    --ochre: #C08E3A;
    --terracotta: #C66B3D;
    --rule: rgba(110, 90, 60, .24);
    --radius-lg: 28px;
    --radius: 22px;
    --radius-sm: 16px;
    --ease: cubic-bezier(.32, .72, .28, 1);
    --font-display: "Fraunces", "Noto Serif SC", Georgia, "宋体", serif;
    --font-body: "Noto Serif SC", "Fraunces", Georgia, "宋体", serif;
    --grain: {_GRAIN};
}}

/* ============================================================
   全局：全站衬线 + 沙面 + 颗粒
   ============================================================ */
.gradio-container, .gradio-container * {{
    font-family: var(--font-body) !important;
    -webkit-font-smoothing: antialiased;
}}
/* gradio-app 必须一起上色。实测它在浅色模式下自带白底、深色模式下是近黑底
   （#0F0E0D），而 .gradio-container 是居中的 1160px，
   于是 1440px 以上的屏幕两侧各露出 140px 的异色竖条，看起来像页面被裁了。 */
html, body, gradio-app, .gradio-container, .main, .app {{
    background: var(--soil) !important;
    color: var(--on-page);
}}
/* 手机端最重要的一条：容器必须收缩到视口宽度。
   原来只写了 max-width，容器作为 flex 子项不会收缩，实测 390px 视口被撑到 782px，
   页面出现两倍宽的横向滚动。这里补上 width / min-width 才能压住。 */
html, body, gradio-app, .main, main.fillable {{
    min-width: 0 !important;
    max-width: 100% !important;
}}
.gradio-container {{
    width: 100% !important;
    max-width: min(1160px, 100%) !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
    margin: 0 auto !important;
}}
.gradio-container * {{ min-width: 0; }}

/* 颗粒层：铺在页面底上，1~3% */
body::before {{
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background-image: var(--grain); opacity: .030; mix-blend-mode: overlay;
}}
.gradio-container > * {{ position: relative; z-index: 1; }}

/* Gradio 自带容器一律去壳，交给我们的沙面卡片 */
.gradio-container .block,
.gradio-container .form,
.gradio-container .panel {{
    border: none !important; box-shadow: none !important; background: transparent !important;
}}

/* ============================================================
   Gradio 原生内容组件必须自带给沙面
   它们不会被自定义面板包住。若只把它们设成透明，
   主题的深色文字会直接沉进深苔色页面底（实测对比度 1.33:1）。
   ============================================================ */
/* 只给"原生 Markdown"加沙面。
   注意：Gradio 给 gr.HTML 也加了 .prose 类，若不排除，
   自定义面板（.hero / .panel / .list / .empty 等）会被再包一层，
   造成双层内边距，实测把 hero 的文字栏从 262px 挤到 222px。 */
.gradio-container .prose:not(:has(> .hero, > .panel, > .list, > .empty,
                                  > .statusbar, > .metrics, > .vcard)) {{
    background: var(--sand) !important;
    color: var(--ink) !important;
    border-radius: var(--radius-sm) !important;
    padding: 18px 22px !important;
    margin: 0 0 12px 0 !important;
}}
.gradio-container .prose a {{ color: var(--moss) !important; text-decoration: underline; }}
.gradio-container .prose strong {{ color: var(--ink) !important; }}
.gradio-container .prose code {{
    background: rgba(58, 64, 50, 0.10) !important;
    color: var(--ink) !important;
    border-radius: 6px;
    /* 行内代码块左右原本各只有 5px，首尾字符贴着底色边缘，
       换字体或缩放时容易看起来缺一角。左右各加到 8px。 */
    padding: 2px 8px !important;
}}
/* 引用块两侧原本都没有安全边距。
   右侧：980px 宽度附近末行句号只剩 5px 余量，字体度量稍有差别就被裁掉。
   左侧：Gradio 默认 padding-left 只有 8px，灰色边线距首字仅 12px，
   换字体或换缩放时首字会贴上边线，看起来像被裁掉一半。
   两侧都留足余量，边线不再压字。 */
.gradio-container .prose blockquote {{
    padding-left: 18px !important;
    padding-right: 16px !important;
}}
.gradio-container .prose blockquote p {{
    overflow-wrap: anywhere;
}}

/* 表格（gr.Dataframe）：单元格与表头都要有底色与墨色 */
.gradio-container .table-wrap,
.gradio-container table {{
    background: var(--sand) !important;
    color: var(--ink) !important;
    border-radius: var(--radius-sm) !important;
}}
.gradio-container table th,
.gradio-container table td {{
    background: var(--sand) !important;
    color: var(--ink) !important;
    border-color: var(--rule) !important;
    /* 表头与单元格的首字原本距左边界只有 8px，字体度量或缩放一变就贴边，
       看起来像被裁掉一半。左右各留一点余量。 */
    padding-left: 14px !important;
    padding-right: 12px !important;
}}

/* 文件列表（gr.File / gr.Files） */
.gradio-container .file-preview,
.gradio-container .file-preview *,
.gradio-container .file-name,
.gradio-container .file-size {{
    background: var(--sand) !important;
    color: var(--ink) !important;
}}
.gradio-container .file-preview {{
    border-radius: var(--radius-sm) !important; padding: 8px 10px !important;
}}

/* 代码块（gr.Code，CodeMirror） */
.gradio-container pre,
.gradio-container .cm-editor,
.gradio-container .cm-scroller,
.gradio-container .cm-content,
.gradio-container .cm-gutters {{
    background: var(--sand) !important;
    color: var(--ink) !important;
}}
.gradio-container .cm-editor {{ border-radius: var(--radius-sm) !important; }}

/* 对话气泡（gr.Chatbot） */
.gradio-container .message,
.gradio-container .message p,
.gradio-container .message li,
.gradio-container .bubble {{ color: var(--ink) !important; }}
.gradio-container .message {{
    background: var(--sand) !important;
    border-radius: var(--radius-sm) !important;
}}
.gradio-container .message.user {{ background: rgba(96, 108, 56, 0.22) !important; }}

/* 下拉、上传区、数字输入等其余原生控件，一并给沙面 */
.gradio-container .dropdown .wrap,
.gradio-container .dropdown .wrap-inner,
.gradio-container .secondary-wrap,
.gradio-container .upload-container,
.gradio-container .file-upload,
.gradio-container .image-container,
.gradio-container .wrap.default,
.gradio-container .container > .wrap {{
    background: var(--sand) !important;
    color: var(--ink) !important;
}}
.gradio-container .dropdown .wrap,
.gradio-container .upload-container,
.gradio-container .file-upload,
.gradio-container .image-container {{ border-radius: var(--radius-sm) !important; }}

/* 兜底：任何仍落在页面底上的 Gradio 原生文字，用页面级浅色 */
.gradio-container .block > .label-wrap,
.gradio-container .block > .label-wrap span,
.gradio-container .block > label,
.gradio-container .block > label span {{ color: var(--on-page) !important; }}

/* 标签文字原本正好落在 block 内容区的左边界上（余量 0），
   字体度量或页面缩放稍有差别，行首字就会贴边甚至被裁掉一条。
   统一右移 3px 留出安全余量。 */
.gradio-container .block > label,
.gradio-container .block > .label-wrap {{ padding-left: 3px !important; }}

/* 正文（Markdown）容器统一加大左侧余量，并且不再横向裁切。
   实测：同一份代码在不同机器上，行首字被吞掉的位置和数量都不一样
   （有的整字消失、有的只缺一半），根源是字体度量差异让首字落在了
   容器的裁切边界之外。这里两手都上：左内边距加到 26px 拉开距离，
   同时取消横向裁切，即使仍有偏差也只会溢出让位，不会被切掉。 */
.gradio-container .prose {{
    padding-left: 26px !important;
    padding-right: 18px !important;
    overflow: visible !important;
}}

/* 上面那条只管住了 .prose 自己，实测还不够：
   行首字仍被吞掉约一个半字（≈14–22px），正好等于段落左内边距的宽度，
   说明真正下刀的是外层容器，裁切边界落在了内容区。
   这里把正文所在的整条祖先链都改成不裁切，并给段落自身再加一层左内边距，
   两道都上，行首字无论落在哪一层边界内都不会被切。 */
.gradio-container .block:has(.prose),
.gradio-container .block:has(.prose) > *,
.gradio-container .prose *,
.gradio-container .tabitem,
.gradio-container .tabitem > * {{
    overflow: visible !important;
}}
.gradio-container .prose p,
.gradio-container .prose li,
.gradio-container .prose > h1,
.gradio-container .prose > h2,
.gradio-container .prose > h3,
.gradio-container .prose > h4 {{
    /* 上一版加到 10px 后，被截的比例明显变小，说明切点位置是固定的，
       加内边距就能把行首字推出切点之外。这里继续加到 26px，
       并配上 .prose 自身的 26px，合计约 52px 的左侧安全区。 */
    padding-left: 26px !important;
}}

/* ============================================================
   首屏：沙面标本板 + 呼吸动效
   ============================================================ */
.hero {{
    position: relative; overflow: hidden;
    isolation: isolate;              /* 建立层叠上下文，让装饰层与文字层可控 */
    background: var(--sand);
    border-radius: var(--radius-lg);
    padding: 34px 38px 32px 40px;
    margin-bottom: 20px;
    box-shadow: 0 18px 44px rgba(0, 0, 0, .30);
}}
.hero::before {{                 /* 颗粒 */
    content: ""; position: absolute; inset: 0; pointer-events: none;
    z-index: 0;
    background-image: var(--grain); opacity: .022;
}}
/* 呼吸光斑：必须待在文字下层。
   实测它原本覆盖了标题左上角，把沙面从 #E8DCC7 压暗到 #CFC6AE，
   标题头一两个字就落在阴影里，看起来"被挡住"。 */
.hero::after {{
    content: ""; position: absolute; right: -50px; bottom: -50px; width: 190px; height: 190px;
    border-radius: 46% 54% 52% 48% / 50% 46% 54% 50%;
    background: radial-gradient(circle at 62% 62%, rgba(96,108,56,.22), rgba(96,108,56,0));
    animation: breathe 7.5s var(--ease) infinite;
    pointer-events: none;
    z-index: 0;
}}
@keyframes breathe {{
    0%, 100% {{ transform: scale(1); opacity: .55; }}
    50%      {{ transform: scale(1.07); opacity: .82; }}
}}
@media (prefers-reduced-motion: reduce) {{
    .hero::after {{ animation: none; }}
    * {{ transition-duration: .01ms !important; }}
}}

.hero h1 {{
    position: relative; z-index: 2; margin: 0 0 12px 0;
    font-family: var(--font-display) !important;
    font-size: 30px; font-weight: 600; letter-spacing: -.3px;
    line-height: 1.35; color: var(--ink);
}}
.hero p {{
    position: relative; z-index: 2; margin: 0; max-width: 62ch;
    font-size: 15.5px; line-height: 1.75; color: var(--ink-2);
}}
.hero .tags {{ position: relative; z-index: 2; margin-top: 20px; display: flex; flex-wrap: wrap; gap: 8px; }}
.hero .tags span {{
    background: rgba(58, 64, 50, .07);
    border: 1px solid var(--rule);
    color: var(--ink-2);
    border-radius: 999px; padding: 5px 15px;
    font-size: 12.5px; letter-spacing: .1px;
}}

/* 首屏行动区。
   实测原来的「作品介绍页」入口只藏在「⑤ 方案素材」页签里的一条行内链接，
   实测框高 20px（低于 44px 可点尺寸），手机上既找不到也点不准；
   这里把入口提到首屏，并做成真正的按钮。
   配色用 --soil 配 --sand：对比度 8.1:1，高于 --moss 的 4.3:1。 */
.cta-row {{
    position: relative; z-index: 2;
    margin-top: 22px; display: flex; flex-wrap: wrap; gap: 10px;
}}
.cta {{
    display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    min-height: 44px; padding: 11px 22px;
    border-radius: 999px;
    font-size: 14.5px; font-weight: 600; letter-spacing: .1px;
    text-decoration: none !important;
    transition: transform 320ms var(--ease), background 320ms var(--ease),
                box-shadow 320ms var(--ease);
}}
.cta.primary {{
    /* 这里必须写死深苔绿，不能用 var(--soil)：
       浅色模式下 --soil 会翻成燕麦色 #D4B895，与沙面字的对比度只剩 1.44:1，
       按钮文字基本看不见。写死 #3A4032 后两套模式都是 8.14:1。 */
    background: #3A4032; color: var(--sand) !important;
    box-shadow: 0 10px 26px rgba(0, 0, 0, .26);
}}
.cta.primary:hover {{ transform: translateY(-2px); box-shadow: 0 16px 34px rgba(0, 0, 0, .30); }}
.cta.ghost {{
    background: rgba(58, 64, 50, .08);
    border: 1px solid var(--rule);
    color: var(--ink) !important;
}}
.cta.ghost:hover {{ background: rgba(58, 64, 50, .15); }}
/* 首屏 hero 的背景两套模式下都是 --sand，所以行动区不需要另开一套配色。 */

/* ============================================================
   状态条
   ============================================================ */
.statusbar {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 2px 0 6px 0; }}
.pill {{
    display: inline-flex; align-items: center;
    border-radius: 999px; padding: 6px 15px;
    font-size: 12.5px; letter-spacing: .1px;
    background: rgba(232, 220, 199, .14);
    color: var(--sand);
}}
.pill.ok   {{ background: rgba(96, 108, 56, .42); color: #DDE6C8; }}
.pill.warn {{ background: rgba(192, 142, 58, .44); color: var(--sand); }}
.pill.bad  {{ background: rgba(198, 107, 61, .46); color: var(--sand); }}
.pill.info {{ background: rgba(139, 157, 131, .34); color: #E1E9DC; }}
.pill.neutral {{ background: rgba(232, 220, 199, .14); color: #CFC3AA; }}

/* ============================================================
   沙面卡片通用
   ============================================================ */
.panel {{
    position: relative; background: var(--sand);
    border-radius: var(--radius); padding: 22px 26px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, .24);
    margin-bottom: 16px; overflow: hidden;
}}
.panel::before {{
    content: ""; position: absolute; inset: 0; pointer-events: none;
    background-image: var(--grain); opacity: .02;
}}

/* ============================================================
   地层条：签名动作
   ============================================================ */
.strata-wrap {{ margin-bottom: 18px; }}
.strata {{
    display: flex; gap: 4px; height: 60px; align-items: stretch;
    padding: 0; background: transparent;
}}
.strata span {{
    min-width: 10px;
    transition: flex-grow 420ms var(--ease), background 420ms var(--ease);
    box-shadow: inset 0 -6px 12px rgba(0, 0, 0, .10);
}}
/* 每段用不对称圆角，形成手绘感的有机边界，绝不出现直角 */
.strata span:nth-child(4n+1) {{ border-radius: 26px 10px 22px 12px / 10px 26px 12px 22px; }}
.strata span:nth-child(4n+2) {{ border-radius: 12px 24px 10px 26px / 24px 12px 26px 10px; }}
.strata span:nth-child(4n+3) {{ border-radius: 20px 14px 26px 10px / 14px 22px 10px 26px; }}
.strata span:nth-child(4n+4) {{ border-radius: 10px 26px 14px 20px / 26px 10px 22px 14px; }}

.strata-legend {{
    display: flex; flex-wrap: wrap; gap: 16px 24px; margin-top: 14px;
}}
.strata-legend div {{ display: flex; align-items: baseline; gap: 7px; }}
.strata-legend .dot {{
    width: 11px; height: 11px; flex: 0 0 11px;
    border-radius: 54% 46% 48% 52% / 46% 52% 48% 54%;
}}
.strata-legend b {{
    font-family: var(--font-display) !important;
    font-size: 17px; font-weight: 600; color: var(--ink);
    font-variant-numeric: tabular-nums;
}}
.strata-legend em {{
    font-style: normal; font-size: 13px; color: var(--ink-2);
}}

/* ============================================================
   结论头部
   ============================================================ */
.gd-head h2 {{
    position: relative; margin: 0 0 8px 0;
    font-family: var(--font-display) !important;
    font-size: 23px; font-weight: 600; letter-spacing: -.3px; line-height: 1.4;
    color: var(--ink);
}}
.gd-head .why {{ position: relative; margin: 0; font-size: 14.5px; line-height: 1.7; color: var(--ink-2); }}
.gd-badge {{
    display: inline-block; vertical-align: 4px; margin-right: 11px;
    background: var(--moss); color: var(--sand);
    border-radius: 999px; padding: 3px 13px;
    font-size: 11.5px; letter-spacing: .4px;
}}

/* ============================================================
   部件分组列表
   ============================================================ */
.group-header {{
    display: flex; align-items: center; gap: 12px;
    font-size: 13px; letter-spacing: .6px; color: var(--ink-2);
    margin: 0 0 12px 4px;
}}
.group-header::after {{
    content: ""; flex: 1; height: 1px; background: var(--rule);
}}

.list {{ position: relative; background: var(--sand); border-radius: var(--radius); overflow: hidden; box-shadow: 0 12px 30px rgba(0,0,0,.24); }}
.list::before {{ content: ""; position: absolute; inset: 0; pointer-events: none; background-image: var(--grain); opacity: .02; }}

.row {{
    position: relative; display: flex; gap: 15px;
    padding: 17px 24px;
    border-bottom: 1px solid var(--rule);
    transition: background 420ms var(--ease);
}}
.row:last-child {{ border-bottom: none; }}
.row:hover {{ background: rgba(58, 64, 50, .035); }}

/* 土块：不对称圆角的有机形状，颜色即类别 */
.row-blob {{
    flex: 0 0 42px; width: 42px; height: 42px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 58% 42% 47% 53% / 45% 55% 45% 55%;
}}
.row-main {{ flex: 1 1 auto; min-width: 0; }}
.row-title {{
    font-family: var(--font-display) !important;
    font-size: 16.5px; font-weight: 600; line-height: 1.45;
    color: var(--ink); letter-spacing: -.1px;
}}
.row-count {{
    font-family: var(--font-display) !important;
    font-size: 13px; color: var(--ink-2); margin-left: 7px;
    font-variant-numeric: tabular-nums;
}}
.row-sub {{ margin-top: 5px; font-size: 13.5px; line-height: 1.65; color: var(--ink-2); }}
.row-trail {{ flex: 0 0 auto; padding-top: 3px; }}
.badge {{
    display: inline-block; white-space: nowrap;
    border-radius: 999px; padding: 5px 14px;
    font-size: 12.5px; letter-spacing: .1px;
}}

.note-block {{
    margin-top: 10px; border-radius: var(--radius-sm);
    padding: 10px 14px; font-size: 13px; line-height: 1.65;
}}
.note-block .k {{
    display: block; margin-bottom: 2px;
    font-size: 11.5px; letter-spacing: .6px;
}}
.note-warn   {{ background: rgba(192, 142, 58, .16); color: #6B4A18; }}
.note-danger {{ background: rgba(198, 107, 61, .15); color: #7A3818; }}
.note-info   {{ background: rgba(139, 157, 131, .20); color: #3F4E39; }}

/* ============================================================
   混投 / 优先级
   ============================================================ */
.flag {{ position: relative; overflow: hidden; }}
.flag::after {{
    content: ""; position: absolute; left: 0; top: 22px; bottom: 22px; width: 5px;
    border-radius: 0 999px 999px 0;
}}
.flag-red {{ border-left: none; }}
.flag-red::after {{ background: var(--terracotta); }}
.flag-amber::after {{ background: var(--ochre); }}
.flag h3 {{
    position: relative; margin: 0 0 14px 0;
    font-family: var(--font-display) !important;
    font-size: 17px; font-weight: 600; letter-spacing: -.1px;
}}
.flag-red h3 {{ color: #7A3818; }}
.flag-amber h3 {{ color: #6B4A18; }}
.flag .mrow {{
    position: relative; display: flex; justify-content: space-between; align-items: center;
    gap: 14px; padding: 10px 0; border-bottom: 1px solid var(--rule);
    font-size: 14px; color: var(--ink);
}}
.flag .mrow:last-of-type {{ border-bottom: none; }}
.flag .tip {{ position: relative; margin: 14px 0 0 0; font-size: 12.5px; line-height: 1.65; color: var(--ink-2); }}
.flag ol {{ position: relative; margin: 0; padding-left: 22px; }}
.flag li {{ font-size: 14px; line-height: 1.7; color: var(--ink); margin-bottom: 11px; }}
.flag li:last-child {{ margin-bottom: 0; }}
.flag li .why {{ color: var(--ink-3); font-size: 12.5px; }}
.flag li .step {{ font-family: var(--font-display) !important; font-weight: 600; }}

/* ============================================================
   折叠区
   ============================================================ */
details.fold {{
    position: relative; background: var(--sand);
    border-radius: var(--radius-sm); padding: 16px 24px;
    margin-bottom: 12px; box-shadow: 0 8px 22px rgba(0, 0, 0, .20);
}}
details.fold > summary {{
    cursor: pointer; list-style: none;
    font-size: 14.5px; color: var(--moss); font-weight: 600;
    display: flex; align-items: center; gap: 10px;
}}
details.fold > summary::-webkit-details-marker {{ display: none; }}
details.fold > summary::after {{
    content: ""; flex: 1; height: 1px; background: var(--rule);
}}
details.fold > summary .chev {{
    display: inline-block; width: 9px; height: 9px;
    border-right: 1.8px solid var(--moss); border-bottom: 1.8px solid var(--moss);
    transform: rotate(45deg); transition: transform 360ms var(--ease);
    margin-top: -3px;
}}
details.fold[open] > summary .chev {{ transform: rotate(-135deg); margin-top: 3px; }}
details.fold ol, details.fold ul {{ margin: 16px 0 2px 0; padding-left: 22px; }}
details.fold li {{ font-size: 13.5px; line-height: 1.7; color: var(--ink-2); margin-bottom: 7px; }}

/* ============================================================
   识别结果 / 空态 / 指标
   ============================================================ */
.vcard-label {{
    position: relative; margin: 0 0 10px 0;
    font-size: 11.5px; letter-spacing: .7px; color: var(--ink-3);
}}
.vsummary {{
    position: relative; margin: 0;
    font-family: var(--font-display) !important;
    font-size: 17px; line-height: 1.6; color: var(--ink);
}}
.vchips {{ position: relative; margin-top: 16px; display: flex; flex-wrap: wrap; gap: 7px; }}
.vchip {{
    background: rgba(58, 64, 50, .07); border: 1px solid var(--rule);
    border-radius: 999px; padding: 5px 13px;
    font-size: 12.5px; color: var(--ink);
}}
.vchip i {{ font-style: normal; color: var(--ink-3); font-size: 11.5px; margin-left: 4px; }}

.empty {{
    position: relative; text-align: center;
    background: var(--sand); border-radius: var(--radius);
    padding: 56px 28px; font-size: 14.5px; line-height: 1.8; color: var(--ink-3);
    box-shadow: 0 12px 30px rgba(0, 0, 0, .24);
}}

.metrics {{ display: flex; flex-wrap: wrap; gap: 14px; }}
.metric {{
    flex: 1 1 140px; min-width: 140px;
    background: var(--sand); border-radius: var(--radius-sm);
    padding: 18px 20px; box-shadow: 0 10px 26px rgba(0, 0, 0, .22);
}}
.metric b {{
    display: block; font-family: var(--font-display) !important;
    font-size: 26px; font-weight: 600; line-height: 1.15;
    letter-spacing: -.5px; font-variant-numeric: tabular-nums;
}}
.metric span {{ display: block; margin-top: 5px; font-size: 12.5px; line-height: 1.5; color: var(--ink-2); }}

.footnote {{
    position: relative; margin-top: 18px; padding: 14px 18px;
    background: rgba(232, 220, 199, .12);
    border-radius: var(--radius-sm);
    font-size: 12.5px; line-height: 1.7; color: #C9BDA4;
}}

/* ============================================================
   Gradio 原生控件
   ============================================================ */
.gradio-container button.primary, .gradio-container .gr-button-primary {{
    background: var(--moss) !important; color: var(--sand) !important;
    border: none !important; border-radius: 999px !important;
    font-weight: 600 !important; letter-spacing: .2px !important;
    transition: background 320ms var(--ease), transform 320ms var(--ease) !important;
}}
.gradio-container button.primary:hover, .gradio-container .gr-button-primary:hover {{
    background: #6E7B42 !important; transform: translateY(-1px);
}}
.gradio-container button.secondary, .gradio-container .gr-button-secondary {{
    background: rgba(232, 220, 199, .18) !important; color: var(--sand) !important;
    border: none !important; border-radius: 999px !important;
}}
.gradio-container input, .gradio-container textarea, .gradio-container select {{
    background: var(--sand) !important; color: var(--ink) !important;
    border: 1px solid var(--rule) !important; border-radius: var(--radius-sm) !important;
}}
.gradio-container label, .gradio-container .label-wrap span, .gradio-container span[data-testid] {{
    color: #C9BDA4 !important;
}}
.gradio-container .tabs > .tab-nav {{
    border-bottom: 1px solid rgba(232, 220, 199, .22) !important; gap: 6px;
}}
.gradio-container .tabs > .tab-nav button {{
    color: #B7AB92 !important; border: none !important;
    border-radius: 999px 999px 0 0 !important;
    font-size: 14px !important; letter-spacing: .2px !important;
    transition: color 320ms var(--ease) !important;
}}
.gradio-container .tabs > .tab-nav button.selected {{
    color: var(--sand) !important; background: rgba(232, 220, 199, .10) !important;
}}
.gradio-container .file-preview, .gradio-container .image-container {{
    border-radius: var(--radius-sm) !important; overflow: hidden;
}}

/* 隐去 Gradio 自带角标与设置入口：
   参赛作品不应出现第三方平台标识；设置面板里的主题开关也会与本页
   跟随系统的配色冲突。 */
.gradio-container .built-with,
.gradio-container button.settings,
.gradio-container .settings,
.gradio-container footer .built-with,
.gradio-container a[href*="gradio.app"] {{
    display: none !important;
}}

/* ============================================================
   浅色方案：跟随系统
   两种模式保持同一关系（页面底比内容面深一档），
   只在地层色域内切换，不出现奶油白、冷灰、纯黑纯白。
   ============================================================ */
@media (prefers-color-scheme: light) {{
    :root {{
        --soil: #D4B895;      /* 页面底：燕麦 */
        --soil-2: #C6A883;
        --sand: #E8DCC7;      /* 内容面：沙 */
        --ink: #2E2A20;       /* 深土色 */
        --ink-2: #63563F;
        --ink-3: #6B5D45;     /* 三级文字：沙面在两套模式下相同，故同值 */
        --on-page: #3B3226;   /* 页面底（燕麦）上的正文用深土色 */
        --rule: rgba(90, 72, 46, .30);
    }}
    .gradio-container,
    .gradio-container .block,
    .gradio-container .form,
    .gradio-container .panel {{
        background: transparent !important;
    }}
    .footnote {{ color: #4A4030; background: rgba(58, 64, 50, .10); }}
    .pill {{ background: rgba(58, 64, 50, .16); color: #3B3226; }}
    .pill.ok   {{ background: rgba(96, 108, 56, .30); color: #2F3A16; }}
    .pill.warn {{ background: rgba(192, 142, 58, .32); color: #5A3E0E; }}
    .pill.bad  {{ background: rgba(198, 107, 61, .30); color: #6B2E12; }}
    .pill.info {{ background: rgba(139, 157, 131, .34); color: #2F3B29; }}
    .pill.neutral {{ background: rgba(58, 64, 50, .16); color: #3B3226; }}
    .gradio-container label,
    .gradio-container .label-wrap span,
    .gradio-container span[data-testid] {{ color: #4A4030 !important; }}
    .gradio-container .tabs > .tab-nav button {{ color: #4A4030 !important; }}
    .gradio-container .tabs > .tab-nav button.selected {{
        color: #2E2A20 !important; background: rgba(58, 64, 50, .12) !important;
    }}
    .gradio-container button.secondary,
    .gradio-container .gr-button-secondary {{
        background: rgba(58, 64, 50, .14) !important; color: #2E2A20 !important;
    }}
    .gradio-container input,
    .gradio-container textarea,
    .gradio-container select {{ color: var(--ink) !important; }}
    body::before {{ mix-blend-mode: multiply; opacity: .022; }}
}}

/* ============================================================
   手机端（≤768px）
   实测问题：375px 视口下页面被撑到 782px；6 个标签页横排溢出视口；
   部件行的右侧类别胶囊把中间文字挤成窄缝；点击区域普遍只有 32px。
   ============================================================ */
@media (max-width: 768px) {{
    /* 间距收紧 */
    .hero {{ padding: 24px 20px 22px 22px; border-radius: 20px; }}
    .hero h1 {{ font-size: 24px; line-height: 1.36; letter-spacing: -.2px; }}
    .hero p {{ font-size: 14.5px; }}
    .hero .tags {{ gap: 6px; margin-top: 14px; }}
    .hero .tags span {{ padding: 4px 11px; font-size: 12.5px; }}

    .panel {{ padding: 16px; border-radius: 18px; }}
    .gd-head h2 {{ font-size: 19px; }}
    .gd-head .why {{ font-size: 13.5px; }}

    /* 状态胶囊：字号抬高、内边距收紧，避免占满一屏 */
    .statusbar {{ gap: 6px; }}
    .pill {{ font-size: 13.5px; padding: 6px 12px; }}
    .hero .tags span {{ font-size: 13.5px; }}

    /* 部件行改为两行结构：类别胶囊独占一行放最上面，
       下面是图标 + 文字。原来胶囊在右侧会把文字挤成一条窄缝。 */
    .row {{ flex-wrap: wrap; padding: 14px 16px; gap: 10px; }}
    .row-blob {{ flex: 0 0 34px; width: 34px; height: 34px; }}
    .row-main {{ flex: 1 1 60%; min-width: 0; }}
    .row-trail {{ order: -1; flex: 0 0 100%; padding-top: 0; }}
    .row-title {{ font-size: 15.5px; }}
    .row-sub {{ font-size: 13px; }}
    .badge {{ font-size: 12.5px; padding: 4px 11px; }}
    .note-block {{ font-size: 12.5px; padding: 9px 12px; }}

    /* 指标行：手机上两列 */
    .gd-stats {{ padding: 2px 0; }}
    .stat {{ flex: 1 1 44%; min-width: 44%; padding: 12px 6px; }}
    .stat b {{ font-size: 20px; }}
    .stat span {{ font-size: 11.5px; }}

    /* 地层条 */
    .strata {{ height: 46px; gap: 3px; }}
    .strata-legend {{ gap: 10px 16px; }}
    .strata-legend b {{ font-size: 15px; }}
    .strata-legend em {{ font-size: 12px; }}

    /* 提示块与折叠区 */
    .flag .mrow {{ flex-wrap: wrap; gap: 6px; font-size: 13.5px; }}
    .flag h3 {{ font-size: 15.5px; }}
    .flag li, .priority li {{ font-size: 13.5px; line-height: 1.7; }}
    details.fold {{ padding: 13px 16px; }}
    details.fold > summary {{ font-size: 14px; }}
    details.fold li {{ font-size: 13px; }}

    .metric {{ flex: 1 1 44%; min-width: 44%; padding: 14px; }}
    .metric b {{ font-size: 22px; }}
    .metric span {{ font-size: 12px; }}

    .footnote {{ padding: 11px 13px; font-size: 13px; }}
    .vsummary {{ font-size: 15.5px; }}
    .vchip {{ font-size: 12.5px; padding: 4px 10px; }}

    /* 原生组件内边距与字号 */
    .gradio-container .prose:not(:has(> .hero, > .panel, > .list, > .empty,
                                      > .statusbar, > .metrics, > .vcard)) {{
        padding: 14px 16px !important;
    }}
    .gradio-container table th,
    .gradio-container table td {{ font-size: 13px; padding: 8px !important; }}

    /* 标签页：单行横向滑动，不换行。
       注意真实结构是 .tabs > .tab-wrapper > .tab-container > button，
       .tab-nav 是 Gradio 4 的类名，在 5.x 不生效。

       早先用的是「换行」方案，实测有副作用：分页条占两行之后，
       下面的内容面板仍按一行的高度定位，面板会盖住第二行的页签，
       375px 宽度下 ④⑤ 直接点不开。改成不换行 + 横向滑动更稳。 */
    .gradio-container .tabs > .tab-wrapper {{
        display: block !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        overflow-y: visible !important;
    }}
    .gradio-container .tabs .tab-container:not(.visually-hidden) {{
        /* 容器原本固定 32px 且 overflow:hidden，按钮抬到 44px 后底部会被裁掉。
           实测裁掉 12px，标签文字下半部分消失。 */
        height: auto !important;
        min-height: 44px !important;
        flex-wrap: nowrap !important;
        gap: 6px !important;
        overflow-x: auto !important;
        overflow-y: visible !important;
        -webkit-overflow-scrolling: touch;
    }}
    .gradio-container .tabs .tab-container:not(.visually-hidden) button {{
        flex: 0 0 auto !important;
        white-space: nowrap !important;
        min-height: 44px !important;
        padding: 10px 14px !important;
        font-size: 14px !important;
        border-radius: 12px !important;
    }}

    /* 图标按钮（清空、删除等小控件）抬到可点尺寸 */
    .gradio-container button.icon,
    .gradio-container .icon-button,
    .gradio-container button[aria-label] {{
        min-width: 44px !important;
        min-height: 44px !important;
    }}

    /* 下拉框内部的输入框 */
    .gradio-container .dropdown input,
    .gradio-container .wrap-inner input,
    .gradio-container input.border-none {{
        min-height: 44px !important;
    }}

    /* Gradio 自带的表单标签字号 */
    .gradio-container label,
    .gradio-container .label-wrap span,
    .gradio-container .block-title {{ font-size: 13px !important; }}

    /* 按钮与输入：抬到可点高度 */
    .gradio-container button.primary,
    .gradio-container button.secondary,
    .gradio-container .gr-button-primary,
    .gradio-container .gr-button-secondary {{ min-height: 46px !important; }}
    .gradio-container input,
    .gradio-container textarea,
    .gradio-container select {{ min-height: 44px !important; font-size: 15px !important; }}

    /* 图片预览不要顶满整屏 */
    .gradio-container .image-container img {{ max-height: 46vh; }}
}}

/* ============================================================
   快捷键提示条：右下角常驻几秒后淡出，鼠标移上去会重新出现
   ============================================================ */
#kb-hint {{
    position: fixed; right: 18px; bottom: 16px; z-index: 60;
    padding: 8px 16px; border-radius: 999px;
    background: rgba(11, 14, 8, .72); color: #C9BDA4;
    border: 1px solid rgba(232, 220, 199, .18);
    font-size: 12.5px; letter-spacing: .04em; line-height: 1.6;
    backdrop-filter: blur(6px); pointer-events: none;
    opacity: 1; transition: opacity 600ms var(--ease);
}}
#kb-hint.gone {{ opacity: 0; }}
#kb-hint b {{ color: #E8DCC7; font-weight: 600; }}
"""


def _esc(text: object) -> str:
    return escape(str(text if text is not None else ""), quote=True)


def empty_html(text: str = "还没有识别结果") -> str:
    return (
        f'<div class="empty">{_esc(text)}<br>'
        "上传或拍摄一张垃圾照片，点「识别并生成投放引导」</div>"
    )


def cta_html(actions: list[tuple[str, str]], kinds: str = "primary") -> str:
    """按钮式链接。

    Gradio 的 Markdown 链接渲染出来是一条 20px 高的行内文字，手机上点不准，
    所以需要对外跳转的入口一律用这里的 <a class="cta">，最小高度 44px。
    kinds 按顺序逐项对应，缺省时沿用最后一项。
    """
    order = [item.strip() for item in kinds.split(",") if item.strip()] or ["primary"]
    links = "".join(
        f'<a class="cta {order[i] if i < len(order) else order[-1]}" '
        f'href="{_esc(href)}">{_esc(label)}</a>'
        for i, (label, href) in enumerate(actions)
    )
    return f'<div class="cta-row">{links}</div>'


def hero_html(
    title: str,
    subtitle: str,
    tags: list[str],
    actions: list[tuple[str, str]] | None = None,
) -> str:
    tag_html = "".join(f"<span>{_esc(tag)}</span>" for tag in tags)
    parts = [
        '<div class="hero">',
        f"<h1>{_esc(title)}</h1>",
        f"<p>{_esc(subtitle)}</p>",
        f'<div class="tags">{tag_html}</div>',
    ]
    if actions:
        parts.append(cta_html(actions, "primary,ghost"))
    parts.append("</div>")
    return "".join(parts)


def status_html(items: list[tuple[str, str]]) -> str:
    pills = "".join(
        f'<span class="pill {_esc(style)}">{_esc(text)}</span>' for text, style in items
    )
    return f'<div class="statusbar">{pills}</div>'


def vision_html(result, note: str = "") -> str:
    chips = "".join(
        f'<span class="vchip">{_esc(item.name)}'
        + (f'<i>{_esc(item.material)}</i>' if item.material else "")
        + "</span>"
        for item in result.items
    )
    if not chips:
        chips = '<span class="vchip">未检测到部件</span>'
    note_html = (
        f'<div class="footnote" style="margin-top:14px">{_esc(note)}</div>' if note else ""
    )
    return (
        '<div class="panel">'
        f'<p class="vcard-label">画面描述，来自 {_esc(result.backend)}，'
        f"耗时 {result.latency_ms:.0f} ms</p>"
        f'<p class="vsummary">{_esc(result.summary or "模型未返回画面描述")}</p>'
        f'<div class="vchips">{chips}</div>'
        f"{note_html}"
        "</div>"
    )


def _strata(counts: dict[str, int], labels: dict[str, str]) -> str:
    """签名动作：按类别数量比例分割的地层条。"""
    total = sum(counts.values())
    if total <= 0:
        return ""
    segments: list[str] = []
    legend: list[str] = []
    for category in CATEGORY_ORDER:
        value = counts.get(category, 0)
        if not value:
            continue
        color = _c(category)
        share = value / total
        segments.append(
            f'<span style="flex:{value} 1 0;background:{color["fill"]}" '
            f'title="{_esc(labels.get(category, category))} {value}"></span>'
        )
        legend.append(
            '<div>'
            f'<i class="dot" style="background:{color["fill"]}"></i>'
            f"<b>{value}</b><em>{_esc(labels.get(category, category))}</em>"
            f'<em style="opacity:.7">·{share * 100:.0f}%</em>'
            "</div>"
        )
    return (
        '<div class="panel strata-wrap">'
        f'<div class="strata">{"".join(segments)}</div>'
        f'<div class="strata-legend">{"".join(legend)}</div>'
        "</div>"
    )


def _note_block(kind: str, label: str, text: str) -> str:
    return (
        f'<div class="note-block note-{kind}">'
        f'<span class="k">{_esc(label)}</span>{_esc(text)}</div>'
    )


def _part_row(part) -> str:
    color = _c(part.category)
    count = f'<span class="row-count">×{part.count}</span>' if part.count > 1 else ""
    prep = f'<div class="row-sub">{_esc(" → ".join(part.prep))}</div>' if part.prep else ""
    notes = ""
    if part.conditional:
        notes += _note_block("warn", "条件判定", part.conditional)
    if part.pitfall:
        notes += _note_block("danger", "常见误投", part.pitfall)
    if part.note:
        notes += _note_block("info", "说明", part.note)
    return (
        '<div class="row">'
        f'<div class="row-blob" style="background:{color["soft"]}">'
        f"{icon_svg(part.category)}</div>"
        '<div class="row-main">'
        f'<div class="row-title">{_esc(part.part)}{count}</div>'
        f"{prep}{notes}"
        "</div>"
        f'<div class="row-trail"><span class="badge" style="background:{color["soft"]};'
        f'color:{color["ink"]}">{_esc(part.category_label)}</span></div>'
        "</div>"
    )


def guidance_html(guidance) -> str:
    if not guidance.all_parts and not guidance.unmatched:
        return empty_html()

    blocks: list[str] = []

    # 结论
    if guidance.is_composite:
        blocks.append(
            '<div class="panel gd-head">'
            f'<h2><span class="gd-badge">复合垃圾</span>'
            f"{_esc(guidance.composite_name)}</h2>"
            f'<p class="why">{_esc(guidance.why)}</p>'
            "</div>"
        )
    else:
        blocks.append(
            '<div class="panel gd-head">'
            f'<h2>{_esc(guidance.composite_name or guidance.summary or "识别结果")}</h2>'
            "</div>"
        )

    # 签名动作：地层条
    blocks.append(_strata(guidance.category_counts(), guidance.labels))

    # 混投检查
    if guidance.mismatches:
        bin_label = guidance.labels.get(guidance.bin_type, guidance.bin_type)
        rows = "".join(
            f"<div class='mrow'><span>{_esc(part.display_name())}</span>"
            f"<span class='badge' style='background:{_c(part.category)['soft']};"
            f"color:{_c(part.category)['ink']}'>{_esc(part.category_label)}</span></div>"
            for part in guidance.mismatches
        )
        blocks.append(
            '<div class="panel flag flag-red">'
            f"<h3>混投检查 · 这是「{_esc(bin_label)}」桶，"
            f"其中 {len(guidance.mismatches)} 项投错了</h3>"
            f"{rows}"
            '<p class="tip">混投会让整桶垃圾失去分类价值，保洁需要二次分拣，'
            "是投放点最主要的成本来源。</p>"
            "</div>"
        )

    # 部件列表
    if guidance.all_parts:
        header = (
            f"需要拆成 {len(guidance.parts)} 部分分别投放"
            if guidance.is_composite
            else f"识别到 {len(guidance.all_parts)} 个部件"
        )
        rows = "".join(_part_row(part) for part in guidance.all_parts)
        blocks.append(
            f'<div class="group-header">{_esc(header)}</div>'
            f'<div class="list">{rows}</div>'
        )

    # 分拣优先级
    if len(guidance.all_parts) >= 4:
        from app.disassembler import SORT_PRIORITY

        items: list[str] = []
        for category, action, reason in SORT_PRIORITY:
            members = [
                part.display_name() for part in guidance.all_parts if part.category == category
            ]
            if not members:
                continue
            label = guidance.labels.get(category, category)
            items.append(
                f"<li><span class='step'>{_esc(action)}</span>："
                f"{_esc('、'.join(members))}（{_esc(label)}）"
                f"<br><span class='why'>{_esc(reason)}</span></li>"
            )
        if items:
            blocks.append(
                '<div class="panel flag flag-amber"><h3>分拣优先级</h3>'
                f"<ol>{''.join(items)}</ol></div>"
            )

    # 折叠区
    if guidance.steps:
        steps = "".join(f"<li>{_esc(step)}</li>" for step in guidance.steps)
        blocks.append(
            '<details class="fold"><summary><span class="chev"></span>操作步骤'
            f"</summary><ol>{steps}</ol></details>"
        )

    pitfalls = [part for part in guidance.all_parts if part.pitfall]
    if pitfalls:
        items = "".join(
            f"<li><b>{_esc(part.display_name())}</b>：{_esc(part.pitfall)}</li>"
            for part in pitfalls
        )
        blocks.append(
            '<details class="fold"><summary><span class="chev"></span>常见误投汇总 · '
            f"{len(pitfalls)} 条</summary><ul>{items}</ul></details>"
        )

    if guidance.unmatched:
        items = "".join(
            f"<li>{_esc(item.name)}"
            + (f"（{_esc(item.material)}）" if item.material else "")
            + f"：规则库暂未收录，建议按 {_esc(guidance.residual_label)} 投放</li>"
            for item in guidance.unmatched
        )
        blocks.append(
            '<div class="panel"><div class="group-header">未匹配到规则的部件 · '
            f"{len(guidance.unmatched)} 项</div><ul>{items}</ul></div>"
        )

    blocks.append(
        f'<div class="footnote">分类口径：{_esc(guidance.region_name)}。'
        "各地标准存在差异，最终以所在城市现行分类目录为准。</div>"
    )
    return "".join(blocks)


def metrics_html(summary: dict) -> str:
    rate_keys = [
        "整体判定准确率",
        "范围外拒答率",
        "范围内误拒答率",
        "平均回答关键词覆盖率",
        "平均检索关键词覆盖率",
        "引用来源命中率",
    ]
    cards: list[str] = []
    for key, value in summary.items():
        if value is None:
            continue
        if key in rate_keys:
            ratio = float(value)
            color = "#606C38" if ratio >= 0.95 else "#C08E3A" if ratio >= 0.8 else "#C66B3D"
            cards.append(
                f'<div class="metric"><b style="color:{color}">{ratio * 100:.1f}%</b>'
                f"<span>{_esc(key)}</span></div>"
            )
        elif "耗时" in key:
            cards.append(
                f'<div class="metric"><b style="color:#606C38">{_esc(value)}</b>'
                f"<span>{_esc(key)} · ms</span></div>"
            )
        else:
            cards.append(
                f'<div class="metric"><b style="color:#2E2A20">{_esc(value)}</b>'
                f"<span>{_esc(key)}</span></div>"
            )
    return f'<div class="metrics">{"".join(cards)}</div>'
