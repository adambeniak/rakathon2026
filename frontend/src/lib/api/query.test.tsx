import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { ApiProblem, problemTitle } from './problem'
import { queryKey, useApiMutation, useApiQuery } from './query'

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return {
    qc,
    Wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    ),
  }
}

const Task = z.object({ id: z.string(), title: z.string() })

describe('queryKey', () => {
  it('starts with the feature so a feature can invalidate only its own data', () => {
    expect(queryKey('coordination', 'case-1', 'tasks')).toEqual(['coordination', 'case-1', 'tasks'])
  })
})

describe('useApiQuery', () => {
  it('returns the parsed body', async () => {
    const { Wrapper } = wrapper()
    const { result } = renderHook(
      () =>
        useApiQuery({
          key: queryKey('coordination', 'c', 'tasks'),
          schema: z.array(Task),
          fetch: async () => [{ id: 't1', title: 'CT', extra: 1 }],
        }),
      { wrapper: Wrapper },
    )
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([{ id: 't1', title: 'CT' }])
  })

  it('turns a body that violates the schema into an ApiProblem that names the field but not the value', async () => {
    const { Wrapper } = wrapper()
    const { result } = renderHook(
      () =>
        useApiQuery({
          key: queryKey('coordination', 'c', 'tasks'),
          schema: z.array(Task),
          fetch: async () => [{ id: 't1', title: 42 }],
        }),
      { wrapper: Wrapper },
    )
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.error).toBeInstanceOf(ApiProblem)
    expect(result.current.error?.detail).toBe('0.title: invalid_type')
    expect(result.current.error?.detail).not.toContain('42')
    expect(problemTitle(result.current.error)).toBe('Odpověď serveru má neočekávaný tvar')
  })

  it('passes a thrown problem through to the error state', async () => {
    const { Wrapper } = wrapper()
    const { result } = renderHook(
      () =>
        useApiQuery({
          key: queryKey('coordination', 'c', 'tasks'),
          schema: z.array(Task),
          fetch: async () => {
            throw new ApiProblem(403, 'Úkoly smí číst jen členové týmu')
          },
        }),
      { wrapper: Wrapper },
    )
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(problemTitle(result.current.error)).toBe('Úkoly smí číst jen členové týmu')
  })
})

describe('useApiMutation', () => {
  it('parses the response and invalidates only the given keys', async () => {
    const { qc, Wrapper } = wrapper()
    qc.setQueryData(queryKey('coordination', 'c', 'tasks'), [])
    qc.setQueryData(queryKey('handover', 'c'), {})
    const { result } = renderHook(
      () =>
        useApiMutation({
          mutate: async (v: { phase: string }) => ({ ok: v.phase === 'ordered' }),
          schema: z.object({ ok: z.boolean() }),
          invalidate: [queryKey('coordination', 'c')],
        }),
      { wrapper: Wrapper },
    )
    result.current.mutate({ phase: 'ordered' })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ ok: true })
    expect(qc.getQueryState(queryKey('coordination', 'c', 'tasks'))?.isInvalidated).toBe(true)
    expect(qc.getQueryState(queryKey('handover', 'c'))?.isInvalidated).toBe(false)
  })

  it('exposes the problem title of a failed write', async () => {
    const { Wrapper } = wrapper()
    const { result } = renderHook(
      () =>
        useApiMutation({
          mutate: async () => {
            throw new ApiProblem(409, 'Úkol čeká na: CT')
          },
          schema: z.unknown(),
        }),
      { wrapper: Wrapper },
    )
    result.current.mutate(undefined)
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(problemTitle(result.current.error)).toBe('Úkol čeká na: CT')
  })
})
