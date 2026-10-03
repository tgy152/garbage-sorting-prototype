# 用 Dreamweaver 优化三个页面 · 操作说明

> 本文件写给第一次用 Dreamweaver 改这三个页面的人。
> 改动前请先看第 1 节：**三个页面里只有一个适合用 Dreamweaver 改。**

---

## 1. 三个页面分别是什么（先弄清这个，能省很多时间）

| 页面 | 实际是什么 | 能用 Dreamweaver 改吗 |
| --- | --- | --- |
| 原型展示页 `/` | **Python 程序**（Gradio 应用），界面写在 `prototype/app/ui.py` 里，运行时才渲染成网页 | ❌ 不能。它不是 HTML 文件，Dreamweaver 打开什么都没有 |
| 作品介绍页 `/landing/` | **纯 HTML + CSS + GSAP 动画**：`landing/index.html` + `landing/styles.css` | ✅ 能，而且很合适 |
| 数据大屏 `/screen/` | **HTML + CSS + JavaScript + Three.js + ECharts**：`大屏/index.html`、`screen.css`、`screen.js`、`scene3d.js` | ✅ 能，但只能在「代码视图」改 |

结论：**作品介绍页用 Dreamweaver 改最顺手，数据大屏可以改但要小心，原型页要改得改 Python。**

---

## 2. 建站点（Dreamweaver 必须先建站点，路径才不会乱）

建议建**两个小站点**，而不是把整个项目建成一个站点——项目里 `prototype/` 有 16000 多个文件，
建大站点会让 Dreamweaver 扫描很久。

### 站点一：作品介绍页

1. 菜单 `站点 → 新建站点`，站点名称填 `垃圾分类-作品介绍页`
2. 本地站点文件夹选：`C:\Users\15040\Documents\ChatGPT\全球校园人工智能算法精英\landing`
3. 保存

### 站点二：数据大屏

1. 菜单 `站点 → 新建站点`，站点名称填 `垃圾分类-数据大屏`
2. 本地站点文件夹选：`C:\Users\15040\Documents\ChatGPT\全球校园人工智能算法精英\大屏`
3. 保存

> 建好后在「文件」面板里双击 `index.html` 就能打开。

---

## 3. 动手前先改两个偏好设置（很重要）

菜单 `编辑 → 首选参数`：

1. **代码格式** → 把「应用源格式」相关选项**全部取消勾选**
   （否则 Dreamweaver 每次保存都会重排整份代码，把缩进和换行全部打乱，
   这些页面是靠精确格式和行内样式维持版式的，重排后容易错位）
2. **新建文档** → 编码选 `UTF-8`，取消「包含 Unicode 签名（BOM）」

---

## 4. 怎么改、改完必须做什么

### 作品介绍页

- **只在「代码」视图改**，不要用「设计」视图拖动。
  这一页用了 CSS 网格、`clip-path`、滚动动画（GSAP + ScrollTrigger），
  设计视图既显示不准，拖一下也可能把结构改坏。
- 想实时看效果：保存后直接用浏览器打开
  `http://127.0.0.1:7860/landing/`（需要原型服务在跑），或者双击 `landing/index.html`。
- 页面里 `/manifest.webmanifest`、`/pwa/icon-192.png` 这几个以 `/` 开头的链接，
  Dreamweaver 会报「链接不存在」，这是正常的（它们指向站点根，不在 landing 文件夹里），忽略即可。

### 数据大屏

- 同样只用「代码」视图。
- **改完必须重新打包单文件版**，否则你拿去做演示的那个文件还是旧的：

  ```
  cd C:\Users\15040\Documents\ChatGPT\全球校园人工智能算法精英\大屏
  node build-single.mjs
  ```

  打完会更新 `数据大屏-单文件版.html`。
- 大屏有三条兜底逻辑：没有 WebGL 会自动降级成 2D 动画，
  改 `scene3d.js` 时别把 `try/catch` 删掉，删了没显卡的电脑会白屏。

### 原型展示页

- 不要用 Dreamweaver 打开 `prototype/` 里的任何东西。
- 想改界面文字、配色、按钮，改动点在 `prototype/app/ui.py`，
  改完重启服务（双击 `prototype\启动原型.cmd`）。
- 想改分类规则，改 `prototype/rules/waste_sorting.yaml`，那是纯文本，用记事本也行。

---

## 5. 改坏了怎么恢复

改动前的完整备份放在：

```
...\全球校园人工智能算法精英\_备份-20261002\
    ├─ landing\    （作品介绍页）
    ├─ 大屏\        （数据大屏）
    └─ pwa\        （图标与 manifest）
```

把对应文件从备份里复制回去就还原了。

---

## 6. 改完怎么验收

项目里已经有现成的自检脚本，改完可以跑一遍（在 `prototype` 目录下执行）：

| 检查 | 命令 |
| --- | --- |
| 作品介绍页结构与图片 | `python scripts/check_landing_preflight.py` |
| 移动端排版 | `node scripts/mobile_audit.mjs` |
| 配色对比度 | `python scripts/check_contrast.py` |
| PWA 可安装性 | `python scripts/check_pwa.py` |

也可以改完直接找我，我跑一遍全部检查并渲染截图，告诉你哪一页出了问题。

---

## 7. 一句话总结

**作品介绍页**：Dreamweaver 代码视图改，最安全，放手试。
**数据大屏**：代码视图改，改完记得 `node build-single.mjs`。
**原型展示页**：Dreamweaver 帮不上，要改 Python。
**任何时候改坏了**：从 `_备份-20261002` 复制回去。
