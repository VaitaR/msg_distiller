import { useMemo } from 'react'

import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import ReactECharts from 'echarts-for-react'

import type { TimelineEntry } from '../../features/events/types'
import { formatPercent } from '../../lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

const categoryColors: Record<string, string> = {
  product: '#15839a',
  risk: '#d45d4c',
  process: '#33658a',
  marketing: '#df8c3b',
  org: '#49796b',
  unknown: '#8d99ae',
}

const reviewStatusColors: Record<string, string> = {
  needs_review: '#d98f2b',
  approved: '#2f7d63',
  published: '#165a72',
  rejected: '#c34f45',
  archived: '#7b8794',
}

type ChronologyDatum = {
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

type ScatterDatum = {
  value: [number, number, number]
  eventId: string
  title: string
  category: string
  reviewStatus: string
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

function startOfDay(value: string) {
  return new Date(value).toISOString().slice(0, 10)
}

function averageConfidence(entries: TimelineEntry[]) {
  if (entries.length === 0) {
    return 0
  }

  return entries.reduce((sum, entry) => sum + entry.confidence, 0) / entries.length
}

function topCategory(entries: TimelineEntry[]) {
  const counts = new Map<string, number>()
  for (const entry of entries) {
    counts.set(entry.category, (counts.get(entry.category) ?? 0) + 1)
  }

  return [...counts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? 'unknown'
}

function buildDailyActivityOption(entries: TimelineEntry[]): EChartsOption {
  const counts = new Map<string, number>()
  for (const entry of entries) {
    const day = startOfDay(entry.start)
    counts.set(day, (counts.get(day) ?? 0) + 1)
  }

  const days = [...counts.keys()].sort()
  return {
    color: ['#165a72'],
    grid: { left: 36, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: 'axis' },
    xAxis: {
      type: 'category',
      data: days,
      axisLabel: { color: '#5f6b76', rotate: 35 },
      axisLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.18)' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#5f6b76' },
      splitLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.08)' } },
    },
    series: [
      {
        type: 'bar',
        data: days.map((day) => counts.get(day) ?? 0),
        barWidth: '55%',
        itemStyle: { borderRadius: [8, 8, 0, 0] },
      },
    ],
  }
}

function buildCategoryMixOption(entries: TimelineEntry[]): EChartsOption {
  const counts = new Map<string, number>()
  for (const entry of entries) {
    counts.set(entry.category, (counts.get(entry.category) ?? 0) + 1)
  }

  const rows = [...counts.entries()].sort((left, right) => right[1] - left[1])

  return {
    grid: { left: 100, right: 24, top: 12, bottom: 24 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    xAxis: {
      type: 'value',
      axisLabel: { color: '#5f6b76' },
      splitLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.08)' } },
    },
    yAxis: {
      type: 'category',
      data: rows.map(([category]) => category),
      axisLabel: { color: '#243642' },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        data: rows.map(([category, count]) => ({
          value: count,
          itemStyle: { color: categoryColors[category] ?? categoryColors.unknown },
        })),
        barWidth: '60%',
        itemStyle: { borderRadius: [0, 8, 8, 0] },
      },
    ],
  }
}

function buildSourceStateOption(entries: TimelineEntry[]): EChartsOption {
  const sources = [...new Set(entries.map((entry) => entry.source_id))]
  const statuses = ['needs_review', 'approved', 'published', 'rejected', 'archived']

  return {
    color: statuses.map((status) => reviewStatusColors[status]),
    grid: { left: 36, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { bottom: 0, textStyle: { color: '#5f6b76' } },
    xAxis: {
      type: 'category',
      data: sources,
      axisLabel: { color: '#243642' },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#5f6b76' },
      splitLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.08)' } },
    },
    series: statuses.map((status) => ({
      name: status.replace(/_/g, ' '),
      type: 'bar',
      stack: 'review-state',
      emphasis: { focus: 'series' },
      data: sources.map(
        (source) => entries.filter((entry) => entry.source_id === source && entry.review_status === status).length,
      ),
    })),
  }
}

