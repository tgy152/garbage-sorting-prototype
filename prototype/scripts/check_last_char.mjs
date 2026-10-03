/**
 * 精确定位「不回答「要拆成几部分、投之前先做什么」。」末尾的句号，
 * 在多个桌面宽度下检查它有没有被裁切或被别的元素压住。
 *
 * 用法：
 *   node scripts/check_last_char.mjs
 */

import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const RUNTIME_MODULES =
  process.env.CODEX_NODE_MODULES ||
  'C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { chromium } = require(`${RUNTIME_MODULES}/playwright`);

const WIDTHS = [1024, 1151, 1280, 1366, 1440, 1536, 1728, 1920];

const browser = await chromium.launch({ channel: 'msedge', headless: true });
let problems = 0;

for (const width of WIDTHS) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.goto('http://127.0.0.1:7860/', { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(700);

  const info = await page.evaluate(() => {
    const prose = Array.from(document.querySelectorAll('.prose')).find((n) =>
      n.textContent.includes('要拆成几部分')
    );
    if (!prose) return { error: '未找到说明块' };

    const walker = document.createTreeWalker(prose, NodeFilter.SHOW_TEXT);
    let node = null;
    while (walker.nextNode()) {
      if (walker.currentNode.textContent.includes('投之前先做什么')) {
        node = walker.currentNode;
        break;
      }
    }
    if (!node) return { error: '未找到该句' };

    const text = node.textContent;
    const idx = text.indexOf('。', text.indexOf('投之前先做什么'));
    if (idx < 0) return { error: '未找到句末句号' };

    const range = document.createRange();
    range.setStart(node, idx);
    range.setEnd(node, idx + 1);
    const cr = range.getBoundingClientRect();

    const el = node.parentElement;
    const eb = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    // 往上找最近的"会裁切"的祖先
    let clip = null;
    let n = el;
    while (n && n !== document.body) {
      const s = getComputedStyle(n);
      if (s.overflowX !== 'visible' || s.overflowY !== 'visible') {
        const b = n.getBoundingClientRect();
        clip = {
          tag: n.tagName.toLowerCase() + '.' + (n.className || '').toString().split(/\s+/).slice(0, 2).join('.'),
          right: Math.round(b.right),
          overflow: s.overflowX + '/' + s.overflowY,
        };
        break;
      }
      n = n.parentElement;
    }

    return {
      charLeft: Math.round(cr.left),
      charRight: Math.round(cr.right),
      charW: Math.round(cr.width),
      parentRight: Math.round(eb.right),
      parentPadRight: cs.paddingRight,
      viewportW: window.innerWidth,
      nearestClipper: clip,
      gapToParent: Math.round(eb.right - cr.right),
    };
  });

  if (info.error) {
    console.log(`${width}px  ${info.error}`);
    problems += 1;
  } else {
    const clipped = info.charRight > info.parentRight + 0.5;
    const nearEdge = info.gapToParent <= 2;
    const flag = clipped || nearEdge ? '⚠️' : '✅';
    if (clipped || nearEdge) problems += 1;
    console.log(
      `${flag} ${String(width).padStart(4)}px  句号 x=${info.charLeft}~${info.charRight} (宽${info.charW})  ` +
        `父元素右边界=${info.parentRight}  余量=${info.gapToParent}px  ` +
        `最近裁切祖先=${info.nearestClipper ? info.nearestClipper.tag + '@' + info.nearestClipper.right : '无'}`
    );
  }
  await page.close();
}

await browser.close();
console.log(problems ? `\n发现 ${problems} 处可疑` : '\n全部宽度下句号都完整可见');
process.exit(problems ? 1 : 0);
