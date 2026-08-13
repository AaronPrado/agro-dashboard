export function BatchPicker({ batches, value, onChange }) {
  // Se agrupa por el código de la explotación y no por su nombre: el nombre no
  // es único y dos explotaciones homónimas quedarían fundidas en un solo grupo.
  const byFarm = new Map()

  for (const batch of batches) {
    if (!byFarm.has(batch.farm_code)) {
      byFarm.set(batch.farm_code, { name: batch.farm_name, batches: [] })
    }
    byFarm.get(batch.farm_code).batches.push(batch)
  }

  return (
    <div className="picker">
      <label className="picker__label" htmlFor="batch">
        Lote
      </label>
      <select id="batch" value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Elige un lote…</option>
        {[...byFarm].map(([farmCode, farm]) => (
          <optgroup key={farmCode} label={`${farm.name} (${farmCode})`}>
            {farm.batches.map((batch) => (
              <option key={batch.id} value={batch.id}>
                {batch.name} · {batch.active_animals} animales
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}
