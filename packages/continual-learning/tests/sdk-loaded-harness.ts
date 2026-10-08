/** Resolve the SDK from several concurrent callers, then report each answer. */
const { loadJevSdk, jevSdkAvailable } = await import("../extensions/jev-sdk.ts");
const callers = 8;
const answers = await Promise.all(Array.from({ length: callers }, () => loadJevSdk()));
console.log(JSON.stringify({ callers, results: answers, availableAfter: jevSdkAvailable() }));
