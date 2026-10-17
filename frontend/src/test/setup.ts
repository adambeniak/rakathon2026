import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll, expect } from 'vitest'
import * as axeMatchers from 'vitest-axe/matchers'
import { cleanup, configure } from '@testing-library/react'
import { server } from '@/mocks/server'

expect.extend(axeMatchers)

// findBy*/waitFor default to 1 s, which a parallel full run can exceed on a busy machine (#144).
configure({ asyncUtilTimeout: 5_000 })

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

if (!window.matchMedia) {
  window.matchMedia = () =>
    ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }) as unknown as MediaQueryList
}
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver
Element.prototype.scrollIntoView ??= () => {}
