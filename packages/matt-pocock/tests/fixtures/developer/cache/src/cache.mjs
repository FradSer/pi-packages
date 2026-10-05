export function createCache(load) {
  const entries = new Map();
  return {
    get(key) {
      if (!entries.has(key)) entries.set(key, Promise.resolve().then(() => load(key)));
      return entries.get(key);
    }
  };
}
