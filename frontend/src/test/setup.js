import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// After each test: unmount React trees and reset the fake environment.
afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.restoreAllMocks()
})
