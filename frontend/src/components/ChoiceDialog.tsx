import { useEffect, useRef, useState } from 'react'
import type { ActionChoice, ChoiceWindow } from '../data/contracts'
import { describeCost } from '../preview/choiceState'

interface Props {
  name: string
  window: ChoiceWindow
  onChoose: (choice: ActionChoice) => void
  onClose: () => void
}

export default function ChoiceDialog({ name, window, onChoose, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [selected, setSelected] = useState<string>('')
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    return () => { element?.close() }
  }, [])
  const chosen = window.choices.find(choice => choice.action === selected)

  return (
    <dialog ref={dialog} className="choice-dialog" aria-labelledby="choice-title" aria-describedby="choice-description"
      onCancel={event => { event.preventDefault(); onClose() }}>
      <div className="dialog-heading">
        <div><span className="eyebrow">Example wake window</span><h2 id="choice-title">{name}</h2></div>
        <button type="button" className="btn btn-ghost" onClick={onClose} aria-label="Close choice window">Close</button>
      </div>
      <p id="choice-description" className="page-sub">Inspect a choice as the operator. This does not wake an agent or carry out an activity.</p>
      <div className="window-summary"><span>Phase {window.phase}</span><span>{window.hrv.toFixed(1)} / {window.max_hrv.toFixed(1)} simulated HRV</span></div>
      {window.in_interval && <p className="notice">In the actual interval path, quiet rest happens without a picker or reflection. This window only illustrates that behavior.</p>}
      <fieldset className="choice-list">
        <legend>Available example choices</legend>
        {window.choices.map(choice => (
          <label key={choice.action} className={`choice-option ${selected === choice.action ? 'chosen' : ''}`}>
            <input type="radio" name="wake-action" value={choice.action} checked={selected === choice.action}
              onChange={() => setSelected(choice.action)} />
            <span><strong>{choice.label}</strong><small>{describeCost(choice)}</small>
              {choice.action === 'rest' && <small>No action-model call or journal required.</small>}
            </span>
          </label>
        ))}
      </fieldset>
      <p className="dialog-footnote">The actual runtime selects its own menu and choice. No financial allowance or work quota is represented by these points.</p>
      <div className="dialog-actions">
        <button type="button" className="btn btn-ghost" onClick={onClose}>Leave undecided</button>
        <button type="button" className="btn btn-primary" disabled={!chosen} onClick={() => { if (chosen) onChoose(chosen) }}>
          Record demonstration
        </button>
      </div>
    </dialog>
  )
}
