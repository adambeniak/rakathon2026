import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import '@fontsource-variable/source-serif-4'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import './index.css'
import { Providers } from './app/providers'
import { createRouter } from './app/router'

async function bootstrap() {
  // Keep mocks as the development default until the remaining workflows use the backend contract.
  const mocks = import.meta.env.VITE_MOCKS === '1' || (import.meta.env.DEV && import.meta.env.VITE_MOCKS !== '0')
  if (mocks) {
    const { worker } = await import('./mocks/browser')
    await worker.start({ onUnhandledRequest: 'bypass', quiet: true })
  }
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <Providers>
        <RouterProvider router={createRouter()} />
      </Providers>
    </StrictMode>,
  )
}
void bootstrap()
