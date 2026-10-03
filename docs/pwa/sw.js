/*
 * Service Worker：让应用可以被"添加到主屏幕"，并在断网时给出可读提示。
 *
 * 策略说明：
 *   识别功能必须联网（要调用云端视觉模型），所以不做全站离线缓存，
 *   只缓存图标与离线页这类静态资源；页面请求走网络优先，失败时回退到离线页。
 */

// 版本号一改，旧的 Cache Storage 会在 activate 时被整体清掉。
// 换图标或改离线页时记得同时改这里，否则浏览器会一直用旧资源。
const CACHE = "waste-sorter-v2";
const STATIC_ASSETS = [
  "/pwa/icon-192.png",
  "/pwa/icon-512.png",
  "/pwa/icon-maskable-512.png",
  "/pwa/apple-touch-icon.png",
  "/pwa/offline.html",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(STATIC_ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // 静态资源走缓存优先
  if (url.pathname.startsWith("/pwa/") || url.pathname === "/manifest.webmanifest") {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request))
    );
    return;
  }

  // 页面与接口：网络优先，断网时回退到离线页
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() =>
        caches.match("/pwa/offline.html").then(
          (hit) =>
            hit ||
            new Response("网络不可用。识别功能需要联网，请检查网络后重试。", {
              headers: { "Content-Type": "text/plain; charset=utf-8" },
            })
        )
      )
    );
  }
});
