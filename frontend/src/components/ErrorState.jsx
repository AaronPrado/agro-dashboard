/**
 * Pinta un fallo de carga con su salida: reintentar sin recargar la página.
 *
 * `error.message` es el mensaje que redacta la capa de API —"No se pudo
 * contactar con la API" o "La API respondió con 500"—, así que el componente
 * distingue la sección que falló sin tener que interpretar el fallo.
 */
export function ErrorState({ title, error, onRetry }) {
  return (
    <div className="status status--error" role="alert">
      <strong>{title}</strong>
      <p className="status__detail">{error.message}</p>
      <button type="button" onClick={onRetry}>
        Reintentar
      </button>
    </div>
  )
}
