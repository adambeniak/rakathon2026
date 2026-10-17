import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, vi } from 'vitest'
import { TextSizeToggle } from './TextSizeToggle'

afterEach(() => {
  vi.restoreAllMocks()
  try {
    window.localStorage.clear()
  } catch {
    // ignore
  }
  document.documentElement.style.fontSize = ''
})

describe('TextSizeToggle', () => {
  it('is a pressed/unpressed button named "Větší písmo" that scales the root font size', async () => {
    render(<TextSizeToggle />)
    const button = screen.getByRole('button', { name: 'Větší písmo' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(document.documentElement.style.fontSize).toBe('')

    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.style.fontSize).toBe('112.5%')

    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(document.documentElement.style.fontSize).toBe('')
  })

  it('remembers the choice for the next page load', async () => {
    const { unmount } = render(<TextSizeToggle />)
    await userEvent.click(screen.getByRole('button', { name: 'Větší písmo' }))
    unmount()
    document.documentElement.style.fontSize = ''

    render(<TextSizeToggle />)
    expect(screen.getByRole('button', { name: 'Větší písmo' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(document.documentElement.style.fontSize).toBe('112.5%')
  })

  it('still works when storage throws', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    render(<TextSizeToggle />)
    const button = screen.getByRole('button', { name: 'Větší písmo' })
    expect(button).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    expect(document.documentElement.style.fontSize).toBe('112.5%')
  })
})
