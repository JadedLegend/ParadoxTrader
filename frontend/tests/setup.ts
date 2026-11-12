import { afterEach, beforeEach, expect, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import axios from 'axios'

// Installed during setup (before test modules import the application). A caught
// transport error still fails the afterEach assertions, so fallback is not hidden.
const blockedFetch = vi.fn(() => {
  throw new Error('Forbidden HTTP: global fetch was called in a fixture test')
})
vi.stubGlobal('fetch', blockedFetch)
const blockedXHR = vi.spyOn(XMLHttpRequest.prototype, 'send').mockImplementation(() => {
  throw new Error('Forbidden HTTP: XMLHttpRequest.send was called in a fixture test')
})
const blockedAxios = vi.spyOn(axios.Axios.prototype, 'request').mockImplementation(() => {
  throw new Error('Forbidden HTTP: Axios.request was called in a fixture test')
})

// The existing forum scrolls to its final post; jsdom has no layout engine.
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  configurable: true,
  value() {},
})

// jsdom does not implement the browser's modal top layer. Keep this shim minimal:
// accessibility queries see a native dialog only when its open attribute is set.
Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: {
    configurable: true,
    value(this: HTMLDialogElement) { this.setAttribute('open', '') },
  },
  close: {
    configurable: true,
    value(this: HTMLDialogElement) { this.removeAttribute('open') },
  },
})

beforeEach(() => {
  blockedFetch.mockClear()
  blockedXHR.mockClear()
  blockedAxios.mockClear()
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  // Also catch accidental transport activity in component effect cleanup.
  cleanup()
  try {
    expect(blockedFetch, 'fixture test attempted fetch').not.toHaveBeenCalled()
    expect(blockedXHR, 'fixture test attempted XMLHttpRequest.send').not.toHaveBeenCalled()
    expect(blockedAxios, 'fixture test attempted Axios.request').not.toHaveBeenCalled()
  } finally {
    localStorage.clear()
    sessionStorage.clear()
    // Do not restore the transport guards between tests or during module loading.
    vi.unstubAllEnvs()
  }
})
