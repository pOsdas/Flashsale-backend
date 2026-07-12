import { dataset, integerEnv } from './lib/config.js';
import { enqueueTelegramUpdate, resetSimulator, setSimulatorProfile } from './lib/api.js';
import { buildSummary } from './lib/summary.js';

const rate = integerEnv('TELEGRAM_UPDATE_RATE', 20);
const preAllocatedVUs = integerEnv('TELEGRAM_PREALLOCATED_VUS', 50);
const maxVUs = integerEnv('TELEGRAM_MAX_VUS', 500);
const commands = ['/products', '/notifications', '/help'];

export const options = {
  scenarios: {
    telegram_commands: {
      executor: 'constant-arrival-rate',
      rate,
      timeUnit: '1s',
      duration: __ENV.TELEGRAM_DURATION || '10m',
      preAllocatedVUs,
      maxVUs,
      tags: { test_mode: 'telegram_bot' },
    },
  },
  thresholds: {
    'http_req_failed{operation:telegram_update_inject}': ['rate<0.01'],
    'http_req_duration{operation:telegram_update_inject}': ['p(95)<500'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

export function setup() {
  resetSimulator();
  setSimulatorProfile('fast');
}

export default function () {
  const user = dataset[(__VU + __ITER) % dataset.length];
  const command = commands[(__VU + __ITER) % commands.length];
  enqueueTelegramUpdate(user, command);
}

export function handleSummary(data) {
  return buildSummary(data, 'telegram-bot-summary');
}
