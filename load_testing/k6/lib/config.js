import { SharedArray } from 'k6/data';

export const BASE_URL = (__ENV.BASE_URL || 'http://backend:8000').replace(/\/$/, '');
export const SIMULATOR_URL = (__ENV.SIMULATOR_URL || 'http://load_simulator:8099').replace(/\/$/, '');
export const LOAD_TEST_KEY = __ENV.LOAD_TEST_KEY || 'flashsale-local-load-key-change-me-123456789';
export const LOAD_CONTROL_KEY = __ENV.LOAD_CONTROL_KEY || 'flashsale-load-control-key';

const usersFile = __ENV.USERS_FILE || '/data/users.json';
const productsFile = __ENV.PRODUCTS_FILE || '/data/integration-products.json';

export const dataset = new SharedArray('load-test-users', function () {
  const parsed = JSON.parse(open(usersFile));
  return parsed.users || parsed;
});

export const integrationProducts = new SharedArray('integration-products', function () {
  try {
    const parsed = JSON.parse(open(productsFile));
    return parsed.products || parsed;
  } catch (_) {
    return [];
  }
});

export function integerEnv(name, fallback) {
  const value = Number.parseInt(__ENV[name] || '', 10);
  return Number.isFinite(value) ? value : fallback;
}

export function floatEnv(name, fallback) {
  const value = Number.parseFloat(__ENV[name] || '');
  return Number.isFinite(value) ? value : fallback;
}
