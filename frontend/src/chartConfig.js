export function chartConfigForRenderer(chart) {
  if (!chart?.config) return null
  return { ...chart.config, type: chart.type || chart.config.type }
}