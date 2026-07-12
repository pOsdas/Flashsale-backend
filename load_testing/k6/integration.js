import { sleep } from 'k6';
import { dataset, integrationProducts, integerEnv } from './lib/config.js';
import { checkNow, createTarget, listTargets, previewProduct } from './lib/api.js';
import { choose } from './lib/data.js';
import { buildSummary } from './lib/summary.js';

const vus = integerEnv('INTEGRATION_VUS', 20);

export const options = {
  scenarios: {
    real_integrations: {
      executor: 'constant-vus',
      vus,
      duration: __ENV.INTEGRATION_DURATION || '10m',
      tags: { test_mode: 'integration' },
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.10'],
    http_req_duration: ['p(95)<15000'],
    checks: ['rate>0.90'],
  },
};

function findExistingTarget(targets, product) {
  return targets.find((target) => (
    target.marketplace === product.marketplace
    && String(target.external_id || '') === String(product.external_id || '')
  ));
}

export default function () {
  if (integrationProducts.length === 0) {
    throw new Error('integration-products.json is empty; start the Integration Lab without -SkipCatalogCollection');
  }

  const user = dataset[(__VU - 1) % dataset.length];
  const product = choose(integrationProducts, __VU * 10000 + __ITER);
  const roll = Math.random();

  if (roll < 0.55) {
    previewProduct(user, product);
  } else if (roll < 0.75) {
    listTargets(user);
  } else if (roll < 0.90) {
    const targets = listTargets(user, 100);
    const existing = findExistingTarget(targets, product);
    if (existing) {
      checkNow(user, existing.id);
    } else {
      const preview = previewProduct(user, product);
      if (preview) createTarget(user, product, preview);
    }
  } else {
    const targets = listTargets(user, 100);
    if (targets.length > 0) {
      checkNow(user, targets[(__VU + __ITER) % targets.length].id);
    }
  }

  sleep(5 + Math.random() * 15);
}

export function handleSummary(data) {
  return buildSummary(data, 'integration-summary');
}
