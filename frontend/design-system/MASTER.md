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
  list card, the workspace sidebar, the workspace Chat tab, alerts.
- **Strong glass (`bg-glass-strong`)** where content sits behind: note cards, the composer and chat questions (no blur
  of their own; blur inside blur looks muddy), the theme menu, row menus, the hover card and dialogs (these also blur).
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
| `provenance-llm-surface` | `#f5f3ff` | `#221d3a` | AI note card and chat answer background (dark: slate with a violet tint, softened 2026-09-14) |
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
- A highlight draws its colour at 40% with `mix-blend-multiply`. An AI note's highlight ("AI" or "AI · edited") draws at
  15%, so the reader's own highlights stand out (`highlightFill(hex, provenance)`). The active note gets a `primary` outline,
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
  `article.note`, `.provenance-badge`, `.note-hover-card`, `.reader-panel`, `article.chat-answer`, `.chat-question`,
  `.chat-sources`, `.chat-answer-text`, `.chat-cite`, `.chat-answer-footer`, `.chunk-flash`, `.save-as-note`,
  `.retraction-banner`, `.reader`, `.highlight.active`, `a.workspace-note`, `section[data-paper-id]`, `.chat-scope`,
  `[data-paper-id]` on "Add papers" options, the "Note" / "Save note" / "Zoom in" / "Toggle theme" / "Question" / "Ask" /
  "Save as note" / "Retry" / "Re-index" / "Resize panel" / "Edit details" / "Save" / "Cancel" names, the "Ask this paper"
  heading and "Suggested questions" list, the "Edit details" dialog with its "Title" / "Authors" / "Year" / "Venue" /
  "DOI" fields and "Retracted" checkbox, the "Workspaces" navigation with "New workspace" / "Workspace name" /
  "Workspace actions" / "Rename" / "Delete", the "Paper actions" / "Add to workspace…" / "Remove from workspace" /
  "Add papers" / "Search papers" names, the "Notes" / "Chat" and "Papers" / "Notes" / "Chat" tabs, and the colour names
  "Yellow" … "Orange" / "Custom colour").
  Style with utility classes next to them.
- **Notes filter.** The top of the Notes tab has two filter chips in a `role="group"` "Show notes from": `aria-pressed`
  rounded-full buttons "You" and "AI", each with a count (`tabular-nums`). On: filled in the provenance badge's colours
  (You `bg-secondary ring-input`, AI `bg-provenance-llm-surface text-provenance-llm`) with a `Check` icon. Off: their own
  `UserRound` / `Sparkles` icon, no fill, `text-muted-foreground` and a `ring-border` outline. So state never rests on
  colour alone. Both start on; "AI" covers edited AI notes. They filter the list only, never the highlights on the paper.
  With every note filtered out, the list says "No notes match these filters."
- **Quotes stay short.** A note's quoted passage (panel card, composer, hover card) shows at most two lines, cut with
  an ellipsis (`line-clamp-2`), with the full passage in `title`. The note's own body is never clamped in the panel.
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
- **Where:** the second tab of the reader's right panel (`RightPanel`, shadcn `Tabs`). The tab
  is in the hash (`#/papers/:id?tab=chat`). Both panels stay mounted, so switching never loses a streaming answer.
  Selecting text in the PDF switches to Notes, where the composer is.
- **One Q&A** (Q&As `gap-6` apart): the question is a `text-sm` `bg-glass-strong` bubble on the right, at most 85% wide,
  `rounded-2xl rounded-br-sm`. The answer is a soft card: `rounded-2xl bg-provenance-llm-surface p-3.5`, no border, and
  nothing that repeats under every answer (the owner found a per-answer footer line and a side border repetitive,
  2026-09-14). Inside: the streamed text (`text-sm leading-relaxed`), then one quiet row with the `Sparkles` AI mark in
  `text-provenance-llm` and a small outline pill per source (`C1`, `C2`, …) that wrap among themselves.
- **Details wait behind hover and focus** (shadcn `Tooltip`, one provider per answer): the AI mark (focusable, class
  `chat-answer-footer`, its sr-only text is the label) shows `AI · <model> · prompt v<N>`. A pill and an inline `[C1]`
  show the source in words, `Source 1: page 6, section “2.4 Analysis”` (`describeSource` in `citations.ts`), over
  "The AI used this passage. Click to see it in the paper." "C1" alone means nothing to a reader, so the same words
  are each button's accessible name. A whole-paper answer shows one `Whole paper · N chunks` badge instead of pills.
