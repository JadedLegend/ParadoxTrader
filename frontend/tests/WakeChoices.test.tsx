import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import WakeChoices from '../src/views/WakeChoices'
import { fixture } from '../src/preview/readFixture'

const escapePattern = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const startsWith = (text: string) => new RegExp(`^${escapePattern(text)}`)

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="test-location">{location.pathname}{location.search}</div>
}

function renderChoices(initialEntry = '/choices') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes><Route path="/choices" element={<WakeChoices />} /></Routes>
      <LocationProbe />
    </MemoryRouter>,
  )
}

async function openChoice(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('button', { name: 'Open example choice window' }))
  const dialog = screen.getByRole('dialog', { name })
  expect(dialog.tagName).toBe('DIALOG')
  expect(dialog.hasAttribute('open')).toBe(true)
  expect(dialog.getAttribute('aria-labelledby')).toBe('choice-title')
  expect(dialog.getAttribute('aria-describedby')).toBe('choice-description')
  expect(within(dialog).getByText(/does not wake an agent or carry out an activity/)).toBeTruthy()
  return dialog
}

function expectNoReceipts() {
  const status = screen.getByRole('status')
  expect(within(status).getByText(/No demonstrations yet/)).toBeTruthy()
  expect(within(status).queryByText(/Operator demonstration/)).toBeNull()
}

