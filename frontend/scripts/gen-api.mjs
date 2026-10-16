import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'

const spec = new URL('../../contracts/openapi.json', import.meta.url).pathname
if (!existsSync(spec)) {
  console.error('contracts/openapi.json neexistuje (kontrakt ještě není vydán). Spusťte `make contract`.')
  process.exit(1)
}
const r = spawnSync('pnpm', ['exec', 'openapi-typescript', spec, '-o', 'src/lib/api/schema.d.ts'], {
  stdio: 'inherit',
})
process.exit(r.status ?? 1)
