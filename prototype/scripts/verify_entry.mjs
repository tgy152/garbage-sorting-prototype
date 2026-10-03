/**
 * 验证作品介绍页入口：首屏是否可见、是否够大、点击是否跳转。
 *
 * 用法：node scripts/verify_entry.mjs [url] [width]
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
let failures = 0;

for (const [label, opts] of [
  ['手机 390', { viewport: { width, height: 844 }, isMobile: true, hasTouch: true }],
  ['桌面 1440', { viewport: { width: 1440, height: 900 } }],
]) {
  const page = await browser.newPage(opts);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(1200);

  const info = await page.evaluate(() => {
    const links = [...document.querySelectorAll('a.cta')];
    return links.map((a) => {
      const r = a.getBoundingClientRect();
      const s = getComputedStyle(a);
      return {
        text: (a.textContent || '').trim(),
        href: a.getAttribute('href'),
        w: Math.round(r.width),
        h: Math.round(r.height),
        top: Math.round(r.top),
        aboveFold: r.top + r.height <= window.innerHeight,
        pe: s.pointerEvents,
        // 隐藏页签里的元素尺寸为 0，不是缺陷，单独统计
        rendered: r.width > 0 && r.height > 0,
      };
    });
  });

  console.log(`\n=== ${label} ===`);
  const visible = info.filter((l) => l.rendered);
  if (!visible.length) {
    console.log('❌ 首屏没有渲染出任何 .cta 入口');
    failures += 1;
  }
  for (const l of visible) {
    const ok = l.h >= 44 && l.w > 60 && l.pe === 'auto' && l.aboveFold;
    if (!ok) failures += 1;
    console.log(
      `${ok ? '✅' : '❌'} 「${l.text}」 ${l.w}x${l.h}px  top=${l.top}  ` +
        `首屏内=${l.aboveFold}  pointer-events=${l.pe}  → ${l.href}`
    );
  }
  if (info.length > visible.length) {
    console.log(`ℹ️  另有 ${info.length - visible.length} 个入口在未打开的页签里（尺寸 0，正常）`);
  }

  // 「⑤ 方案素材」里的入口：切过去再量一次，确认也是可点尺寸
  await page.evaluate(() => {
    const btns = document.querySelectorAll('.tab-container:not(.visually-hidden) button');
    if (btns[4]) btns[4].click();
  });
  await page.waitForTimeout(1000);
  const inTab = await page.evaluate(() => {
    const a = [...document.querySelectorAll('a.cta[href="/landing/"]')].find(
      (el) => el.getBoundingClientRect().height > 0
    );
    if (!a) return null;
    const r = a.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height) };
  });
  if (inTab && inTab.h >= 44) {
    console.log(`✅ 「⑤ 方案素材」页签里的入口 ${inTab.w}x${inTab.h}px`);
  } else {
    failures += 1;
    console.log(`❌ 「⑤ 方案素材」页签里的入口异常：${JSON.stringify(inTab)}`);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);

  const anchor = page.locator('a.cta[href="/landing/"]').first();
  if (await anchor.count()) {
    try {
      await anchor.click({ timeout: 8000 });
      await page.waitForTimeout(2500);
      const ok = page.url().includes('/landing');
      if (!ok) failures += 1;
      console.log(`${ok ? '✅' : '❌'} 点击后 URL：${page.url()}`);
    } catch (e) {
      failures += 1;
      console.log(`❌ 点击失败：${e.message.split('\n')[0]}`);
    }
  } else {
    failures += 1;
    console.log('❌ 首屏没有 href="/landing/" 的入口');
  }
  await page.close();
}

const page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true });
const resp = await page.goto(new URL('/share', url).href, { waitUntil: 'networkidle', timeout: 30000 });
const qrCount = await page.locator('img.qr').count();
const qrOk = await page.evaluate(() => {
  const img = document.querySelector('img.qr');
  return img ? img.complete && img.naturalWidth > 0 : false;
});
console.log('\n=== /share ===');
console.log(`${resp.status() === 200 ? '✅' : '❌'} HTTP ${resp.status()}，二维码 ${qrCount} 张，可解码=${qrOk}`);
if (resp.status() !== 200 || qrCount < 2 || !qrOk) failures += 1;

await browser.close();
console.log(`\n${failures === 0 ? '全部通过' : `${failures} 项未通过`}`);
process.exit(failures === 0 ? 0 : 1);
