# PaperLab design system

The single source of truth for how PaperLab looks. Read this before any task that changes what the
UI looks like or how it behaves. If a value here and a value in `src/index.css` disagree, fix
`index.css`.

## Direction

A calm reading tool, in the spirit of Readwise Reader or Zotero 7. The PDF is the content; the
interface around it stays quiet. Desktop first. Light and dark themes, chosen with the toggle
(Light / Dark / System).

Derived from ui-ux-pro-max (`~/.claude/skills/ui-ux-pro-max`), then curated. The generator is tuned
for landing pages, so only these parts of its output were kept:
- Palette: "document grey + scan blue", from
  `search.py "document reader annotation tool minimalism swiss neutral" --design-system`.
- Type pairing: Crimson Pro + Atkinson Hyperlegible ("academic, research, scholarly, accessible"), from
  `search.py "research paper reader note-taking productivity tool calm minimal content-first academic" --design-system`.
- Rejected from its output: landing-page patterns, the mobile touch-first flat style, the OLED-dark-only
  style, and loading fonts from Google (this app is local-first, so fonts are bundled with `@fontsource`).
- Glass (added 2026-09-13, "subtle"): ui-ux-pro-max's Glassmorphism style (`search.py "glassmorphism" --domain style`),
  toned down for reading: more opaque surfaces than its 15–30% default, so text keeps ≥ 4.5:1.

## Glass

The app chrome is frosted glass over a faint blue/violet glow on the page background. The paper is not.
- **Glass (`glass` from `@/components/glass`: `bg-glass backdrop-blur-lg backdrop-saturate-150`)**, with a
  `border-glass-border` or `ring-glass-border` hairline: reader toolbar, the reader's right panel (Notes | Chat), library
  list card, alerts.
- **Strong glass (`bg-glass-strong`)** where content sits behind: note cards, the composer and chat questions (no blur
  of their own; blur inside blur looks muddy), the theme menu and the hover card (these two also blur).
- **Never glass:** the PDF page, highlights, the citation flash, and the AI provenance surface
  (`bg-provenance-llm-surface` wins, including under chat answers).
- OS "Reduce transparency" swaps both glass tokens for `card`, so every surface turns solid.
- Measured contrast on glass (screenshots, both themes): body text 10.8–17.7:1, muted text 5.8–7.5:1.

## Stack

- Components: shadcn/ui, style `radix-nova`, in `src/components/ui/`. Add one with
  `npx shadcn@4.21.0 add <name>` or through the shadcn MCP server (`.mcp.json` at the repo root).
  Never hand-copy a component.
- Styling: Tailwind CSS 4 utility classes. No per-feature `.css` files. The only stylesheets are
  `src/index.css` (tokens) and PDF.js's own `pdf_viewer.css`.
- Icons: `lucide-react` only. Decorative icons get `aria-hidden`; icon-only buttons get `aria-label`.
- Class merging: `cn` from `@/lib/utils`.

## Tokens

Defined in `src/index.css` as CSS variables and exposed to Tailwind through `@theme inline`
(so `bg-primary`, `text-muted-foreground`, `bg-provenance-llm-surface`, …).

| Token | Light | Dark | Use |
|---|---|---|---|
| `background` | `#f8fafc` | `#0f172a` | App background |
| `foreground` | `#0f172a` | `#f1f5f9` | Body text |
| `card` | `#ffffff` | `#1e293b` | Cards, toolbar |
| `primary` / `primary-foreground` | `#2563eb` / `#ffffff` | `#60a5fa` / `#0f172a` | The one primary action per view, focus ring |
| `muted` / `muted-foreground` | `#f1f5f9` / `#475569` | `#1e293b` / `#94a3b8` | Reader pane background, secondary text, quotes |
| `destructive` | `#dc2626` | `#f87171` | Errors, delete |
| `border` / `input` | `#e2e8f0` / `#cbd5e1` | white 10% / white 15% | Dividers, field borders |
| `provenance-llm` / `-foreground` | `#6d28d9` / `#ffffff` | `#a78bfa` / `#1e1b4b` | AI provenance badge |
| `provenance-llm-surface` | `#f5f3ff` | `#2e1065` | AI note card background |
| `highlight-draft` | blue 25% | same | The pending selection. Saved highlights use their note's colour (see "Highlight colours") |
| `glass` / `glass-strong` | white 70% / white 85% | slate-800 55% / slate-800 92% | Frosted chrome / cards and floating surfaces |
| `glass-border` | slate-400 35% | white 10% | Hairline on glass |
| `ambient-1` / `ambient-2` (body glow) | blue 12% / violet 10% | blue 18% / violet 16% | Radial glows behind the glass |

