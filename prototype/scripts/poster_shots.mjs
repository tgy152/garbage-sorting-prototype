/**
 * 把网页截成做海报用的高清图。
 *
 * 只截图，不改任何页面与地址。
 * 输出到 data/exports/poster/，命名按海报里要用的顺序编号。
 *
 * 用法：node scripts/poster_shots.mjs [baseUrl]
 */

import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const require = createRequire(import.meta.url);
const RUNTIME_MODULES =
  process.env.CODEX_NODE_MODULES ||
  'C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { chromium } = require(`${RUNTIME_MODULES}/playwright`);

const base = (process.argv[2] || 'http://127.0.0.1:7860').replace(/\/$/, '');
const out = 'data/exports/poster';
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const shots = [];

async function shot(name, page, options) {
  const path = `${out}/${name}.png`;
  await page.screenshot({ path, ...options });
  shots.push(name);
  console.log(`  ${name}.png`);
}

// ---------- 桌面 ----------
const desk = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2,
  // 统一用深色方案：原型、/app、/share 三处的深色底是同一个色值，
  // 截图拼进海报时不会出现色差，也不用给每张图加底板。
  colorScheme: 'dark',
});
await desk.goto(`${base}/`, { waitUntil: 'networkidle', timeout: 60000 });
await desk.waitForTimeout(2000);

console.log('桌面：');
await shot('10-prototype-hero-desktop', desk);
await shot('11-prototype-full-desktop', desk, { fullPage: true });

// 跑一次识别，拿真实结果区
const runButton = desk.getByRole('button', { name: '识别并生成投放引导' });
if (await runButton.count()) {
  await runButton.first().click();
  await desk.waitForTimeout(6000);
  const guidance = desk.locator('.panel').first();
  if (await guidance.count()) {
    await guidance.scrollIntoViewIfNeeded();
    await desk.waitForTimeout(600);
    await shot('12-prototype-result-desktop', desk);
    try {
      await guidance.screenshot({ path: `${out}/13-prototype-result-card.png` });
      shots.push('13-prototype-result-card');
      console.log('  13-prototype-result-card.png');
    } catch (e) {
      console.log(`  [跳过] 结果卡片截图失败：${e.message.split('\n')[0]}`);
    }
  }
  await shot('14-prototype-full-result-desktop', desk, { fullPage: true });
}

await desk.goto(`${base}/landing/`, { waitUntil: 'networkidle', timeout: 60000 });
await desk.waitForTimeout(1500);
await desk.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await desk.waitForTimeout(1200);
await desk.evaluate(() => window.scrollTo(0, 0));
await desk.waitForTimeout(600);
await shot('20-landing-hero-desktop', desk);
await shot('21-landing-full-desktop', desk, { fullPage: true });

for (const [name, id] of [
  ['22-landing-problem', '#problem'],
  ['23-landing-method', '#method'],
  ['24-landing-data', '#data'],
  ['25-landing-iteration', '#iteration'],
]) {
  const el = desk.locator(id).first();
  if (await el.count()) {
    await el.screenshot({ path: `${out}/${name}.png` });
    shots.push(name);
    console.log(`  ${name}.png`);
  }
}
await desk.close();

// ---------- 手机 ----------
const phone = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
  colorScheme: 'dark',
});
console.log('手机：');
await phone.goto(`${base}/`, { waitUntil: 'networkidle', timeout: 60000 });
await phone.waitForTimeout(2000);
await shot('30-prototype-hero-phone', phone);
await shot('31-prototype-full-phone', phone, { fullPage: true });

const runPhone = phone.getByRole('button', { name: '识别并生成投放引导' });
if (await runPhone.count()) {
  await runPhone.first().click();
  await phone.waitForTimeout(6000);
  const card = phone.locator('.panel').first();
  if (await card.count()) {
    await card.scrollIntoViewIfNeeded();
    await phone.waitForTimeout(600);
    await shot('32-prototype-result-phone', phone);
  }
}

await phone.goto(`${base}/landing/`, { waitUntil: 'networkidle', timeout: 60000 });
await phone.waitForTimeout(1500);
await shot('40-landing-full-phone', phone, { fullPage: true });
await phone.evaluate(() => window.scrollTo(0, 0));
await phone.waitForTimeout(500);
await shot('41-landing-hero-phone', phone);

await phone.goto(`${base}/app`, { waitUntil: 'networkidle', timeout: 60000 });
await phone.waitForTimeout(900);
await shot('50-install-phone', phone);
await shot('51-install-full-phone', phone, { fullPage: true });

await phone.goto(`${base}/share`, { waitUntil: 'networkidle', timeout: 60000 });
await phone.waitForTimeout(900);
await shot('52-share-phone', phone);
await shot('53-share-full-phone', phone, { fullPage: true });
await phone.close();

await browser.close();
console.log(`\n共 ${shots.length} 张，输出目录 ${out}`);