describe('actual fixture WakeChoices page', () => {
  it.each(fixture.agents)('navigates to $agent_id by its named button and records rest locally', async agent => {
    const user = userEvent.setup()
    const before = structuredClone(fixture)
    renderChoices()
    await user.click(screen.getByRole('button', { name: startsWith(agent.name) }))
    expect(screen.getByTestId('test-location').textContent).toBe(`/choices?agent=${agent.agent_id}`)
    expect(screen.getByRole('button', { name: startsWith(agent.name) }).getAttribute('aria-pressed')).toBe('true')
    expect(screen.getAllByRole('button', { pressed: true })).toHaveLength(1)
    expect(screen.getByRole('heading', { name: agent.name })).toBeTruthy()
    expectNoReceipts()
    const dialog = await openChoice(user, agent.name)
    const window = fixture.windows[agent.agent_id].phase0
    expect(within(dialog).getAllByRole('radio').map(radio => (radio as HTMLInputElement).value)).toEqual(window.choices.map(choice => choice.action))
    const record = within(dialog).getByRole('button', { name: 'Record demonstration' }) as HTMLButtonElement
    expect(record.disabled).toBe(true)
    const rest = window.choices.find(choice => choice.action === 'rest')!
    await user.click(within(dialog).getByRole('radio', { name: startsWith(rest.label) }))
    expect(record.disabled).toBe(false)
    expect((within(dialog).getByRole('radio', { name: startsWith(rest.label) }) as HTMLInputElement).checked).toBe(true)
    await user.click(record)
    expect(screen.queryByRole('dialog')).toBeNull()
    const status = screen.getByRole('status')
    expect(within(status).getByText(agent.name)).toBeTruthy()
    expect(within(status).getByText(rest.label)).toBeTruthy()
    expect(within(status).getByText(/Operator demonstration/)).toBeTruthy()
    const after = Math.min(window.max_hrv, window.hrv - rest.hrv_cost)
    expect(within(status).getByText(`${window.hrv.toFixed(1)} → ${after.toFixed(1)}`)).toBeTruthy()
    expect(within(status).getByText('Simulated HRV estimate only')).toBeTruthy()
    // Recording is not a resource debit or recovery in the shared fixture.
    expect(screen.getByText(`${window.hrv.toFixed(1)} / ${window.max_hrv.toFixed(1)} simulated HRV`)).toBeTruthy()
    expect(fixture).toEqual(before)
  })

  it('moves through all seven URL-selected identities without losing the chosen scenario', async () => {
    const user = userEvent.setup()
    renderChoices('/choices?agent=oracle')
    const scenario = screen.getByRole('combobox', { name: 'Inspect a scenario' })
    await user.selectOptions(scenario, 'phase3')
    for (const agent of fixture.agents) {
      await user.click(screen.getByRole('button', { name: startsWith(agent.name) }))
      expect(screen.getByTestId('test-location').textContent).toBe(`/choices?agent=${agent.agent_id}`)
      expect((scenario as HTMLSelectElement).value).toBe('phase3')
      const dialog = await openChoice(user, agent.name)
      const window = fixture.windows[agent.agent_id].phase3
      expect(within(dialog).getByText('Phase 3')).toBeTruthy()
      expect(within(dialog).getAllByRole('radio').map(radio => (radio as HTMLInputElement).value)).toEqual(window.choices.map(choice => choice.action))
      await user.click(within(dialog).getByRole('button', { name: 'Leave undecided' }))
      expectNoReceipts()
    }
  })

  it('honors an initial agent query and safely resolves an unknown query to the first fixture identity', () => {
    const initial = renderChoices('/choices?agent=paradox_hunter')
    expect(screen.getByRole('heading', { name: 'The Paradox Hunter' })).toBeTruthy()
    initial.unmount()
    renderChoices('/choices?agent=not_an_agent')
    expect(screen.getByRole('heading', { name: 'The Tempest' })).toBeTruthy()
    expectNoReceipts()
  })

  it('handles native Escape/cancel without creating a receipt', async () => {
    const user = userEvent.setup()
    renderChoices()
    const dialog = await openChoice(user, 'The Tempest')
    await user.click(within(dialog).getByRole('radio', { name: /^Quiet rest/ }))
    await user.keyboard('{Escape}')
    // jsdom has no native Escape default action. Dispatch the cancel event that
    // an actual browser emits, rather than adding fake key handlers to runtime.
    fireEvent(dialog, new Event('cancel', { bubbles: false, cancelable: true }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(dialog.hasAttribute('open')).toBe(false)
    expectNoReceipts()
  })

  it.each(['Leave undecided', 'Close choice window'])('%s discards even a selected option', async buttonName => {
    const user = userEvent.setup()
    renderChoices()
    let dialog = await openChoice(user, 'The Tempest')
    await user.click(within(dialog).getByRole('radio', { name: /^Quiet rest/ }))
    await user.click(within(dialog).getByRole('button', { name: buttonName }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expectNoReceipts()
    dialog = await openChoice(user, 'The Tempest')
    expect((within(dialog).getByRole('button', { name: 'Record demonstration' }) as HTMLButtonElement).disabled).toBe(true)
    expect(within(dialog).getAllByRole('radio').every(radio => !(radio as HTMLInputElement).checked)).toBe(true)
  })

  it.each(fixture.agents)('$agent_id phase 0 excludes peers, while interval has only optional quiet rest', async agent => {
    const user = userEvent.setup()
    renderChoices(`/choices?agent=${agent.agent_id}`)
    let dialog = await openChoice(user, agent.name)
    const phase0Actions = within(dialog).getAllByRole('radio').map(radio => (radio as HTMLInputElement).value)
    for (const action of ['forum_post', 'direct_message', 'analyze_consensus']) expect(phase0Actions).not.toContain(action)
    await user.click(within(dialog).getByRole('button', { name: 'Leave undecided' }))
    await user.selectOptions(screen.getByRole('combobox', { name: 'Inspect a scenario' }), 'interval')
    expect(screen.getByText('Quiet interval example')).toBeTruthy()
    dialog = await openChoice(user, agent.name)
    expect(within(dialog).getAllByRole('radio')).toHaveLength(1)
    const rest = within(dialog).getByRole('radio', { name: /^Quiet rest — no reflection required/ }) as HTMLInputElement
    expect(rest.value).toBe('rest')
    expect(rest.checked).toBe(false)
    expect((within(dialog).getByRole('button', { name: 'Record demonstration' }) as HTMLButtonElement).disabled).toBe(true)
    expect(within(dialog).queryByRole('textbox')).toBeNull()
    expect(within(dialog).getByText('No action-model call or journal required.')).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: 'Leave undecided' }))
    expectNoReceipts()
  })

  it('resets stale selection on scenario changes and records against the visible agent/window', async () => {
    const user = userEvent.setup()
    renderChoices('/choices?agent=tempest')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Inspect a scenario' }), 'phase1')
    await user.click(screen.getByRole('button', { name: startsWith('The Weaver') }))
    let dialog = await openChoice(user, 'The Weaver')
    const window = fixture.windows.weaver.phase1
    const choice = window.choices.find(item => item.action !== 'rest')!
    await user.click(within(dialog).getByRole('radio', { name: startsWith(choice.label) }))
    await user.click(within(dialog).getByRole('button', { name: 'Record demonstration' }))
    const status = screen.getByRole('status')
    expect(within(status).getByText('The Weaver')).toBeTruthy()
    expect(within(status).getByText(choice.label)).toBeTruthy()
    expect(within(status).getByText(`${window.hrv.toFixed(1)} → ${(window.hrv - choice.hrv_cost).toFixed(1)}`)).toBeTruthy()
    await user.selectOptions(screen.getByRole('combobox', { name: 'Inspect a scenario' }), 'interval')
    dialog = await openChoice(user, 'The Weaver')
    expect(within(dialog).getAllByRole('radio')).toHaveLength(1)
    expect((within(dialog).getByRole('button', { name: 'Record demonstration' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('clears local logs and loses them on unmount/reload without browser-storage persistence', async () => {
    const user = userEvent.setup()
    const storageWrite = vi.spyOn(Storage.prototype, 'setItem')
    try {
      let mounted = renderChoices()
      expect((screen.getByRole('button', { name: 'Clear' }) as HTMLButtonElement).disabled).toBe(true)
      async function recordRest() {
        const dialog = await openChoice(user, 'The Tempest')
        await user.click(within(dialog).getByRole('radio', { name: /^Quiet rest/ }))
        await user.click(within(dialog).getByRole('button', { name: 'Record demonstration' }))
      }
      await recordRest()
      expect((screen.getByRole('button', { name: 'Clear' }) as HTMLButtonElement).disabled).toBe(false)
      await user.click(screen.getByRole('button', { name: 'Clear' }))
      expectNoReceipts()
      await recordRest()
      mounted.unmount()
      // A new component tree models reload without jsdom's unsupported navigation.
      mounted = renderChoices('/choices?agent=tempest')
      expectNoReceipts()
      expect((screen.getByRole('button', { name: 'Clear' }) as HTMLButtonElement).disabled).toBe(true)
      expect(storageWrite).not.toHaveBeenCalled()
      expect(localStorage.length).toBe(0)
      expect(sessionStorage.length).toBe(0)
      mounted.unmount()
    } finally {
      storageWrite.mockRestore()
    }
  })

  it('announces fixture, funding, and planned scheduling scopes without claiming agent work', () => {
    renderChoices()
    expect(screen.getByText(/runtime-derived example menus and sample resource states—not agent activity/)).toBeTruthy()
    expect(screen.getByText(/No schedule is running/)).toBeTruthy()
    expect(screen.getByText(/not money, provider credits/)).toBeTruthy()
    expect(screen.getByText(/creator’s available funding/)).toBeTruthy()
    expect(screen.getByText(/None are activated here/)).toBeTruthy()
    expect(screen.getByText(/not agent decisions, journals, forecasts, or orders/)).toBeTruthy()
  })
})
