import { sleep } from 'k6';
import { dataset, integerEnv } from './lib/config.js';
import { listTargets, previewProduct, resetSimulator, setSimulatorProfile } from './lib/api.js';
import { syntheticProduct } from './lib/data.js';
import { buildSummary } from './lib/summary.js';

const startRate = integerEnv('START_RATE', 10);
const maxRate = integerEnv('MAX_RATE', 500);
const preAllocated = integerEnv('PREALLOCATED_VUS', 200);
const maxVUs = integerEnv('MAX_VUS', 3000);

export const options = {
  scenarios: {
    breakpoint: {
      executor: 'ramping-arrival-rate',
      startRate,
      timeUnit: '1s',
      preAllocatedVUs: preAllocated,
      maxVUs,
      stages: [
        { target: Math.round(maxRate * 0.2), duration: '3m' },
        { target: Math.round(maxRate * 0.4), duration: '3m' },
        { target: Math.round(maxRate * 0.6), duration: '3m' },
        { target: Math.round(maxRate * 0.8), duration: '3m' },
        { target: maxRate, duration: '5m' },
      ],
      tags: { test_mode: 'breakpoint' },
    },
  },
  thresholds: {
    http_req_failed: [{ threshold: 'rate<0.05', abortOnFail: true, delayAbortEval: '2m' }],
    http_req_duration: [{ threshold: 'p(95)<2000', abortOnFail: true, delayAbortEval: '3m' }],
    dropped_iterations: ['count==0'],
  },
};

export function setup() {
  resetSimulator();
  setSimulatorProfile('fast');
}

export default function () {
  const user = dataset[(__VU + __ITER) % dataset.length];
  if ((__ITER + __VU) % 4 === 0) {
    previewProduct(user, syntheticProduct(__VU * 100000 + __ITER));
  } else {
    listTargets(user);
  }
  sleep(0.05);
}

export function handleSummary(data) {
  return buildSummary(data, 'breakpoint-summary');
}
