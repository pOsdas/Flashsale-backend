import http from 'k6/http';
import { check } from 'k6';
import {
  BASE_URL,
  LOAD_TEST_KEY,
  LOAD_CONTROL_KEY,
  SIMULATOR_URL,
} from './config.js';
import {
  businessFailures,
  businessSuccess,
  checkNowDuration,
  checkedTargets,
  createDuration,
  createdTargets,
  listDuration,
  previewDuration,
  telegramUpdatesInjected,
} from './metrics.js';

export function headersFor(user) {
  return {
    'Content-Type': 'application/json',
    'X-Load-Test-Key': LOAD_TEST_KEY,
    'X-Load-Test-User-ID': String(user.id),
  };
}

function record(response, name, expectedStatuses) {
  const ok = check(response, {
    [`${name}: expected status`]: (r) => expectedStatuses.includes(r.status),
  });
  if (ok) businessSuccess.add(1, { operation: name });
  else businessFailures.add(1, { operation: name, status: String(response.status) });
  return ok;
}

export function listTargets(user, pageSize = 20) {
  const response = http.get(
    `${BASE_URL}/api/v1/monitoring/targets/?page_size=${pageSize}`,
    { headers: headersFor(user), tags: { operation: 'list_targets' } },
  );
  listDuration.add(response.timings.duration);
  record(response, 'list_targets', [200]);
  if (response.status !== 200) return [];
  try {
    const body = response.json();
    return Array.isArray(body) ? body : (body.results || []);
  } catch (_) {
    businessFailures.add(1, { operation: 'list_targets_json' });
    return [];
  }
}

export function previewProduct(user, product) {
  const response = http.post(
    `${BASE_URL}/api/v1/monitoring/products/preview/`,
    JSON.stringify({ marketplace: product.marketplace, url: product.url }),
    { headers: headersFor(user), tags: { operation: 'preview_product', marketplace: product.marketplace } },
  );
  previewDuration.add(response.timings.duration);
  record(response, 'preview_product', [200]);
  if (response.status !== 200) return null;
  try { return response.json('product'); } catch (_) { return null; }
}

export function createTarget(user, product, preview = null) {
  const payload = {
    marketplace: product.marketplace,
    role: product.role || 'competitor',
    url: product.url,
    check_interval_minutes: product.check_interval_minutes || 15,
  };
  if (preview && preview.external_id) payload.external_id = preview.external_id;
  const response = http.post(
    `${BASE_URL}/api/v1/monitoring/targets/`,
    JSON.stringify(payload),
    { headers: headersFor(user), tags: { operation: 'create_target', marketplace: product.marketplace } },
  );
  createDuration.add(response.timings.duration);
  const ok = record(response, 'create_target', [201]);
  if (ok) createdTargets.add(1);
  if (!ok) return null;
  try { return response.json(); } catch (_) { return null; }
}

export function checkNow(user, targetID) {
  const response = http.post(
    http.url`${BASE_URL}/api/v1/monitoring/targets/${targetID}/check-now/`,
    null,
    {
      headers: headersFor(user),
      tags: {
        operation: 'check_now',
      },
    },
  );

  checkNowDuration.add(response.timings.duration);
  const ok = record(response, 'check_now', [200, 202, 409]);

  if (ok && response.status !== 409) {
    checkedTargets.add(1);
  }

  return response;
}

export function patchTarget(user, targetID, minutes) {
  const response = http.patch(
    http.url`${BASE_URL}/api/v1/monitoring/targets/${targetID}/`,
    JSON.stringify({
      check_interval_minutes: minutes,
    }),
    {
      headers: headersFor(user),
      tags: {
        operation: 'patch_target',
      },
    },
  );

  record(response, 'patch_target', [200]);
  return response;
}

export function pauseOrResume(user, target, pause) {
  const action = pause ? 'pause' : 'resume';

  const response = http.post(
    http.url`${BASE_URL}/api/v1/monitoring/targets/${target.id}/${action}/`,
    null,
    {
      headers: headersFor(user),
      tags: {
        operation: action,
      },
    },
  );

  record(response, action, [200]);
  return response;
}

export function deleteTarget(user, targetID) {
  const response = http.del(
    http.url`${BASE_URL}/api/v1/monitoring/targets/${targetID}/`,
    null,
    {
      headers: headersFor(user),
      tags: {
        operation: 'delete_target',
      },
    },
  );

  record(response, 'delete_target', [204, 404]);
  return response;
}

export function setSimulatorProfile(name) {
  return http.post(
    `${SIMULATOR_URL}/__control/profile?name=${encodeURIComponent(name)}`,
    null,
    { headers: { 'X-Load-Control-Key': LOAD_CONTROL_KEY }, tags: { operation: 'simulator_profile' } },
  );
}

export function resetSimulator() {
  return http.post(
    `${SIMULATOR_URL}/__control/reset`,
    null,
    { headers: { 'X-Load-Control-Key': LOAD_CONTROL_KEY }, tags: { operation: 'simulator_reset' } },
  );
}

export function priceShock(percent) {
  return http.post(
    `${SIMULATOR_URL}/__control/price-shock?percent=${percent}`,
    null,
    { headers: { 'X-Load-Control-Key': LOAD_CONTROL_KEY }, tags: { operation: 'price_shock' } },
  );
}

export function enqueueTelegramUpdate(user, text) {
  const response = http.post(
    `${SIMULATOR_URL}/__control/telegram-updates`,
    JSON.stringify({ chat_id: `load-${user.id}`, text }),
    {
      headers: {
        'Content-Type': 'application/json',
        'X-Load-Control-Key': LOAD_CONTROL_KEY,
      },
      tags: { operation: 'telegram_update_inject' },
    },
  );
  const ok = record(response, 'telegram_update_inject', [202]);
  if (ok) telegramUpdatesInjected.add(1);
  return response;
}
