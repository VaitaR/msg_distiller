import type { Meta, StoryObj } from '@storybook/react-vite'

import type { EventRecord } from '../../features/events/types'
import { EventDetailPanel } from './event-detail-panel'

const sampleEvent: EventRecord = {
  event_id: '00000000-0000-0000-0000-000000000001',
  message_id: 'msg-seed-001',
  source_channels: ['#releases'],
  title: 'Payments v2 launch',
  action: 'launch',
  object_id: 'payments-v2',
  object_name_raw: 'Payments v2',
  qualifiers: [],
  stroke: 'General availability',
  anchor: 'billing',
  category: 'product',
  status: 'completed',
  change_type: 'release',
  environment: 'production',
  severity: 'medium',
  confidence: 0.87,
  importance: 82,
  message_published_at: '2026-03-02T09:55:00Z',
  summary: 'Payments v2 launched in production with lower checkout friction.',
  why_it_matters: 'Reduces drop-off across the main conversion path.',
  links: [],
  anchors: ['payments'],
  impact_area: ['payments', 'checkout'],
  impact_type: ['conversion'],
  time_source: 'message',
  time_confidence: 0.9,
  cluster_key: 'cluster-payments-v2',
  dedup_key: 'dedup-payments-v2',
  source_id: 'slack',
  review_status: 'needs_review',
  reviewed_by: null,
  reviewed_at: null,
  version: 1,
  origin: 'ai_extraction',
  extracted_at: '2026-03-02T10:00:00Z',
  planned_start: '2026-03-02T10:00:00Z',
  planned_end: '2026-03-02T18:00:00Z',
  actual_start: '2026-03-02T10:00:00Z',
  actual_end: '2026-03-02T17:00:00Z',
  event_date: '2026-03-02T10:00:00Z',
}

const meta = {
  title: 'Events/EventDetailPanel',
  component: EventDetailPanel,
  args: {
    event: sampleEvent,
    actor: 'storybook-user',
    isSaving: false,
    onSave: async () => undefined,
  },
  decorators: [
    (Story) => (
      <div className="max-w-xl p-6">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof EventDetailPanel>

export default meta

type Story = StoryObj<typeof meta>

export const Viewing: Story = {}

export const EmptySelection: Story = {
  args: {
    event: null,
  },
}