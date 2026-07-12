import { sleep } from 'k6';
import { dataset } from './lib/config.js';
import { listTargets, previewProduct, resetSimulator } from './lib/api.js';
import { syntheticProduct } from './lib/data.js';
import { buildSummary } from './lib/summary.js';

export const options = {
  vus: 5,
  duration: '1m',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
    checks: ['rate>0.99'],
  },
};

export function setup() {
  resetSimulator();
}

export default function () {
  const user = dataset[(__VU - 1) % dataset.length];
  listTargets(user);
  previewProduct(user, syntheticProduct(__VU * 100000 + __ITER));
  sleep(1);
}

export function handleSummary(data) {
  return buildSummary(data, 'smoke-summary');
}
