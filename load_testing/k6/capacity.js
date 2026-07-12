import http from 'k6/http';
import { group, sleep } from 'k6';
import { BASE_URL, dataset, integerEnv } from './lib/config.js';
import {
  checkNow,
  createTarget,
  deleteTarget,
  headersFor,
  listTargets,
  patchTarget,
  pauseOrResume,
  previewProduct,
  resetSimulator,
  setSimulatorProfile,
} from './lib/api.js';
import { syntheticProduct } from './lib/data.js';
import { journeyDuration, journeyFailures } from './lib/metrics.js';
import { buildSummary } from './lib/summary.js';

const peakVUs = integerEnv('PEAK_VUS', 1000);

export const options = {
  scenarios: {
    customers: {
      executor: 'ramping-vus',
      startVUs: 0,
      gracefulRampDown: '30s',
      stages: [
        { duration: __ENV.RAMP_UP || '5m', target: peakVUs },
        { duration: __ENV.HOLD || '15m', target: peakVUs },
        { duration: __ENV.RAMP_DOWN || '3m', target: 0 },
      ],
      exec: 'customerJourney',
      tags: { test_mode: 'capacity' },
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.01', abortOnFail: false }],
    http_req_duration: ['p(95)<750', 'p(99)<2000'],
    'http_req_duration{operation:list_targets}': ['p(95)<500'],
    'http_req_duration{operation:create_target}': ['p(95)<1500'],
    checks: ['rate>0.99'],
    journey_failures: ['rate<0.02'],
    dropped_iterations: ['count==0'],
  },
};

export function setup() {
  resetSimulator();
  setSimulatorProfile(__ENV.SIMULATOR_PROFILE || 'normal');
  return { startedAt: Date.now() };
}

function userForVU() {
  return dataset[(__VU - 1) % dataset.length];
}

function pickTarget(targets) {
  if (!targets || targets.length === 0) return null;
  return targets[(__ITER + __VU) % targets.length];
}

export function customerJourney() {
  const started = Date.now();
  const user = userForVU();
  const roll = Math.random() * 100;
  let failed = false;

  group('customer journey', () => {
    if (roll < 50) {
      listTargets(user);
      return;
    }

    if (roll < 70) {
      const product = syntheticProduct(__VU * 1000000 + __ITER);
      if (!previewProduct(user, product)) failed = true;
      return;
    }

    const targets = listTargets(user);
    const target = pickTarget(targets);

    if (roll < 85) {
      if (!target) { failed = true; return; }
      const response = checkNow(user, target.id);
      failed = ![200, 202, 409].includes(response.status);
      return;
    }

    if (roll < 87) {
      const product = syntheticProduct(900000000 + __VU * 100000 + __ITER);
      const preview = previewProduct(user, product);
      if (!preview || !createTarget(user, product, preview)) failed = true;
      return;
    }

    if (roll < 92) {
      if (!target) { failed = true; return; }
      failed = patchTarget(user, target.id, [15, 30, 60][__ITER % 3]).status !== 200;
      return;
    }

    if (roll < 96) {
      if (!target) { failed = true; return; }
      const pause = target.status !== 'paused';
      failed = pauseOrResume(user, target, pause).status !== 200;
      return;
    }

    if (roll < 99) {
      const response = http.get(`${BASE_URL}/api/v1/monitoring/alerts/?page_size=20`, {
        headers: headersFor(user), tags: { operation: 'list_alerts' },
      });
      failed = response.status !== 200;
      return;
    }

    if (target) {
      const response = deleteTarget(user, target.id);
      failed = ![204, 404].includes(response.status);
    }
  });

  journeyDuration.add(Date.now() - started);
  journeyFailures.add(failed);
  sleep(2 + Math.floor(Math.random() * 7));
}

export function handleSummary(data) {
  return buildSummary(data, 'capacity-summary');
}
