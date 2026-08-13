import { formatDate } from '../format.js'
import { bandColor } from '../rationBands.js'

export function BatchRations({ rationPeriods }) {
  return (
    <>
      <h3 className="batch__section">Alimentación</h3>

      {rationPeriods.length === 0 ? (
        <p className="status">
          Sin periodos de ración en el tramo consultado. Se sitúan sobre el eje de
          producción, así que un lote sin producción no muestra ninguno; su ración vigente
          figura arriba.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th scope="col">Ración</th>
              <th scope="col">Formulada</th>
              <th scope="col">Desde</th>
              <th scope="col">Hasta</th>
            </tr>
          </thead>
          <tbody>
            {rationPeriods.map((period, index) => (
              <tr key={`${period.ration_id}-${period.date_from}`}>
                <td>
                  <span
                    className="band"
                    style={{ backgroundColor: bandColor(index) }}
                    aria-hidden="true"
                  />
                  {period.ration}
                </td>
                <td>{formatDate(period.formulated_on)}</td>
                <td>{formatDate(period.date_from)}</td>
                <td>{period.date_to === null ? 'Vigente' : formatDate(period.date_to)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
