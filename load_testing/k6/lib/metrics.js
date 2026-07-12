import { Counter, Rate, Trend } from 'k6/metrics';

export const businessFailures = new Counter('business_failures');
export const businessSuccess = new Counter('business_success');
export const journeyFailures = new Rate('journey_failures');
export const journeyDuration = new Trend('journey_duration', true);
export const previewDuration = new Trend('preview_duration', true);
export const createDuration = new Trend('target_create_duration', true);
export const checkNowDuration = new Trend('check_now_duration', true);
export const listDuration = new Trend('target_list_duration', true);
export const createdTargets = new Counter('created_targets');
export const checkedTargets = new Counter('checked_targets');

export const telegramUpdatesInjected = new Counter('telegram_updates_injected');