- **Waiting:** until the first token, three `bg-provenance-llm` dots bounce (`motion-safe` only) in a `role="status"`
  with a screen-reader label ("Finding sources…", then "Writing the answer…").
- **Empty chat:** a centred `MessageSquareText` in a provenance-surface circle, the `font-heading` heading
  "Ask this paper", one line of `text-muted-foreground` help, and three outline starter buttons
  (`Suggested questions`: "Summarize the main contribution", "What method do they use?", "What are the limitations?")
  that ask in one click.
- **Citations:** `[C1]` is an inline `text-primary` button (4.7:1 light, 6.0:1 dark on the surface) whose visible text
  stays `[C1]`, with an `aria-label` naming the source. Its text must equal the answer's own characters: promote counts
  offsets in it. A marker with no surviving source is plain text.
- **Citation flash:** clicking a citation or a source chip scrolls the reader to the chunk and draws its rects for
  1.5 s with `bg-highlight-draft`, a `primary` outline and `mix-blend-multiply`. It pulses only under `motion-safe`.
- **Save as note:** selecting text inside one saved answer floats a small primary "Save as note" button (`Sparkles`)
  just below the selection. With nothing to anchor on it is disabled, and a `Tooltip` on a focusable wrapper says
  "Include a cited passage [C…] to anchor this note" (a disabled button gets no pointer or focus events).
- **Input:** one rounded-xl `bg-glass-strong` box pinned under the list, holding a borderless auto-growing `Textarea`
  ("Question", up to `max-h-40`) and an `icon-sm` primary `ArrowUp` button ("Ask"); the focus ring is on the box
  (`focus-within`). Under it, the hint "Enter to send · Shift+Enter for a new line" (`aria-describedby`). Enter sends,
  Shift+Enter adds a line, and it is disabled while an answer streams.
- **Errors:** a destructive `Alert` inside the Q&A it belongs to, with Retry or Re-index in `AlertAction`. A mid-stream
  error keeps the partial text above it.

## Paper metadata

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

## Resizable panel

- The reader's right panel is resizable from its left edge (`PanelResizeHandle`, the WAI-ARIA window splitter:
  `role="separator"`, "Resize panel", `aria-valuenow`/`min`/`max`). Drag it; or focus it and use ←/→ (16 px steps);
  double-click or Enter goes back to 360 px. A 2px `primary` line shows on hover (60%), focus and drag.
- Width: 360 px default, 320 px minimum, at most 60% of the window (`panelWidth.ts`). The grid clamps with CSS `clamp()`
  too, so a remembered width still fits a smaller window. Remembered in `localStorage` `paperlab-panel-width`.

## Motion

From ui-ux-pro-max (Quick Reference §7): 150–300 ms, ease-out on entry, opacity and transform only, no layout shift,
one or two moving things per view. Tokens live in `@/components/motion` (built on `tw-animate-css`); use them, not
one-off animation classes.
- **Everything is `motion-safe`.** With the OS set to reduce motion nothing moves, and the PDF canvas shows without a fade.
- **`popIn`** (fade + grow from 95%, 200 ms) for pop-ups, with an `origin-*` class pointing at where they come from: the
  highlight hover card and "Save as note" (`origin-top-left`), the note composer (`origin-top`).
- **`slideUpIn`** (fade up 8 px, 300 ms) for a new list item, once: a note card created in the last few seconds
  (`isFresh(created_at)`), in the reader or on a workspace's Notes tab, and the chat answer being asked now. Items loaded
  from the server, or re-shown by a filter, stay still.
- **`fadeIn`** (300 ms) for the library, workspace and reader pages, the reader's Notes / Chat panels and the workspace
  home's Papers / Notes / Chat panels (it replays each time a panel is shown).
- **The PDF canvas** fades in (300 ms) once it has drawn, instead of flashing from blank.
- **`pressable`** (scale to 97% while held) on filter chips, starter questions, source pills and the send button.
- **No exit animations** (they need the element to outlive its unmount).
- **Tooltips on adjacent triggers** (the source pills) use `TooltipProvider disableHoverableContent`: a hoverable wide
  tooltip keeps its "pointer heading to the tooltip" zone over the next pill and shows the wrong explanation.
