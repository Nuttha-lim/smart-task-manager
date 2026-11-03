/* Service Worker for Smart Task Manager — รับ Web Push แล้วแสดง notification.
   ต้องอยู่ใน web/ เพื่อให้ flutter build web คัดลอกไปที่ root ของแอป
   (path ที่ register ใช้คือ /serviceworker.js) */

/* eslint-disable no-restricted-globals */

self.addEventListener('install', (event) => {
  // ข้าม waitUntil → activate ทันที ไม่ค้าง version เก่า
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// backend ส่ง payload เป็น JSON: {title, body}
self.addEventListener('push', (event) => {
  let title = 'Smart Task Manager';
  let body = 'มีงานด่วนรอคุณอยู่';

  if (event.data) {
    try {
      const payload = event.data.json();
      if (payload.title) title = payload.title;
      if (payload.body) body = payload.body;
    } catch (_) {
      // payload ไม่ใช่ JSON → ใช้ default (ไม่ crash)
    }
  }

  const options = {
    body: body,
    icon: 'icons/Icon-192.png',
    badge: 'icons/Icon-192.png',
    data: { url: './' },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || './';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          return client.focus();
        }
      }
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
