import type { Meta, StoryObj } from '@storybook/react-vite'

import { ErrorState } from './error-state'

const meta = {
  title: 'Events/States/ErrorState',
  component: ErrorState,
  args: {
    title: 'Could not load review data',
    description: 'The backend request failed. Verify the API and retry.',
    onRetry: () => undefined,
  },
  decorators: [
    (Story) => (
      <div className="max-w-xl p-6">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof ErrorState>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const WithoutRetry: Story = {
  args: {
    onRetry: undefined,
  },
}
