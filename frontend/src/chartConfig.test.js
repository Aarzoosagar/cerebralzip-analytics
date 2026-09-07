import assert from "node:assert/strict"
import test from "node:test"
import { chartConfigForRenderer } from "./chartConfig.js"

test("preserves scatter type and numeric XY points for Chart.js", () => {
  const config = chartConfigForRenderer({
    type: "scatter",
    config: {
      type: "scatter",
      data: { datasets: [{ data: [{ x: -5.2, y: 4.4 }, { x: 1.5, y: 3.8 }] }] },
    },
  })

  assert.equal(config.type, "scatter")
  assert.deepEqual(config.data.datasets[0].data, [{ x: -5.2, y: 4.4 }, { x: 1.5, y: 3.8 }])
})

test("preserves non-scatter chart types", () => {
  const config = chartConfigForRenderer({ type: "bar", config: { type: "bar", data: { labels: ["SP"], datasets: [{ data: [2] }] } } })

  assert.equal(config.type, "bar")
  assert.deepEqual(config.data.labels, ["SP"])
})