All text pairs above meet WCAG AA (4.5:1) in their theme. Check any new pair before using it.

Fonts: body `Atkinson Hyperlegible Next Variable` (`font-sans`), headings `Crimson Pro Variable`
(`font-heading`). Radius `0.625rem`.

## Highlight colours

- Each note has one colour, lowercase `#rrggbb`. Presets: Yellow `#facc15` (default), Green `#4ade80`,
  Blue `#60a5fa`, Pink `#f472b6`, Orange `#fb923c`, plus any custom colour. No violet preset: violet means AI.
- A highlight draws its colour at 40% with `mix-blend-multiply`. The active note gets a `primary` outline,
  never a colour swap.
- Pick colours with `HighlightColorPicker` only (composer, panel card, hover card). Swatches are named buttons
  with `aria-pressed`; a custom colour commits when the native picker closes.
- New highlights start on the last colour used (`localStorage` `paperlab-highlight-color`, yellow if unavailable).

## PaperLab-specific rules

- **Provenance is never subtle.** Every note shows a `ProvenanceBadge` with an icon and a label
  ("You", "AI", "AI · edited"). AI notes also get the `provenance-llm-surface` background. Never
  rely on colour alone.
- **The PDF page stays white in both themes.** It is the paper. Highlights use `mix-blend-multiply`.
- **Nothing that shifts selection coordinates** goes on `.pdf-page`: no border, no padding.
- **Stable test hooks.** Keep the class names and accessible names the Playwright specs use
  (`.paper-row`, `.status`, `.paper-preview`, `.pdf-page`, `.pdf-overlay`, `.highlight`, `.draft`, `.zoom-level`,
  `article.note`, `.provenance-badge`, `.note-hover-card`, `article.chat-answer`, `.chat-question`, `.chat-sources`,
  `.chat-answer-text`, `.chat-cite`, `.chat-answer-footer`, `.chunk-flash`, `.save-as-note`, `.retraction-banner`, the
  "Note" / "Save note" / "Zoom in" / "Toggle theme" / "Question" / "Save as note" / "Retry" / "Re-index" /
  "Edit details" / "Save" / "Cancel" names, the "Edit details" dialog with its "Title" / "Authors" / "Year" / "Venue" /
  "DOI" fields and "Retracted" checkbox, the "Notes" / "Chat" tabs, and the colour names "Yellow" … "Orange" /
  "Custom colour").
  Style with utility classes next to them.
- One primary button per view. Destructive actions use `text-destructive` and ask for confirmation.
  A delete icon repeated on every list row stays `text-muted-foreground` until its row is hovered or focused.
- **The hover card manages its note.** It is `NoteCard` in its compact variant (`div.hover-note`, never an
  `article.note`): colour, Edit, Delete. It stays open while the pointer is on the highlight or the card, closes
  300 ms after it leaves both, and never closes while any of its notes is being edited. Keyboard users use the panel.
- **Right-click is resolved by the highlight hit-test.** A saved highlight opens the note menu (colours, Edit note,
  Copy quote, Delete note); the pending selection opens the draft menu (Highlight in <colour>, Add note…, Copy text,
  Cancel); anywhere else the browser keeps its own menu. The menu is the shadcn `DropdownMenu` anchored at the
  pointer, and a failed copy shows in the error alert.

## Chat (M4)

