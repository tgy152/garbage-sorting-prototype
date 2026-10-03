/**
 * 定位"是谁把页面撑宽了"：从 html 到最宽的元素，逐层打印计算样式。
 *
 * 用法：
 *   node scripts/mobile_chain.mjs [url] [width]
 */

import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const RUNTIME_MODULES =
  process.env.CODEX_NODE_MODULES ||
  'C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { chromium } = require(`${RUNTIME_MODULES}/playwright`);

const url = process.argv[2] || 'http://127.0.0.1:7860/';
const width = Number(process.argv[3] || 390);

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({
  viewport: { width, height: 844 },
  isMobile: true,
  hasTouch: true,
});
await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
await page.waitForTimeout(1000);

const report = await page.evaluate((viewportWidth) => {
  const info = (el) => {
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const cls = (el.className || '').toString().split(/\s+/).filter(Boolean).slice(0, 2).join('.');
    return {
      tag: `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${cls ? '.' + cls : ''}`,
      width: Math.round(r.width),
      right: Math.round(r.right),
      display: s.display,
      width_css: s.width,
      minWidth: s.minWidth,
      maxWidth: s.maxWidth,
      flex: `${s.flexGrow}/${s.flexShrink}/${s.flexBasis}`,
      whiteSpace: s.whiteSpace,
      overflowX: s.overflowX,
      position: s.position,
    };
  };

  // 找出最宽的"叶子级"溢出元素
  let widest = null;
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0) continue;
    if (!widest || r.width > widest.width) widest = { el, width: r.width };
  }
  if (!widest) return { chain: [], viewportWidth };

  const chain = [];
  let node = widest.el;
  while (node && node !== document.documentElement.parentElement) {
    chain.push(info(node));
    node = node.parentElement;
  }
  return { chain: chain.reverse(), viewportWidth, widestText: widest.el.textContent?.trim().slice(0, 30) };
}, width);

console.log(`视口宽度 ${report.viewportWidth}px`);
console.log(`最宽元素文字：「${report.widestText || ''}」`);
console.log('');
console.log(
  'tag'.padEnd(44) +
    'width'.padStart(7) +
    'minW'.padStart(9) +
    'flex'.padStart(14) +
    'wrap'.padStart(10) +
    'display'.padStart(12)
);
for (const item of report.chain) {
  console.log(
    item.tag.slice(0, 43).padEnd(44) +
      String(item.width).padStart(7) +
      item.minWidth.padStart(9) +
      item.flex.padStart(14) +
      item.whiteSpace.padStart(10) +
      item.display.padStart(12)
  );
}

await browser.close();
