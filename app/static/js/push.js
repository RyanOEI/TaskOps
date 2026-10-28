// TaskOps Client PWA & Push Notification Manager

// Helper: Convert URL-safe Base64 to Uint8Array for PushManager
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/\-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

// Get CSRF Token from meta tag
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// Send PushSubscription to backend
async function sendSubscriptionToBackend(subscription) {
  if (!subscription) return false;

  let key = '';
  let auth = '';

  // 1. Try standard PushSubscription.toJSON()
  try {
    const rawJson = subscription.toJSON();
    if (rawJson && rawJson.keys) {
      key = rawJson.keys.p256dh || '';
      auth = rawJson.keys.auth || '';
    }
  } catch (e) {
    console.warn('[Push] toJSON() extraction failed:', e);
  }

  // 2. Fallback to getKey() if needed
  if (!key && subscription.getKey) {
    const rawKey = subscription.getKey('p256dh');
    if (rawKey) {
      key = btoa(String.fromCharCode.apply(null, new Uint8Array(rawKey)));
    }
  }
  if (!auth && subscription.getKey) {
    const rawAuth = subscription.getKey('auth');
    if (rawAuth) {
      auth = btoa(String.fromCharCode.apply(null, new Uint8Array(rawAuth)));
    }
  }

  const payload = {
    endpoint: subscription.endpoint,
    keys: {
      p256dh: key,
      auth: auth
    }
  };

  try {
    const res = await fetch('/auth/push-subscribe', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfToken()
      },
      body: JSON.stringify(payload)
    });
    const result = await res.json();
    return result.status === 'success';
  } catch (err) {
    console.error('[Push] Failed to post push subscription to backend:', err);
    return false;
  }
}

// Initialize Push and PWA handling
let deferredPrompt = null;

document.addEventListener('DOMContentLoaded', async () => {
  const installBtn = document.getElementById('btn-install-pwa');
  const enablePushBtn = document.getElementById('btn-enable-push');
  const vapidMeta = document.querySelector('meta[name="vapid-public-key"]');
  const vapidPublicKey = vapidMeta ? vapidMeta.getAttribute('content') : '';

  // 1. Intercept PWA Install Prompt
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    if (installBtn) {
      installBtn.classList.remove('hidden');
    }
  });

  if (installBtn) {
    installBtn.addEventListener('click', async () => {
      if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        if (outcome === 'accepted') {
          installBtn.classList.add('hidden');
        }
        deferredPrompt = null;
      }
    });
  }

  // 2. Service Worker Registration
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    if (enablePushBtn) enablePushBtn.classList.add('hidden');
    return;
  }

  try {
    const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });

    // Check existing push subscription
    let subscription = await registration.pushManager.getSubscription();

    // Update UI status
    const updatePushUiState = (isSubscribed) => {
      if (!enablePushBtn) return;
      if (isSubscribed) {
        enablePushBtn.classList.add('bg-emerald-50', 'text-emerald-700', 'border-emerald-200');
        enablePushBtn.classList.remove('bg-indigo-50', 'text-indigo-700', 'border-indigo-200');
        enablePushBtn.setAttribute('title', 'Notifikasi Push Aktif');
        enablePushBtn.innerHTML = `
          <svg class="w-4 h-4 mr-1 text-emerald-600 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
          </svg>
          <span>Push On</span>
        `;
      } else {
        enablePushBtn.classList.remove('bg-emerald-50', 'text-emerald-700', 'border-emerald-200');
        enablePushBtn.classList.add('bg-indigo-50', 'text-indigo-700', 'border-indigo-200');
        enablePushBtn.setAttribute('title', 'Klik untuk mengaktifkan notifikasi push di perangkat ini');
        enablePushBtn.innerHTML = `
          <svg class="w-4 h-4 mr-1 text-indigo-600 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path>
          </svg>
          <span>Aktifkan Push</span>
        `;
      }
    };

    // CRITICAL: Always synchronize existing subscription to current logged-in user!
    if (subscription) {
      updatePushUiState(true);
      await sendSubscriptionToBackend(subscription);
    } else {
      updatePushUiState(false);
      // Auto-subscribe if permission was previously granted
      if (Notification.permission === 'granted' && vapidPublicKey) {
        try {
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
          });
          await sendSubscriptionToBackend(subscription);
          updatePushUiState(true);
        } catch (err) {
          console.warn('[Push] Auto-subscribe renewal warning:', err);
        }
      }
    }

    // Explicit Click handler: Subscribe
    if (enablePushBtn) {
      enablePushBtn.addEventListener('click', async () => {
        const existingSub = await registration.pushManager.getSubscription();
        if (existingSub) {
          alert('Notifikasi push sudah aktif di perangkat ini untuk akun Anda.');
          return;
        }

        if (!vapidPublicKey) {
          alert('Kunci publik Push Service belum tersedia di server.');
          return;
        }

        try {
          const permission = await Notification.requestPermission();
          if (permission !== 'granted') {
            alert('Izin notifikasi tidak diberikan oleh browser. Pastikan izin notifikasi aktif di pengaturan browser / ponsel Anda.');
            return;
          }

          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapidPublicKey)
          });

          const success = await sendSubscriptionToBackend(subscription);
          if (success) {
            updatePushUiState(true);
            alert('Notifikasi push berhasil diaktifkan untuk akun ini!');
          } else {
            alert('Berhasil meminta izin browser, namun gagal mendaftarkan token ke server.');
          }
        } catch (err) {
          console.error('[Push] Error during push opt-in:', err);
          alert('Terjadi kesalahan saat mengaktifkan push: ' + err.message);
        }
      });
    }

  } catch (err) {
    console.error('[Push] ServiceWorker registration failed:', err);
  }
});

