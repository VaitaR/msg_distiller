import type { Meta, StoryObj } from '@storybook/react-vite'

import { LoadingState } from './loading-state'

const meta = {
  title: 'Events/States/LoadingState',
  component: LoadingState,
  args: {
    lines: 5,
  },
  decorators: [
    (Story) => (
      <div className="max-w-xl p-6">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof LoadingState>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}