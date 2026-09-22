/* =========================================================================
 * Nodalis — sw.js  (v9)
 *
 * WHY THIS FILE HAS TO EXIST
 *
 * Nodalis is one HTML file, deliberately. This is the one exception, and it is
 * not a choice: a notification with BUTTONS on it can only be shown by a
 * service worker. The web platform allows no other route.
 *
 *   new Notification(...)                        - no buttons, ever, anywhere.
 *                                                  Throws outright on Android.
 *   registration.showNotification(..., {actions}) - buttons. Requires this file.
 *
 * That is the whole of the "Snooze does nothing when I press it in the Windows
 * or Android notification" bug. Either there was no service worker at all, so
 * the notification had no buttons; or there was an older one from a previous
 * deployment that had never heard of 'notificationclick', so the buttons were
 * drawn and pressing them did nothing. The app has always listened for the
 * message this file sends. Nothing was sending it.
 *
 * DEPLOY BOTH FILES. index.html and sw.js, side by side, same directory. If
 * this file is missing the app still works and reminders still appear - they
 * just lose their buttons, and the app says so plainly in Reminders.
 *
 * It also brings genuine offline use with it, which the app wanted anyway:
 * network first so a new deployment is never masked by a stale cache, cache
 * second so a plane or a tunnel does not take the app away.
 * ========================================================================= */

const VERSION = 'nodalis-v9.5';
const SHELL = VERSION + '-shell';

self.addEventListener('install', function (event) {
  // Take over immediately: a notification button that needs a reload before it
  // works is a notification button that does not work.
  self.skipWaiting();
  event.waitUntil((async function () {
    try {
      const cache = await caches.open(SHELL);
      await cache.addAll(['./', './index.html']);
    } catch (err) { /* a cold cache is not a failure */ }
  })());
});

self.addEventListener('activate', function (event) {
  event.waitUntil((async function () {
    const names = await caches.keys();
    await Promise.all(names.map(function (n) {
      return n.indexOf(VERSION) === 0 ? null : caches.delete(n);
    }));
    await self.clients.claim();
  })());
});

/* ------------------------------------------------------------------ fetch */

self.addEventListener('fetch', function (event) {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // never touch GitHub's API

  event.respondWith((async function () {
    try {
      const fresh = await fetch(req);
      if (fresh && fresh.ok && fresh.type !== 'opaque') {
        try { (await caches.open(SHELL)).put(req, fresh.clone()); } catch (err) { /* full, or opaque */ }
      }
      return fresh;
    } catch (err) {
      const hit = await caches.match(req);
      if (hit) return hit;
      if (req.mode === 'navigate') {
        const shell = await caches.match('./index.html');
        if (shell) return shell;
      }
      throw err;
    }
  })());
});

/* --------------------------------------------------- notification buttons */

/**
 * The bit that was missing.
 *
 * event.action is '' for a tap on the notification body, or the action id for
 * a button. Either way: bring a window to the front if there is one and tell
 * it what was pressed; if there is no window, open one with the instruction in
 * the URL so a snooze still happens when the app was closed.
 */
self.addEventListener('notificationclick', function (event) {
  const action = event.action || 'open';
  const data = event.notification.data || {};
  event.notification.close();

  event.waitUntil((async function () {
    const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of clients) {
      try { client.postMessage({ type: 'nd-remind-action', action: action, id: data.id, kind: data.kind, refId: data.refId }); }
      catch (err) { /* client going away */ }
      if ('focus' in client) { try { await client.focus(); return; } catch (err) { /* try the next one */ } }
      return;
    }
    const target = './?ndaction=' + encodeURIComponent(action) +
      '&ndremind=' + encodeURIComponent(data.id || '');
    try { await self.clients.openWindow(target); } catch (err) { /* nothing else to try */ }
  })());
});

self.addEventListener('message', function (event) {
  const d = event.data || {};
  if (d.type === 'nd-sw-ping' && event.source) {
    try { event.source.postMessage({ type: 'nd-sw-pong', version: VERSION, actions: true }); }
    catch (err) { /* the page went away */ }
  }
  if (d.type === 'nd-sw-skip-waiting') self.skipWaiting();
});
