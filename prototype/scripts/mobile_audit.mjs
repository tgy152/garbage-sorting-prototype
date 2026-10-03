/**
 * 移动端布局实测：用真实浏览器在手机视口下渲染两个页面，量出问题。
 *
 * 检查项：
 *   1. 横向溢出 —— 任何元素右边界超出视口，手机上就会出现左右横拉
 *   2. 字号过小 —— 正文低于 14px 在手机上读起来费劲
 *   3. 点击区域过小 —— 可点元素低于 44×44 容易点错
 *   4. 页面级横向滚动 —— documentElement.scrollWidth 超出视口
 *
 * 用法（在 prototype 目录下）：
 *   node scripts/mobile_audit.mjs
 */

import { createRequire } from 'node:module';

// Playwright 装在 Codex 运行时自带的 node_modules 里，不在项目内，
// 因此用显式路径加载，而不是靠包名解析。
const require = createRequire(import.meta.url);
const RUNTIME_MODULES =
  process.env.CODEX_NODE_MODULES ||
  'C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
let chromium;
try {
  ({ chromium } = require(`${RUNTIME_MODULES}/playwright`));
} catch (error) {
  console.error('无法加载 playwright：', error.message);
  console.error('可通过 CODEX_NODE_MODULES 环境变量指定 node_modules 目录。');
  process.exit(2);
}

const VIEWPORTS = [
  { name: 'iPhone SE', width: 375, height: 667 },
  { name: 'iPhone 14', width: 390, height: 844 },
  { name: '安卓大屏', width: 412, height: 915 },
];

const TARGETS = [
  { name: '原型工具页', url: 'http://127.0.0.1:7860/' },
  { name: '作品介绍页', url: 'http://127.0.0.1:7860/landing/' },
];

const MIN_FONT = 14;
const MIN_TAP = 44;

async function audit(page, viewport) {
  return page.evaluate(
    ({ width, minFont, minTap }) => {
      const seen = new Set();
      const overflow = [];
      const smallText = [];
      const smallTap = [];

      const describe = (el) => {
        const id = el.id ? `#${el.id}` : '';
        const cls = (el.className || '')
          .toString()
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .map((c) => `.${c}`)
          .join('');
        const text = (el.textContent || '').trim().slice(0, 24);
        return `${el.tagName.toLowerCase()}${id}${cls}${text ? ` "${text}"` : ''}`;
      };

      for (const el of document.querySelectorAll('body *')) {
        const style = getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
          continue;
        }
        // Gradio 会把标签页按钮复制一份到 .visually-hidden 容器里用于测量宽度，
        // 那些元素只有 1px 高，不是真实可点区域，必须排除，否则全是误报。
        if (el.closest('.visually-hidden, .sr-only, [aria-hidden="true"]')) {
          continue;
        }
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 || rect.height === 0) continue;
        // 完全在视口外（例如折叠容器内部）也不计入
        if (rect.bottom < 0 || rect.top > document.documentElement.scrollHeight) continue;

        // 1. 横向溢出
        if (rect.right > width + 1) {
          const key = describe(el);
          if (!seen.has(key)) {
            seen.add(key);
            overflow.push({
              el: key,
              right: Math.round(rect.right),
              width: Math.round(rect.width),
            });
          }
        }

        // 2. 字号：只看直接承载文字的叶子节点
        const hasText = Array.from(el.childNodes).some(
          (n) => n.nodeType === 3 && n.textContent.trim().length > 1
        );
        if (hasText) {
          const size = parseFloat(style.fontSize);
          // 正文与元信息分层判定：正文 14px，元信息（胶囊、标签、脚注、代码）13px
          const isMeta =
            el.matches('.pill, .badge, .footnote, code, label, .vchip, .tags span, .cap');
          const floor = isMeta ? 13 : minFont;
          if (size < floor) {
            smallText.push({
              el: describe(el),
              size: Math.round(size * 10) / 10,
              floor,
            });
          }
        }

        // 3. 点击区域：只统计真正可交互的控件。
        // svg / span 之类的子元素会从可点父级继承 cursor:pointer，
        // 但它们本身不是点击目标，统计进来只会制造误报。
        const interactive = el.matches(
          'a[href], button, input:not([type="hidden"]), select, textarea, summary, ' +
            '[role="button"], [role="tab"], [role="switch"], [role="checkbox"], [role="slider"]'
        );
        if (interactive && rect.height < minTap) {
          smallTap.push({
            el: describe(el),
            h: Math.round(rect.height),
            w: Math.round(rect.width),
          });
        }
      }

      return {
        scrollWidth: document.documentElement.scrollWidth,
        hasHScroll: document.documentElement.scrollWidth > width + 1,
        overflow: overflow.slice(0, 12),
        overflowCount: overflow.length,
        smallText: smallText.slice(0, 14),
        smallTextCount: smallText.length,
        smallTap: smallTap.slice(0, 14),
        smallTapCount: smallTap.length,
      };
    },
    { width: viewport.width, minFont: MIN_FONT, minTap: MIN_TAP }
  );
}

const browser = await chromium.launch({ channel: 'msedge', headless: true });
let problems = 0;

for (const target of TARGETS) {
  console.log('='.repeat(78));
  console.log(`${target.name}  ${target.url}`);
  console.log('='.repeat(78));

  for (const viewport of VIEWPORTS) {
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 2,
      isMobile: true,
      hasTouch: true,
    });
    try {
      await page.goto(target.url, { waitUntil: 'networkidle', timeout: 45000 });
      await page.waitForTimeout(1200);
      const result = await audit(page, viewport);

      const flags = [];
      if (result.hasHScroll) flags.push(`页面横向滚动 ${result.scrollWidth}px`);
      if (result.overflowCount) flags.push(`溢出元素 ${result.overflowCount}`);
      if (result.smallTextCount) flags.push(`小字 ${result.smallTextCount}`);
      if (result.smallTapCount) flags.push(`小点击区 ${result.smallTapCount}`);

      console.log(`\n【${viewport.name} ${viewport.width}x${viewport.height}】`);
      console.log(flags.length ? `  ⚠️ ${flags.join('  |  ')}` : '  ✅ 未发现问题');
      problems += flags.length;

      if (result.overflow.length) {
        console.log('  横向溢出：');
        for (const item of result.overflow) {
          console.log(`    right=${item.right} w=${item.width}  ${item.el}`);
        }
      }
      if (result.smallText.length) {
        console.log('  字号偏小（含各自下限）：');
        for (const item of result.smallText) {
          console.log(`    ${item.size}px（下限 ${item.floor}）  ${item.el}`);
        }
      }
      if (result.smallTap.length) {
        console.log('  点击区域偏小：');
        for (const item of result.smallTap) {
          console.log(`    ${item.w}x${item.h}  ${item.el}`);
        }
      }
    } catch (error) {
      console.log(`\n【${viewport.name}】渲染失败：${error.message}`);
      problems += 1;
    } finally {
      await page.close();
    }
  }
  console.log('');
}

await browser.close();
console.log('='.repeat(78));
console.log(problems ? `共发现 ${problems} 类问题` : '全部通过');
process.exit(problems ? 1 : 0);
