/*
 * 在 Photoshop 里排「校园垃圾分类投放引导助手」展示海报。
 *
 * 结构照着参考海报那两套的共性来：顶部通栏 → 主视觉 → 编号模块（中英标题 + 分隔线）
 * → 底部通栏收尾。配色用作品自己的锚点色（深苔底 + 沙面字 + 赭石点缀），
 * 而不套用参考图里的青绿或暖棕，因为海报要和截图里的界面同色系，
 * 图才能直接落在版面上、不出现色块接缝。
 *
 * 用法（路径尽量只用 ASCII，ExtendScript 对中文路径不稳）：
 *   $app.DoJavaScript("$.evalFile('.../build_poster.jsx')")
 *
 * 脚本结束前会存出 PSD（分层）与 PNG（预览）。
 */

#target photoshop

(function () {
  var BASE = "C:/Users/15040/AppData/Local/Temp/codex_poster";
  var IMG = BASE + "/img";
  var OUT_PSD = BASE + "/out/poster.psd";
  var OUT_PNG = BASE + "/out/poster.png";

  // ---------- 版面参数 ----------
  var W = 1080;
  var MARGIN = 60;
  var CONTENT = W - MARGIN * 2; // 960
  var GAP_MODULE = 90;

  var C_SOIL = "3A4032"; // 页面底：深苔
  var C_BAR = "2E2A20";  // 通栏：墨
  var C_SAND = "E8DCC7"; // 主文字：沙
  var C_MUTED = "CFC3AA"; // 次级文字
  var C_LINE = "6B5D45";  // 分隔线
  var C_OCHRE = "C08E3A"; // 强调：赭石
  var C_SAGE = "8B9D83";  // 英文：灰绿
  // 英文小标签原本用 C_SAGE，实测在深苔底上只有 3.7:1，17px 字号不够用。
  // B9AE95 是 4.87:1，同属大地色域，观感不变。
  var C_EN = "B9AE95";

  var F_TITLE = "NotoSerifSC-Black";
  var F_BOLD = "NotoSerifSC-Bold";
  var F_BODY = "NotoSerifSC-Regular";
  var F_SANS = "NotoSansSC-Regular";
  var F_SANS_B = "NotoSansSC-Bold";

  app.displayDialogs = DialogModes.NO;
  app.preferences.rulerUnits = Units.PIXELS;
  try {
    app.preferences.interpolation = ResampleMethod.BICUBICSHARPER;
  } catch (e) {}

  function col(hex) {
    var c = new SolidColor();
    c.rgb.hexValue = hex;
    return c;
  }

  /* layer.bounds 返回的是带单位的字符串（"0 px"）而不是数字。
     直接拿它做减法会被 UnitValue 的隐式转换带偏，实测把 (60, 1106)
     算成 (-60, -1106)，截图整块跑到画布外，导出的 PNG 上那一块只剩底色。
     所以一律 parseFloat 之后再算，并且移动后回读一次坐标自校验。 */
  function moveTo(layer, x, y) {
    for (var i = 0; i < 4; i++) {
      var b = layer.bounds;
      var dx = x - parseFloat(b[0]);
      var dy = y - parseFloat(b[1]);
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) {
        return true;
      }
      layer.translate(dx, dy);
    }
    var f = layer.bounds;
    return Math.abs(x - parseFloat(f[0])) < 0.5 && Math.abs(y - parseFloat(f[1])) < 0.5;
  }

  function addText(doc, str, x, baselineY, size, font, hex, align) {
    var layer = doc.artLayers.add();
    layer.kind = LayerKind.TEXT;
    layer.name = "字/" + str.substring(0, 16);
    var t = layer.textItem;
    t.contents = str;
    t.font = font;
    t.size = size;
    t.color = col(hex);
    try {
      // 一律左对齐，居中/右对齐自己按量到的宽度换算。
      // 直接用 Justification.CENTER 在这份文档里没生效（文字右边缘贴在锚点上）。
      t.justification = Justification.LEFT;
    } catch (e) {}
    t.position = [0, baselineY];
    try {
      t.antiAliasMethod = AntiAlias.SMOOTH;
      t.hyphenation = false;
    } catch (e) {}
    var b = layer.bounds;
    var left = parseFloat(b[0]);
    var width = parseFloat(b[2]) - left;
    var targetX = x;
    if (align === "center") {
      targetX = x - width / 2;
    } else if (align === "right") {
      targetX = x - width;
    }
    moveTo(layer, targetX, parseFloat(b[1]));
    return layer;
  }

  function addRect(doc, x, y, w, h, hex) {
    var layer = doc.artLayers.add();
    layer.name = "块/" + hex;
    doc.selection.select([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]);
    doc.selection.fill(col(hex), ColorBlendMode.NORMAL, 100);
    doc.selection.deselect();
    return layer;
  }

  // 置入截图，缩放到目标宽度，左上角对齐到 (x, y)，返回实际高度
  function placeImage(doc, file, x, y, targetW, stroke) {
    var f = new File(IMG + "/" + file);
    if (!f.exists) {
      throw new Error("找不到截图：" + f.fsName);
    }
    var src = app.open(f);
    var dup = src.activeLayer.duplicate(doc, ElementPlacement.PLACEATBEGINNING);
    src.close(SaveOptions.DONOTSAVECHANGES);
    app.activeDocument = doc;

    dup.name = "图/" + file;
    var b = dup.bounds;
    var pct = (targetW / (parseFloat(b[2]) - parseFloat(b[0]))) * 100;
    dup.resize(pct, pct, AnchorPosition.TOPLEFT);
    moveTo(dup, x, y);
    b = dup.bounds;

    if (stroke) {
      app.foregroundColor = col(C_LINE);
      try {
        dup.applyStroke(4, ColorBlendMode.NORMAL, 100, false);
      } catch (e) {}
    }
    return parseFloat(b[3]) - parseFloat(b[1]);
  }

  // 模块标题：编号 + 中文标题 + 英文副题 + 分隔线，返回标题区总高
  function moduleHead(doc, no, cn, en, y) {
    addText(doc, no, MARGIN, y + 30, 40, F_SANS_B, C_OCHRE, "left");
    addText(doc, cn, MARGIN + 84, y + 30, 34, F_BOLD, C_SAND, "left");
    addText(doc, en, MARGIN + 84, y + 70, 17, F_SANS, C_EN, "left");
    addRect(doc, MARGIN, y + 92, CONTENT, 2, C_LINE);
    return 116;
  }

  /* ============================================================
     先把高度算出来：Photoshop 建文档必须一次给定画布尺寸，
     所以这里用各地块的固定高度累加，再统一建文档。
     ============================================================ */
  var heightOf = function (targetW, srcW, srcH) {
    return Math.round((targetW / srcW) * srcH);
  };

  var H_TOP = 140;
  var H_HERO = 760;
  // 每个模块 = 标题区 116 + 图，这里必须和 moduleHead 的返回值保持一致
  var H_HEAD = 116;
  var H_01 = H_HEAD + heightOf(960, 2880, 2730);
  var H_02 = H_HEAD + heightOf(960, 2880, 1430);
  var H_03 = H_HEAD + heightOf(960, 2880, 1800) + 36 + heightOf(960, 1296, 416);
  var H_04 = H_HEAD + heightOf(960, 2880, 1478);
  var H_05 = H_HEAD + heightOf(960, 2880, 900);
  // 06 两张手机图并排：各 420 宽，间距 120
  var H_06 = H_HEAD + heightOf(420, 1170, 2532);
  var H_BOTTOM = 250;

  var TOTAL =
    H_TOP + H_HERO + GAP_MODULE +
    H_01 + GAP_MODULE +
    H_02 + GAP_MODULE +
    H_03 + GAP_MODULE +
    H_04 + GAP_MODULE +
    H_05 + GAP_MODULE +
    H_06 + 100 + H_BOTTOM;

  var doc = app.documents.add(W, TOTAL, 72, "海报-垃圾分类投放引导助手",
                              NewDocumentMode.RGB, DocumentFill.WHITE);
  doc.selection.selectAll();
  doc.selection.fill(col(C_SOIL), ColorBlendMode.NORMAL, 100);
  doc.selection.deselect();

  var y = 0;

  // ---------- 顶部通栏 ----------
  addRect(doc, 0, y, W, H_TOP, C_BAR);
  addText(doc, "全球校园人工智能算法精英大赛 · AI+场景创新",
          MARGIN, y + 56, 19, F_SANS, C_MUTED, "left");
  addText(doc, "校园垃圾分类投放引导助手",
          MARGIN, y + 106, 32, F_BOLD, C_SAND, "left");
  addText(doc, "参赛作品 · 原型演示",
          W - MARGIN, y + 106, 19, F_SANS, C_EN, "right");
  y += H_TOP;

  // ---------- 主视觉 ----------
  var heroTop = y + 60;
  addText(doc, "把一件垃圾，", MARGIN, heroTop + 66, 60, F_TITLE, C_SAND, "left");
  addText(doc, "拆成该投的几部分", MARGIN, heroTop + 146, 60, F_TITLE, C_SAND, "left");
  addText(doc, "拍照识别画面里的每个部件，", MARGIN, heroTop + 214, 21, F_BODY, C_MUTED, "left");
  addText(doc, "逐个给出投放类别与投前动作。", MARGIN, heroTop + 250, 21, F_BODY, C_MUTED, "left");
  addText(doc, "复合垃圾拆解 · 条件化判定 · 地区口径可切换 · 规则库可维护",
          MARGIN, heroTop + 320, 19, F_SANS, C_OCHRE, "left");
  placeImage(doc, "30-prototype-hero-phone.png", W - MARGIN - 300, heroTop, 300, false);
  y += H_HERO;

  // ---------- 01 问题 ----------
  y += GAP_MODULE;
  y += moduleHead(doc, "01", "分类知识不是没记住，是套不上", "PROBLEM", y);
  y += placeImage(doc, "22-landing-problem.png", MARGIN, y, CONTENT, true);

  // ---------- 02 方案 ----------
  y += GAP_MODULE;
  y += moduleHead(doc, "02", "感知、判定、生成，各归其位", "METHOD", y);
  y += placeImage(doc, "23-landing-method.png", MARGIN, y, CONTENT, true);

  // ---------- 03 产品 ----------
  y += GAP_MODULE;
  y += moduleHead(doc, "03", "拍一张照片，拿到分步投放引导", "PRODUCT", y);
  y += placeImage(doc, "10-prototype-hero-desktop.png", MARGIN, y, CONTENT, true);
  y += 36;
  y += placeImage(doc, "13-prototype-result-card.png", MARGIN, y, CONTENT, true);

  // ---------- 04 实测数据 ----------
  y += GAP_MODULE;
  y += moduleHead(doc, "04", "在一组真实照片上跑出来的结果", "DATA", y);
  y += placeImage(doc, "24-landing-data.png", MARGIN, y, CONTENT, true);

  // ---------- 05 迭代 ----------
  y += GAP_MODULE;
  y += moduleHead(doc, "05", "覆盖率从 38% 补到 100%，用了两轮", "ITERATION", y);
  y += placeImage(doc, "25-landing-iteration.png", MARGIN, y, CONTENT, true);

  // ---------- 06 访问方式 ----------
  y += GAP_MODULE;
  y += moduleHead(doc, "06", "扫码即用，也可以装到手机桌面", "ACCESS", y);
  var phoneW = 420;
  var phoneGap = CONTENT - phoneW * 2;
  placeImage(doc, "50-install-phone.png", MARGIN, y, phoneW, true);
  placeImage(doc, "52-share-phone.png", MARGIN + phoneW + phoneGap, y, phoneW, true);
  y += H_06 - H_HEAD;

  // ---------- 底部通栏 ----------
  y += 100;
  addRect(doc, 0, y, W, H_BOTTOM, C_BAR);
  addText(doc, "把一件垃圾，拆成该投的几部分", W / 2, y + 96, 38, F_BOLD, C_SAND, "center");
  addText(doc, "类别判定由规则库完成，规则文件可按所在城市分类目录维护",
          W / 2, y + 146, 20, F_SANS, C_MUTED, "center");
  addText(doc, "作品介绍页 /landing/　｜　安装引导 /app　｜　扫码分享 /share",
          W / 2, y + 196, 19, F_SANS, C_EN, "center");

  // ---------- 存盘 ----------
  var outDir = new Folder(BASE + "/out");
  if (!outDir.exists) {
    outDir.create();
  }
  var psdOpts = new PhotoshopSaveOptions();
  psdOpts.layers = true;
  psdOpts.embedColorProfile = true;
  doc.saveAs(new File(OUT_PSD), psdOpts, true, Extension.LOWERCASE);

  var pngOpts = new PNGSaveOptions();
  pngOpts.compression = 6;
  pngOpts.interlaced = false;
  doc.saveAs(new File(OUT_PNG), pngOpts, true, Extension.LOWERCASE);

  return "OK " + doc.width + "x" + doc.height + " 图层数=" + doc.layers.length +
         " PSD=" + OUT_PSD + " PNG=" + OUT_PNG;
})();
