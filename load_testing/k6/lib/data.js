export function syntheticProduct(seed) {
  const index = Math.abs(seed) + 1000000;
  if (index % 2 === 0) {
    return {
      marketplace: 'wb',
      url: `https://www.wildberries.ru/catalog/${10000000 + index}/detail.aspx`,
      role: index % 5 === 0 ? 'own' : 'competitor',
      check_interval_minutes: 15,
    };
  }
  return {
    marketplace: 'ozon',
    url: `https://www.ozon.ru/product/load-test-${index}-${20000000 + index}/`,
    role: index % 5 === 0 ? 'own' : 'competitor',
    check_interval_minutes: 15,
  };
}

export function choose(array, seed) {
  if (!array || array.length === 0) return null;
  return array[Math.abs(seed) % array.length];
}
