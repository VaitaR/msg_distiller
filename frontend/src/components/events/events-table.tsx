import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table'
import { useState } from 'react'
import type { SortingState } from '@tanstack/react-table'

import type { EventRecord } from '../../features/events/types'
import { cn } from '../../lib/utils'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card'

import { eventColumns } from '../../features/events/table-columns'

export function EventsTable({
  items,
  selectedEventId,
  onSelect,
}: {
  items: EventRecord[]
  selectedEventId: string | null
  onSelect: (eventId: string) => void
}) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'confidence', desc: true },
  ])

  const table = useReactTable({
    data: items,
    columns: eventColumns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    state: { sorting },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review queue</CardTitle>
        <CardDescription>
          Sorted client-side for MVP. Backend filtering stays authoritative for review status.
        </CardDescription>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        <table data-testid="events-table" className="min-w-full border-separate border-spacing-y-2 text-left text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {header.isPlaceholder ? null : (
                      <button
                        type="button"
                        className="flex items-center gap-1"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </button>
                    )}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                data-testid="events-row"
                className={cn(
                  'cursor-pointer rounded-3xl bg-white/80 transition hover:bg-white',
                  row.original.event_id === selectedEventId && 'ring-2 ring-primary/40',
                )}
                onClick={() => onSelect(row.original.event_id)}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-3 first:rounded-l-3xl last:rounded-r-3xl">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}