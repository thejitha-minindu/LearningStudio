// Windows Application Control may block native SWC. This version-pinned workaround
// selects the installed official WASM package; no security controls are disabled.
// Next 16.3.6's ordinary package-name WASM fallback does not resolve correctly here.
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const env = { ...process.env, NEXT_TELEMETRY_DISABLED: '1' };
if (process.platform === 'win32') {
  env.NEXT_TEST_WASM_DIR = path.dirname(require.resolve('@next/swc-wasm-nodejs'));
}
const result = spawnSync(process.execPath, [require.resolve('next/dist/bin/next'), ...process.argv.slice(2)], { stdio: 'inherit', env });
if (result.error) { console.error(result.error.message); process.exit(1); }
process.exit(result.status ?? 1);