Pattern from ui-ux-pro-max (`search.py "AI chat panel streaming answer citations sidebar" --domain ux`): stream text as
it arrives instead of a long spinner, and label AI output clearly (severity High). shadcn guidance
(`--stack shadcn "tabs tooltip"`): Tabs for switching related panels, Tooltip rather than `title` for hints.
- **Where:** the second tab of the reader's right panel (`RightPanel`, shadcn `Tabs`). The PDF keeps its width. The tab
  is in the hash (`#/papers/:id?tab=chat`). Both panels stay mounted, so switching never loses a streaming answer.
  Selecting text in the PDF switches to Notes, where the composer is.
- **One Q&A:** the question is a `bg-glass-strong` bubble on the right. The answer sits on `bg-provenance-llm-surface`:
  sources first (outline chips `C1 · p.4 · Method`, or one `Whole paper · N chunks` badge), then the streamed text,
  then the footer `Sparkles` + `AI · <model> · prompt v<N>` in `text-xs text-muted-foreground`
  (6.9:1 light, 5.9:1 dark on the surface).
- **Citations:** `[C1]` is an inline `text-primary` button (4.7:1 light, 6.0:1 dark on the surface) whose visible text
  stays `[C1]`, with an `aria-label` naming the source. Its text must equal the answer's own characters: promote counts
  offsets in it. A marker with no surviving source is plain text.
- **Citation flash:** clicking a citation or a source chip scrolls the reader to the chunk and draws its rects for
  1.5 s with `bg-highlight-draft`, a `primary` outline and `mix-blend-multiply`. It pulses only under `motion-safe`.
- **Save as note:** selecting text inside one saved answer floats a small primary "Save as note" button (`Sparkles`)
  just below the selection. With nothing to anchor on it is disabled, and a `Tooltip` on a focusable wrapper says
  "Include a cited passage [C…] to anchor this note" (a disabled button gets no pointer or focus events).
- **Input:** a labelled `Textarea` ("Question") pinned under the list. Enter sends, Shift+Enter adds a line, and it is
  disabled while an answer streams.
- **Errors:** a destructive `Alert` inside the Q&A it belongs to, with Retry or Re-index in `AlertAction`. A mid-stream
  error keeps the partial text above it.

## Paper metadata (M6.5)

Pattern from ui-ux-pro-max (`search.py "critical warning banner persistent alert content page" --domain ux`): toasts are
for non-critical information and auto-dismiss, so a critical fact is not a toast. `search.py "edit form dialog modal
fields validation" --domain ux`: mark required fields, show loading then success or error on submit (severity High).
- **Retraction banner:** a destructive `Alert` (`role="alert"`, `TriangleAlert`) spanning the reader under the toolbar,
  above the pages and the right panel, never over the PDF. Opaque `bg-card`, never glass, never dismissible. Title
  "This paper has been retracted", then "Check the retraction notice before relying on its findings." and the DOI link
  when there is one. `text-destructive` on `card`, full opacity for both the title and the description (the banner's
  own class overrides `alert.tsx`'s `/90` description, which measures 4.32:1 here -- under AA): 4.8:1 light, 5.3:1 dark.
- **Edit details:** an outline "Edit details" button (`PencilLine`) in the reader toolbar opens a shadcn `Dialog`:
  Title (required), Authors (`Textarea`, one per line), Year and Venue side by side, DOI, Abstract (`Textarea`), and
  a "Retracted" `Checkbox`. Save is disabled until something changed and reads "Saving…" while it runs. A refusal
  shows a destructive `Alert` inside the dialog, which stays open with the draft. Only changed fields are sent: the
  server remembers them as corrections that re-processing never overwrites.

## Pre-delivery check (from ui-ux-pro-max Quick Reference §1–§3)

Run through this before finishing any UI task, in **both** themes:
- [ ] Text contrast ≥ 4.5:1; focus rings visible when tabbing through every control.
- [ ] Every icon-only button has an `aria-label`; every field has a visible or `aria-label` label.
- [ ] Tab order follows the visual order; Escape closes menus and cancels the note draft.
- [ ] Errors appear in an `Alert` (`role="alert"`) near what failed, with a way to recover (Retry, dismiss).
- [ ] Buttons show a pointer cursor and a disabled state while their action runs.
- [ ] No layout shift when data loads; long titles truncate with the full text in `title`.
- [ ] No emoji as icons.
