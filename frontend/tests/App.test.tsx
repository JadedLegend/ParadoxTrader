import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from '../src/App'
import { fixture } from '../src/preview/readFixture'

async function mountApp(path: string) {
  // App owns BrowserRouter; history is local jsdom state, not a server request.
  window.history.replaceState({}, '', path)
  const mounted = render(<App />)
  const main = screen.getByRole('main')
  await waitFor(() => expect(within(main).queryAllByText(/^Loading/)).toHaveLength(0))
  expect(within(main).queryByRole('heading', { name: 'This screen could not be displayed' })).toBeNull()
  expect(within(main).getByRole('note').textContent).toMatch(/Fixture preview.*Local agent and portfolio examples; Library reads imported source text/)
  return { ...mounted, main }
}

const routes = [
  ['/', 'Dashboard'], ['/choices', 'Room to choose'], ['/agents', 'Agents'],
  ['/library', 'Library'],
  ['/forum', 'Forum'], ['/inbox', 'Messages'], ['/queue', 'Trade Queue'], ['/config', 'Configuration'],
]

describe('App fixture-mode smoke coverage', () => {
  it.each(routes)('%s renders its local screen with all eight navigation links', async (path, title) => {
    const { main } = await mountApp(path)
    expect(within(main).getByText(title, { exact: true })).toBeTruthy()
    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    expect(within(nav).getAllByRole('link')).toHaveLength(8)
    expect(within(nav).getByRole('link', { name: 'Wake Choices' }).getAttribute('href')).toBe('/choices')
    expect(within(nav).getByRole('link', { name: 'Library' }).getAttribute('href')).toBe('/library')
  })

  it('renders no credential, Save, countdown, or trading-mode mutation controls in preview configuration', async () => {
    const { main } = await mountApp('/config')
    expect(main.querySelector('input[type="password"]')).toBeNull()
    expect(main.querySelectorAll('input, textarea')).toHaveLength(0)
    expect(within(main).queryByRole('button', { name: /save|countdown|trades execute|trades queue/i })).toBeNull()
    expect(within(main).getByText(/No secret inputs are shown/)).toBeTruthy()
    expect(within(main).getByText(/Review required \(fixture only\)/)).toBeTruthy()
    expect(within(main).getByText(/Wake interval: Unavailable/)).toBeTruthy()
    expect(within(main).getByText(/do not start a scheduler/)).toBeTruthy()
    for (const agent of fixture.agents) {
      expect(within(main).getAllByText(agent.model).length).toBeGreaterThan(0)
    }
  })

  it('disables initialization, every phase control, and every real dashboard wake', async () => {
    const { main } = await mountApp('/')
    const mutations = within(main).getAllByRole('button', { name: /^(Initialize System|Phase \d:|Wake$)/ })
    expect(mutations).toHaveLength(12)
    for (const button of mutations) expect((button as HTMLButtonElement).disabled).toBe(true)
    expect(within(main).getAllByRole('link', { name: 'Preview wake choices' })).toHaveLength(7)
    expect(within(main).getByRole('alert').textContent).toMatch(/Market data unavailable.*not connected/)
  })

  it('distinguishes confirmed-empty positions from unconfigured and failed lookups on the actual map', async () => {
    const { main } = await mountApp('/agents')
    const mapTitle = within(main).getByText('Map of Attention')
    const map = mapTitle.parentElement!
    const positionCard = (name: string) => within(map).getByText(name, { exact: true }).parentElement!.parentElement!
    expect(within(positionCard('The Siren')).getByText(/Confirmed empty — no open positions/)).toBeTruthy()
    expect(within(positionCard('The Alchemist')).getByText(/Broker account not configured — holdings unknown/)).toBeTruthy()
    expect(within(positionCard('The Weaver')).getByRole('alert').textContent).toMatch(/Position lookup failed — holdings unknown/)
    expect(within(positionCard('The Shadow')).queryByText(/Confirmed empty/)).toBeNull()
    expect(within(positionCard('The Tempest')).getByText('DEMO')).toBeTruthy()
    expect(within(main).getByText(/Unknown is not empty/)).toBeTruthy()
    for (const button of within(main).getAllByRole('button', { name: 'Wake' })) {
      expect((button as HTMLButtonElement).disabled).toBe(true)
    }
  })

  it('keeps agent journal, innermost, and identity mutation controls disabled', async () => {
    const user = userEvent.setup()
    const { main } = await mountApp('/agents')
    await user.click(within(main).getByRole('button', { name: 'The Tempest' }))
    await within(main).findByText('No journal entries yet.')
    for (const name of ['Write', 'Keep']) {
      expect((within(main).getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true)
    }
    for (const name of ['Operator journal entry', 'Innermost entry']) {
      expect((within(main).getByRole('textbox', { name }) as HTMLTextAreaElement).disabled).toBe(true)
    }
    await user.click(within(main).getByRole('button', { name: 'Self-Definition' }))
    const revise = await within(main).findByRole('button', { name: 'Revise identity (operator)' })
    expect((revise as HTMLButtonElement).disabled).toBe(true)
    expect(within(main).queryByRole('button', { name: 'Save revision' })).toBeNull()
  })

  it.each([
    ['/forum', 'Post', 'Forum post'], ['/inbox', 'Send', 'Message content'],
  ])('%s disables the actual message composer and submit button', async (path, submit, input) => {
    const { main } = await mountApp(path)
    expect((within(main).getByRole('button', { name: submit }) as HTMLButtonElement).disabled).toBe(true)
    expect((within(main).getByRole('textbox', { name: input }) as HTMLTextAreaElement).disabled).toBe(true)
    if (path === '/forum') {
      expect(within(main).getByText(/This post was not written by an agent/)).toBeTruthy()
    } else {
      expect(within(main).getByText('No messages.')).toBeTruthy()
    }
  })

  it('renders the nested queue proposal symbol, side, quantity and thesis, but cannot approve or reject it', async () => {
    const { main } = await mountApp('/queue')
    expect(within(main).getByText('DEMO', { exact: true })).toBeTruthy()
    expect(within(main).getByText('buy', { exact: true })).toBeTruthy()
    expect(within(main).getByText((_content, element) => element?.tagName === 'SPAN' && element.textContent === 'Qty: 2')).toBeTruthy()
    expect(within(main).getByText(/Fixture only: a sample review card, not a recommendation or pending order/)).toBeTruthy()
    for (const name of ['Approve', 'Reject']) {
      expect((within(main).getByRole('button', { name }) as HTMLButtonElement).disabled).toBe(true)
    }
    const notes = within(main).getByRole('textbox', { name: 'Review notes for DEMO' }) as HTMLInputElement
    expect(notes.disabled).toBe(true)
    expect(within(main).getByText(/these are not broker orders/)).toBeTruthy()
  })
})
