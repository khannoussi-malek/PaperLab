import { describe, expect, it } from 'vitest'
import { claudeCodeCommand, configFileHint, desktopConfig, detectOs } from './connectClaude'

const MAC = '/Users/me/research-note'
const WINDOWS = 'C:\\Users\\me\\PaperLab'

describe('detectOs', () => {
  it('reads Windows, macOS and Linux from the platform the browser reports, and never guesses WSL', () => {
    expect(['Win32', 'Windows'].map(detectOs)).toEqual(['windows', 'windows'])
    expect(['MacIntel', 'macOS', 'iPhone', 'iPad'].map(detectOs)).toEqual(['macos', 'macos', 'macos', 'macos'])
    expect(['Linux x86_64', 'Linux', 'Chrome OS', ''].map(detectOs)).toEqual(['linux', 'linux', 'linux', 'linux'])
  })
})

describe('desktopConfig', () => {
  it('runs the launcher script on macOS and Linux', () => {
    const expected = `{
  "mcpServers": {
    "paperlab": {
      "command": "/Users/me/research-note/scripts/paperlab-mcp"
    }
  }
}`
    expect(desktopConfig(MAC, 'macos')).toBe(expected)
    expect(desktopConfig(MAC, 'linux')).toBe(expected)
  })

  it('runs the launcher script through wsl on Windows + WSL, with the path inside WSL', () => {
    expect(JSON.parse(desktopConfig('/home/me/PaperLab', 'wsl'))).toEqual({
      mcpServers: { paperlab: { command: 'wsl', args: ['-e', '/home/me/PaperLab/scripts/paperlab-mcp'] } },
    })
  })

  it('calls docker compose directly on Windows', () => {
    expect(desktopConfig(WINDOWS, 'windows')).toBe(`{
  "mcpServers": {
    "paperlab": {
      "command": "docker",
      "args": [
        "compose",
        "-f",
        "C:\\\\Users\\\\me\\\\PaperLab\\\\docker-compose.yml",
        "exec",
        "-T",
        "api",
        "python",
        "-m",
        "mcp_server"
      ]
    }
  }
}`)
  })

  it('drops one trailing separator from the folder', () => {
    expect(desktopConfig(`${MAC}/`, 'macos')).toBe(desktopConfig(MAC, 'macos'))
    expect(desktopConfig(`${WINDOWS}\\`, 'windows')).toBe(desktopConfig(WINDOWS, 'windows'))
  })
})

describe('claudeCodeCommand', () => {
  it('quotes the launcher script on macOS, Linux and WSL', () => {
    const expected = "claude mcp add -s user paperlab -- '/Users/me/research-note/scripts/paperlab-mcp'"
    expect((['macos', 'linux', 'wsl'] as const).map((os) => claudeCodeCommand(`${MAC}/`, os))).toEqual([
      expected,
      expected,
      expected,
    ])
  })

  it("keeps a folder with spaces and a ' in it as one argument", () => {
    expect(claudeCodeCommand("/Users/me/Bob's papers/Paper Lab", 'macos')).toBe(
      "claude mcp add -s user paperlab -- '/Users/me/Bob'\\''s papers/Paper Lab/scripts/paperlab-mcp'",
    )
  })

  it('calls docker compose directly on Windows', () => {
    expect(claudeCodeCommand(`${WINDOWS}\\`, 'windows')).toBe(
      'claude mcp add -s user paperlab -- docker compose -f "C:\\Users\\me\\PaperLab\\docker-compose.yml" exec -T api python -m mcp_server',
    )
  })
})

describe('configFileHint', () => {
  it("says where each system keeps Claude Desktop's config", () => {
    expect((['macos', 'windows', 'wsl', 'linux'] as const).map(configFileHint)).toEqual([
      '~/Library/Application Support/Claude/claude_desktop_config.json',
      '%APPDATA%\\Claude\\claude_desktop_config.json',
      '%APPDATA%\\Claude\\claude_desktop_config.json',
      'Open it from Claude Desktop: Settings → Developer → Edit Config.',
    ])
  })
})
