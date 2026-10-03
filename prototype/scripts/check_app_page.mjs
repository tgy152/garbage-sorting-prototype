/**
 * 「安装到手机」引导页的分支检查。
 *
 * PWA 装不上有四种完全不同的原因：已经在应用里、微信内置浏览器、
 * 地址不是 https、iOS 没有一键安装。页面必须逐一分辨并说清楚，
 * 所以这里按四种真实环境各跑一遍。
 *
 * 用法：node scripts/check_app_page.mjs [secureBase] [lanBase]
 */

import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const RUNTIME_MODULES =
  process.env.CODEX_NODE_MODULES ||
  'C:/Users/15040/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const { chromium } = require(`${RUNTIME_MODULES}/playwright`);

const secureBase = (process.argv[2] || 'http://127.0.0.1:7860').replace(/\/$/, '');
const lanBase = (process.argv[3] || '').replace(/\/$/, '');

const UA = {
  android:
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
  iphone:
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
  wechat:
    'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 MicroMessenger/8.0.49',
};

const browser = await chromium.launch({ channel: 'msedge', headless: true });
let failures = 0;

function report(ok, message) {
  if (!ok) failures += 1;
  console.log(`${ok ? '✅' : '❌'} ${message}`);
}

async function readStatus(page) {
  return page.evaluate(() => ({
    title: document.getElementById('status-title')?.textContent.trim(),
    text: document.getElementById('status-text')?.textContent.trim(),
    android: !document.getElementById('steps-android')?.hidden,
    iosSteps: !document.getElementById('steps-ios')?.hidden,
    installed: !document.getElementById('steps-installed')?.hidden,
    buttonHidden: document.getElementById('install-btn')?.hidden,
    qrOk: (() => {
      const img = document.querySelector('img.qr');
      return Boolean(img && img.complete && img.naturalWidth > 0);
    })(),
  }));
}

async function open(ua, url, extraInit) {
  const context = await browser.newContext({
    userAgent: ua,
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  if (extraInit) await page.addInitScript(extraInit);
  await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(600);
  return { context, page };
}

// 1) 安卓 + https/本机地址：等 beforeinstallprompt
{
  const fake = `
    window.addEventListener('load', function () {
      var e = new Event('beforeinstallprompt');
      e.prompt = function () { window.__prompted = true; };
      e.userChoice = Promise.resolve({ outcome: 'accepted' });
      window.__event = e;
      window.dispatchEvent(e);
    });
  `;
  const { context, page } = await open(UA.android, `${secureBase}/app`, fake);
  const s = await readStatus(page);
  console.log(`\n=== 安卓（可安装） ===\n  状态：${s.title} —— ${s.text}`);
  report(s.title === '这台设备可以直接安装', '状态判断为「可以直接安装」');
  report(s.buttonHidden === false, '「安装到手机」按钮出现');
  report(s.android && !s.iosSteps, '只展示安卓步骤');
  report(s.qrOk, '二维码正常渲染');

  await page.click('#install-btn');
  await page.waitForTimeout(300);
  const prompted = await page.evaluate(() => window.__prompted === true);
  report(prompted, '点击按钮调起了系统安装流程');
  await context.close();
}

// 2) iPhone：没有一键安装
{
  const { context, page } = await open(UA.iphone, `${secureBase}/app`);
  const s = await readStatus(page);
  console.log(`\n=== iPhone ===\n  状态：${s.title} —— ${s.text}`);
  report(s.title === '需要手动添加', '状态判断为「需要手动添加」');
  report(s.iosSteps && !s.android, '只展示 iOS 步骤');
  report((await page.locator('#steps-ios').innerText()).includes('添加到主屏幕'), 'iOS 步骤含「添加到主屏幕」');
  await context.close();
}

// 3) 微信内置浏览器
{
  const { context, page } = await open(UA.wechat, `${secureBase}/app`);
  const s = await readStatus(page);
  console.log(`\n=== 微信 ===\n  状态：${s.title} —— ${s.text}`);
  report(s.title === '微信里装不了', '状态判断为「微信里装不了」');
  await context.close();
}

// 4) 局域网 http 地址：不满足安装条件
if (lanBase) {
  const { context, page } = await open(UA.android, `${lanBase}/app`);
  const s = await readStatus(page);
  console.log(`\n=== 局域网地址 ${lanBase} ===\n  状态：${s.title} —— ${s.text}`);
  report(s.title === '这个地址装不了', '状态判断为「这个地址装不了」');
  await context.close();
}

// 5) 从原型首屏一键安装：应拦截跳转，直接弹安装框
{
  const fake = `
    window.addEventListener('load', function () {
      var e = new Event('beforeinstallprompt');
      e.prompt = function () { window.__prompted = true; };
      e.userChoice = Promise.resolve({ outcome: 'accepted' });
      window.dispatchEvent(e);
    });
  `;
  const context = await browser.newContext({
    userAgent: UA.android,
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  await page.addInitScript(fake);
  await page.goto(`${secureBase}/`, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(1200);
  await page.click('a.cta[href="/app"]');
  await page.waitForTimeout(1200);
  const prompted = await page.evaluate(() => window.__prompted === true);
  console.log('\n=== 原型首屏一键安装 ===');
  report(prompted, '首屏「安装到手机」直接调起安装，不跳转');
  report(page.url().includes('/app') === false, `仍留在原型页（${page.url()}）`);
  await context.close();
}

// 6) 装完之后再打开：应识别为已在应用内，不再劝人安装
{
  const { context, page } = await open(UA.iphone, `${secureBase}/app`, () => {
    Object.defineProperty(window.navigator, 'standalone', { value: true });
  });
  const s = await readStatus(page);
  console.log('\n=== 已安装后再打开 ===');
  console.log(`  状态：${s.title} —— ${s.text}`);
  report(s.title === '已安装', '状态判断为「已安装」');
  report(s.installed && !s.android && !s.iosSteps, '不再显示安装步骤');
  await context.close();
}

await browser.close();
console.log(`\n${failures === 0 ? '全部通过' : `${failures} 项未通过`}`);
process.exit(failures === 0 ? 0 : 1);
