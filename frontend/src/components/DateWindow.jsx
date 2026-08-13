export function DateWindow({ dateFrom, dateTo, onDateFromChange, onDateToChange, onReset }) {
  return (
    <div className="window">
      <label className="window__label" htmlFor="date-from">
        Desde
      </label>
      <input
        id="date-from"
        type="date"
        value={dateFrom}
        max={dateTo || undefined}
        onChange={(event) => onDateFromChange(event.target.value)}
      />

      <label className="window__label" htmlFor="date-to">
        Hasta
      </label>
      <input
        id="date-to"
        type="date"
        value={dateTo}
        min={dateFrom || undefined}
        onChange={(event) => onDateToChange(event.target.value)}
      />

      <button type="button" onClick={onReset} disabled={!dateFrom && !dateTo}>
        Todo el periodo
      </button>
    </div>
  )
}
