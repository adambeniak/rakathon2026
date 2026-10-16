import { newStore, type MockStore } from './cases'

export const store: MockStore = newStore()

export function resetStore(): void {
  Object.assign(store, newStore())
}
