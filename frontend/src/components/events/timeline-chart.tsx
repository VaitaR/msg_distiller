import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'

import type { TimelineEntry } from '../../features/events/types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

const categoryColors: Record<string, string> = {
  product: '#15839a',
  risk: '#d45d4c',
  process: '#33658a',
  marketing: '#df8c3b',
  org: '#49796b',
  unknown: '#8d99ae',
}

type TimelineDatum = {
  value: [number, number, number]
  eventId: string
  title: string
  category: string
  reviewStatus: string
  sourceId: string
  importance: number
  confidence: number
  style: { fill: string }
}

type RenderParams = {
  coordSys: {
    x: number
    y: number
    width: number
    height: number
  }
}

type RenderApi = {
  value: (dimension: number) => number
  coord: (values: [number, number]) => number[]
  size: (values: [number, number]) => number[]
  style: () => unknown
}

function buildOption(entries: TimelineEntry[]): EChartsOption {
  const categories = entries.map((entry) => entry.title)
  const data: TimelineDatum[] = entries.map((entry, index) => ({
    value: [new Date(entry.start).getTime(), new Date(entry.end ?? entry.start).getTime(), index],
    eventId: entry.event_id,
    title: entry.title,
    category: entry.category,
    reviewStatus: entry.review_status,
    sourceId: entry.source_id,
    importance: entry.importance,
    confidence: entry.confidence,
    style: { fill: categoryColors[entry.category] ?? categoryColors.unknown },
  }))

  const series = [
    {
      type: 'custom',
      renderItem: (params: RenderParams, api: RenderApi) => {
        const categoryIndex = api.value(2) as number
        const start = api.coord([api.value(0), categoryIndex])
        const end = api.coord([api.value(1), categoryIndex])
        const size = api.size([0, 1])
        const height = size[1] * 0.56
        const coordSys = params.coordSys

        return {
          type: 'rect',
          transition: ['shape'],
          shape: echarts.graphic.clipRectByRect(
            {
              x: start[0],
              y: start[1] - height / 2,
              width: Math.max(end[0] - start[0], 8),
              height,
            },
            {
              x: coordSys.x,
              y: coordSys.y,
              width: coordSys.width,
              height: coordSys.height,
            },
          ),
          style: api.style(),
        }
      },
      encode: { x: [0, 1], y: 2 },
      data,
    },
  ] as unknown as NonNullable<EChartsOption['series']>

  return {
    backgroundColor: 'transparent',
    grid: { left: 170, right: 40, top: 20, bottom: 40 },
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const point = (Array.isArray(params)
          ? params[0]?.data
          : (params as { data?: TimelineDatum }).data) as TimelineDatum
        return [
          `<strong>${point.title}</strong>`,
          `Category: ${point.category}`,
          `Review: ${point.reviewStatus}`,
          `Source: ${point.sourceId}`,
          `Confidence: ${Math.round(point.confidence * 100)}%`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#5f6b76' },
      splitLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.08)' } },
    },
    yAxis: {
      type: 'category',
      data: categories,
      inverse: true,
      axisLabel: {
        color: '#243642',
        width: 150,
        overflow: 'truncate',
      },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series,
  }
}

export function TimelineChart({
  entries,
  onSelect,
}: {
  entries: TimelineEntry[]
  onSelect: (eventId: string) => void
}) {
  return (
    <Card data-testid="timeline-chart-card">
      <CardHeader>
        <CardTitle>Timeline</CardTitle>
        <CardDescription>Click a bar to inspect the related event.</CardDescription>
      </CardHeader>
      <CardContent>
        <ReactECharts
          className="timeline-chart"
          option={buildOption(entries)}
          style={{ height: `${Math.max(entries.length * 44, 420)}px`, width: '100%' }}
          onEvents={{
            click: (params: { data?: TimelineDatum }) => {
              const data = params.data as TimelineDatum | undefined
              if (data?.eventId) {
                onSelect(data.eventId)
              }
            },
          }}
        />
      </CardContent>
    </Card>
  )
}