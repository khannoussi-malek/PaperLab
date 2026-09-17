/** What the Connect Claude page fills in for each system: Claude Desktop's config, Claude Code's command, the config file. */
export type SetupOs = 'macos' | 'windows' | 'wsl' | 'linux'

/** The system to preselect, from `navigator.userAgentData.platform` or `navigator.platform`. WSL looks like Windows
 * from the browser, so it is never guessed. */
export function detectOs(platform: string): SetupOs {
  if (/win/i.test(platform)) return 'windows'
  if (/mac|iphone|ipad/i.test(platform)) return 'macos'
  return 'linux'
}

/** The folder as typed, without surrounding spaces or one trailing `/` or `\`. */
const trimmed = (folder: string) => folder.trim().replace(/[/\\]$/, '')

const COMPOSE_EXEC = ['exec', '-T', 'api', 'python', '-m', 'mcp_server']

/** The `mcpServers` entry to paste into claude_desktop_config.json. Windows calls `docker compose` directly: Windows
 * apps get the system PATH Docker Desktop fills, and a `.cmd` wrapper won't start without a shell. */
export function desktopConfig(folder: string, os: SetupOs): string {
  const root = trimmed(folder)
  const paperlab =
    os === 'windows'
      ? { command: 'docker', args: ['compose', '-f', `${root}\\docker-compose.yml`, ...COMPOSE_EXEC] }
      : os === 'wsl'
        ? { command: 'wsl', args: ['-e', `${root}/scripts/paperlab-mcp`] }
        : { command: `${root}/scripts/paperlab-mcp` }
  return JSON.stringify({ mcpServers: { paperlab } }, null, 2)
}

/** The one-line `claude mcp add` for Claude Code, run in a terminal (inside WSL for `wsl`). */
export function claudeCodeCommand(folder: string, os: SetupOs): string {
  const root = trimmed(folder)
  if (os === 'windows') {
    return `claude mcp add -s user paperlab -- docker compose -f "${root}\\docker-compose.yml" ${COMPOSE_EXEC.join(' ')}`
  }
  return `claude mcp add -s user paperlab -- '${`${root}/scripts/paperlab-mcp`.replaceAll("'", "'\\''")}'`
}

/** Where Claude Desktop keeps its config on each system. */
export function configFileHint(os: SetupOs): string {
  if (os === 'macos') return '~/Library/Application Support/Claude/claude_desktop_config.json'
  if (os === 'linux') return 'Open it from Claude Desktop: Settings → Developer → Edit Config.'
  return '%APPDATA%\\Claude\\claude_desktop_config.json'
}
