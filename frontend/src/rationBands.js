const BAND_COLORS = ['#dbe7f3', '#efe3d0', '#dfe9db', '#e8dfec']

/**
 * Color de la banda de un periodo de ración, por su posición en la serie.
 *
 * La gráfica y la tabla de raciones lo comparten para que una banda y su fila
 * se reconozcan entre sí; ambas recorren la lista que devuelve la API sin
 * reordenarla, que es lo que mantiene los índices alineados.
 */
export function bandColor(index) {
  return BAND_COLORS[index % BAND_COLORS.length]
}