- **E2E:** `e2e/motion.spec.ts` checks `animationName` (`enter` or `none`) under both motion settings. Hover tests move
  the mouse like a person (`glideTo`: many small steps, then a rest); instant jumps confuse Radix's pointer tracking.

## Workspaces

Patterns from ui-ux-pro-max: `search.py "sidebar navigation workspace project list rename delete" --domain ux` (tab
order matches visual order, severity High), `search.py "active navigation state hover actions destructive
confirmation" --domain ux` (highlight the active nav item; confirm before delete, High) and `search.py "dialog
command searchable list dropdown submenu checkbox" --stack shadcn` (Command for a searchable list rather than an
Input with a custom dropdown; Dialog for modal content, High).
- **Sidebar:** a plain `nav` ("Workspaces") on glass beside the library and each workspace home, never in the reader
  (the paper keeps its width). "All papers", then the workspaces alphabetically, then a ghost "New workspace" (`Plus`).
  The active item has `aria-current="page"`, `bg-primary/10` and the same 3 px `primary` inset bar as the previewed
  paper row. Each workspace's `EllipsisVertical` "Workspace actions" button stays invisible until its row is hovered
  or focused, like the rows' delete icon.
- **Names:** create and rename are an inline `Input` ("Workspace name"): Enter saves, Escape cancels, leaving it blank
  cancels. A refusal is a `role="alert"` line under the field in `text-xs text-destructive`: "Enter a name" or "A
  workspace with this name already exists". Delete asks with `window.confirm`, like papers and notes, and says
  "Papers and notes stay in your library".
- **Paper rows:** one row component everywhere (`PaperList`). Its `EllipsisVertical` "Paper actions" menu holds the
  "Add to workspace…" submenu (`DropdownMenuCheckboxItem`s that stay open while ticking) and, on a workspace home,
  "Remove from workspace".
- **Workspace home:** the header is the workspace name (Crimson Pro, `text-3xl`) over "N papers · M notes". Tabs are
  shadcn `Tabs` kept in the hash (`?tab=notes|chat`, `location.replace`), all `forceMount`ed. Papers: "Add papers" is
  the view's primary button, "Upload PDFs" is outline.
- **Add papers:** a `Dialog` on strong glass with a `Command` checklist of library papers not yet in the workspace.
  The item's check mark is `data-checked`; the footer's primary button counts the choice ("Add 2 papers").
- **Notes tab:** papers in title order, each an `h2` over a two-column grid of read-only note cards. A card is one link
  (`a.workspace-note`) to the reader focused on it: provenance badge and page, the quote (2 lines, full text in `title`,
  as "Quotes stay short"), the body (6 lines). AI notes keep `bg-provenance-llm-surface`. No filter chips: the reader's
  Notes tab has them, and this tab only points into the reader.
- **Chat tab:** the reader's `ChatPanel` in a glass card, under the `.chat-scope` line ("2 papers (1 not indexed) · 3
  notes"). Chips name the paper: `C1 · Karpukhin 2020 p.3`, `N1 · You · BERT p.4` (the paper label is the first
  author's surname and year, the surname alone without a year, else the title cut to 24 characters, as in the prompt
  the model sees). "Using 58 of 64 notes (newest first)" is a
  `text-xs text-muted-foreground` line under the chips. Citations navigate (`location.hash`, so Back returns to the
  answer): `[C…]` to the reader flashing the passage, `[N…]` to the reader focusing the note. An empty workspace shows
  "Add papers to chat with this workspace." and disables the input. Answers keep the opaque AI surface.

## Pre-delivery check (from ui-ux-pro-max Quick Reference §1–§3)

Run through this before finishing any UI task, in **both** themes:
- [ ] Text contrast ≥ 4.5:1; focus rings visible when tabbing through every control.
- [ ] Every icon-only button has an `aria-label`; every field has a visible or `aria-label` label.
- [ ] Tab order follows the visual order; Escape closes menus and cancels the note draft.
- [ ] Errors appear in an `Alert` (`role="alert"`) near what failed, with a way to recover (Retry, dismiss).
- [ ] Buttons show a pointer cursor and a disabled state while their action runs.
- [ ] No layout shift when data loads; long titles truncate with the full text in `title`.
- [ ] No emoji as icons.
