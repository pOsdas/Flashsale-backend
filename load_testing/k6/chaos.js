import { sleep } from 'k6';
import { dataset, integerEnv } from './lib/config.js';
import {
  checkNow,
  listTargets,
  priceShock,
  resetSimulator,
  setSimulatorProfile,
} from './lib/api.js';
import { buildSummary } from './lib/summary.js';

const vus = integerEnv('CHAOS_VUS', 300);

export const options = {
  scenarios: {
    traffic: {
      executor: 'constant-vus',
      vus,
      duration: __ENV.CHAOS_DURATION || '16m',
      exec: 'traffic',
      tags: { test_mode: 'chaos' },
    },
    controller: {
      executor: 'per-vu-iterations',
      vus: 1,
      iterations: 1,
      maxDuration: __ENV.CHAOS_DURATION || '16m',
      exec: 'controller',
      tags: { test_mode: 'chaos_control' },
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.25'],
    'http_req_failed{test_mode:chaos_control}': ['rate<0.01'],
    http_req_duration: ['p(95)<5000'],
  },
};

export function setup() {
  resetSimulator();
  setSimulatorProfile('normal');
}

export function traffic() {
  const user = dataset[(__VU - 1) % dataset.length];
  const targets = listTargets(user);
  if (targets.length > 0 && Math.random() < 0.35) {
    checkNow(user, targets[(__VU + __ITER) % targets.length].id);
  }
  sleep(2 + Math.random() * 5);
}

export function controller() {
  sleep(120);
  setSimulatorProfile('slow');
  sleep(120);
  setSimulatorProfile('degraded');
  sleep(180);
  setSimulatorProfile('outage');
  sleep(60);
  setSimulatorProfile('normal');
  priceShock(-15);
  sleep(180);
  setSimulatorProfile('telegram_429');
  sleep(60);
  setSimulatorProfile('normal');
}

export function handleSummary(data) {
  return buildSummary(data, 'chaos-summary');
}
