import { client, unwrap } from '@/lib/api/client'
import { queryKey, useApiMutation, useApiQuery } from '@/lib/api/query'
import { kocList, referralCreated, referralPrefill, referralSubmission, type ReferralSubmission } from './schemas'

export function multipart(parts: ReadonlyArray<readonly [string, string | File]>): FormData {
  const form = new FormData()
  // A File keeps its original name: the backend takes the document id (and the LLM cache key) from it.
  for (const [name, part] of parts) {
    if (typeof part === 'string') form.append(name, part)
    else form.append(name, part, part.name)
  }
  return form
}

export const useKocDirectory = () =>
  useApiQuery({
    key: queryKey('referral', 'kocs'),
    schema: kocList,
    fetch: async () => unwrap(await client.GET('/api/directory/kocs')),
  })

/** Reads the letter and returns the evidenced draft; nothing is stored until the GP submits. */
export const usePrefillReferral = () =>
  useApiMutation({
    mutate: async (letter: File) =>
      unwrap(
        await client.POST('/api/referrals/prefill', {
          // The contract types the binary part as `string`; the serializer sends the real File.
          body: { letter: letter as unknown as string },
          bodySerializer: () => multipart([['letter', letter]]),
        }),
      ),
    schema: referralPrefill,
    invalidate: [],
  })

export const useSubmitReferral = () =>
  useApiMutation({
    mutate: async ({ letter, submission }: { letter: File; submission: ReferralSubmission }) =>
      unwrap(
        await client.POST('/api/referrals', {
          body: { letter: letter as unknown as string, payload: '' },
          bodySerializer: () =>
            multipart([
              ['letter', letter],
              ['payload', JSON.stringify(referralSubmission.parse(submission))],
            ]),
        }),
      ),
    schema: referralCreated,
  })
