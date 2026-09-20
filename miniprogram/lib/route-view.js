/** A browsing selection only: it never records a visit or claims navigation. */
function routeView(route, selectedId) {
  const ids = new Set();
  const stops = (Array.isArray(route.stops) ? route.stops : [])
    .filter((stop) => {
      if (!stop || !stop.id || !stop.place || !stop.place.id || !Number.isSafeInteger(stop.order) || stop.order < 0 || ids.has(stop.id)) return false;
      ids.add(stop.id); return true;
    })
    .sort((left, right) => left.order - right.order || String(left.id).localeCompare(String(right.id)))
    .map((stop, index) => Object.assign({}, stop, { position: index + 1 }));
  const stopIndex = Math.max(0, stops.findIndex((stop) => stop.id === selectedId));
  return { routeStops: stops, stopIndex, activeStop: stops[stopIndex] || null };
}
module.exports = { routeView };