function buildPriorityMatrixOption(entries: TimelineEntry[]): EChartsOption {
  const data: ScatterDatum[] = entries.map((entry) => ({
    value: [Math.round(entry.confidence * 100), entry.importance, 10 + entry.importance / 6],
    eventId: entry.event_id,
    title: entry.title,
    category: entry.category,
    reviewStatus: entry.review_status,
  }))

  return {
    grid: { left: 48, right: 18, top: 16, bottom: 34 },
    tooltip: {
      formatter: (params: unknown) => {
        const point = (params as { data?: ScatterDatum }).data
        if (!point) {
          return ''
        }

        return [
          `<strong>${point.title}</strong>`,
          `Category: ${point.category}`,
          `Review: ${point.reviewStatus}`,
          `Confidence: ${point.value[0]}%`,
          `Importance: ${point.value[1]}`,
        ].join('<br/>')
      },
    },
    xAxis: {
      type: 'value',
      name: 'Confidence %',
      min: 0,
      max: 100,
      axisLabel: { color: '#5f6b76' },
      splitLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.08)' } },
    },
    yAxis: {
      type: 'value',
      name: 'Importance',
      axisLabel: { color: '#5f6b76' },
      splitLine: { lineStyle: { color: 'rgba(20, 54, 69, 0.08)' } },
    },
    series: [
      {
        type: 'scatter',
        data,
        symbolSize: (value: number[]) => value[2],
        itemStyle: {
          color: (params: unknown) => {
            const point = (params as { data?: ScatterDatum }).data
            return reviewStatusColors[point?.reviewStatus ?? 'archived'] ?? reviewStatusColors.archived
          },
          opacity: 0.85,
        },
      },
    ],
  }
}

function buildChronologyOption(entries: TimelineEntry[]): EChartsOption {
  const categories = entries.map((entry) => entry.title)
  const data: ChronologyDatum[] = entries.map((entry, index) => ({
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
    grid: { left: 170, right: 24, top: 12, bottom: 32 },
    tooltip: {
      trigger: 'item',
      formatter: (params: unknown) => {
        const point = (params as { data?: ChronologyDatum }).data
        if (!point) {
          return ''
        }

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

function StatCard({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card>
      <CardContent className="space-y-1 p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
        <p className="text-3xl font-semibold text-foreground">{value}</p>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

function ChartCard({
  title,
  description,
  option,
  height,
  onClick,
  testId,
}: {
  title: string
  description: string
  option: EChartsOption
  height: number
  onClick?: (params: { data?: { eventId?: string } }) => void
  testId?: string
}) {
  return (
    <Card data-testid={testId}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <ReactECharts
          option={option}
          style={{ height: `${height}px`, width: '100%' }}
          onEvents={onClick ? { click: onClick } : undefined}
        />
      </CardContent>
    </Card>
  )
}

export function AnalysisDashboard({
  entries,
  onSelect,
}: {
  entries: TimelineEntry[]
  onSelect: (eventId: string) => void
}) {
  const stats = useMemo(() => {
    const total = entries.length
    const needsReview = entries.filter((entry) => entry.review_status === 'needs_review').length
    const avgConfidence = averageConfidence(entries)
    return {
      total,
      needsReview,
      avgConfidence,
      topCategory: topCategory(entries),
    }
  }, [entries])

  const dailyActivity = useMemo(() => buildDailyActivityOption(entries), [entries])
  const categoryMix = useMemo(() => buildCategoryMixOption(entries), [entries])
  const sourceState = useMemo(() => buildSourceStateOption(entries), [entries])
  const priorityMatrix = useMemo(() => buildPriorityMatrixOption(entries), [entries])
  const chronology = useMemo(() => buildChronologyOption(entries), [entries])

  return (
    <div className="space-y-6" data-testid="analysis-dashboard">
      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <StatCard label="Events in window" value={String(stats.total)} hint="All events returned by the selected review-state and date filters." />
        <StatCard label="Needs review" value={String(stats.needsReview)} hint="Backlog that still requires a human decision." />
        <StatCard label="Average confidence" value={formatPercent(stats.avgConfidence)} hint="Extraction confidence across the visible event set." />
        <StatCard label="Top category" value={stats.topCategory} hint="Dominant theme in the current analysis slice." />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard
          title="Daily activity"
          description="Volume by day so analysts can spot spikes and quiet periods immediately."
          option={dailyActivity}
          height={280}
          testId="analysis-daily-activity"
        />
        <ChartCard
          title="Category mix"
          description="Distribution of detected work themes in the current window."
          option={categoryMix}
          height={280}
          testId="analysis-category-mix"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <ChartCard
          title="Review state by source"
          description="Shows where backlog and approved output are accumulating across Slack and Telegram."
          option={sourceState}
          height={300}
          testId="analysis-source-state"
        />
        <ChartCard
          title="Priority matrix"
          description="High-importance and low-confidence events are usually the fastest candidates for manual review. Click a point to inspect it."
          option={priorityMatrix}
          height={300}
          onClick={(params) => {
            const eventId = params.data?.eventId
            if (eventId) {
              onSelect(eventId)
            }
          }}
          testId="analysis-priority-matrix"
        />
      </div>

      <ChartCard
        title="Chronology"
        description="Original time-span view retained for schedule-like investigations and source-to-event drill-down. Click a bar to inspect it."
        option={chronology}
        height={Math.max(entries.length * 38, 360)}
        onClick={(params) => {
          const eventId = params.data?.eventId
          if (eventId) {
            onSelect(eventId)
          }
        }}
        testId="analysis-chronology"
      />
    </div>
  )
}