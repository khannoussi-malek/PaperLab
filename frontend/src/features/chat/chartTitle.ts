/** The bold first line a chart answer starts with, as its saved chart's title. */
export const chartTitle = (content: string) => content.match(/^\*\*(.+?)\*\*/)?.[1] ?? 'Chart from chat'
