// ── Ufone 5G Dashboard — Push Notification Service Worker ──────────────────
self.addEventListener('push', function(event) {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || '💬 New Message', {
      body:    data.body || '',
      icon:    '/static/images/logo1.jpg',
      badge:   '/static/images/logo1.jpg',
      tag:     'chat-' + (data.room || 'region'),
      renotify: true,
      data:    { room: data.room || 'region' },
    })
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  const room = event.notification.data && event.notification.data.room;
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if (c.url.includes('/chat/')) { c.focus(); return; }
      }
      return clients.openWindow('/chat/' + (room ? '?room=' + room : ''));
    })
  );
});