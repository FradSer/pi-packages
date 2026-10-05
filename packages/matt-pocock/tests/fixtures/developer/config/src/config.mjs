export function parseConfig(env) {
  const input = env;
  let enabled;
  if (input.FEATURE_ENABLED === undefined) { enabled = false; }
  else { if (input.FEATURE_ENABLED === 'true') { enabled = true; }
  else { if (input.FEATURE_ENABLED === 'false') { enabled = false; }
  else { throw new Error('FEATURE_ENABLED must be true or false'); } } }
  const portText = input.PORT === undefined ? '3000' : input.PORT;
  const port = Number(portText);
  if (!/^\d+$/.test(portText) || !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('PORT must be an integer from 1 to 65535');
  }
  return {enabled, port};
}
