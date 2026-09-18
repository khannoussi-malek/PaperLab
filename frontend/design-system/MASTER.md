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
  (`.paper-row`, `.status`, `.paper-preview`, `.search-count`, `.no-matches`, "Clear search", `.pdf-page`, `.pdf-overlay`, `.highlight`, `.draft`, `.zoom-level`,
  `article.note`, `.provenance-badge`, `.note-hover-card`, `.reader-panel`, `article.chat-answer`, `.chat-question`,
  `.chat-sources`, `.chat-answer-text`, `.chat-cite`, `.chat-answer-footer`, `.chat-following`,
  `article.chat-answer[data-parent-id]`, `.chunk-flash`, `.save-as-note`,
  `.retraction-banner`, `.reader`, `.highlight.active`, `a.workspace-note`, `section[data-paper-id]`, `.chat-scope`,
  `[data-paper-id]` on "Add papers" options, the "Note" / "Save note" / "Zoom in" / "Toggle theme" / "Question" / "Ask" /
  "Save as note" / "Retry" / "Re-index" / "Follow up" / "Stop following" / "Resize panel" / "Edit details" / "Save" / "Cancel" names, the "Ask this paper"
  and "Ask this workspace" headings and "Suggested questions" list, the "Edit details" dialog with its "Title" /
  "Authors" / "Year" / "Venue" /
  "DOI" fields and "Retracted" checkbox, the "Workspaces" navigation with "New workspace" / "Workspace name" /
  "Workspace actions" / "Rename" / "Delete", the "Paper actions" / "Add to workspace…" / "Remove from workspace" /
  "Add papers" / "Search papers" names, the "Notes" / "Chat" and "Papers" / "Notes" / "Chat" tabs, and the colour names
  "Yellow" … "Orange" / "Custom colour"). Also `article.dataset-card`, `.capture-box`, `.capture-crop`,
  `.table-region`, `.table-marker`, `.number-mark`, `.chart-view`, `.chart-warning`, `.chart-row`, `a.own-dataset`,
  `.series-card`, `.note-chart`, the "Data" tab, and the names "Capture table" / "Table name" / "Save table" /
  "Column N name" / "Column N actions" / "Row N actions" / "Row R, column C" / "Add as number" / "Label" / "Number
  found" / "Value" / "± error" / "Unit" / "Add number" / "Charts" / "New dataset" / "New chart" / "Chart actions" /
  "Chart title" / "Dataset name" / "Pasted data" / "CSV file" / "Create dataset" / "Charts use this data" / "Save
  anyway" / "View data table" / "Chart data" / "Add series" / "Choose data" / "Save chart" / "Save changes" / "Save
  as copy" / "Attach chart" / "Search charts" / "Remove chart" / "Add to note…" / "Quick chart" / "Open". Also
  `article.connection-card`, `.cloud-tag`, `.key-hint`, `.test-result`, `li.model-row`, `.embedding-indexed`, and
  the names "Settings" / "Add connection" / "Test" / "Edit connection" / "Delete connection" / "Add model" / "Add a
  model" / "Search or type a model name" / "Default model" / "Remove <name> from chat" / "Delete <name> from disk" /
  "Model to pull" / "Pull" / "Pulling <name>" / "Kind" / "Preset" / "Name" / "Base URL" / "API key" / "Replace key" /
  "Remove key" / "Save connection" / "Model" / "Manage models…" / "Set up a model" / "Open settings" / "Embedding
  model" / "Re-index library" / "Re-index the library?" / "Re-index". Also `.reference-row`, `.references-summary`
  and `.reference-list`.
  Also the names "Connect Claude" / "Open Connect Claude" / "Your system" (tabs "macOS" / "Windows" / "Windows + WSL" /
  "Linux") / "PaperLab folder" / "Copy" / "Copied" / "Check the server", and the regions "Claude Desktop" / "Claude
  Code" / "Check PaperLab's side".
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

## Chat

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
- **Paper search** (the one exception to "re-shown by a filter stay still", asked for 2026-09-17): a row the search brings
  back plays `fadeIn`, 40 ms after the row above it (at most 240 ms), with `fill-mode-backwards`, then drops the class
  so a tab panel shown again doesn't replay it. Rows from the server (first load, an upload) and rows still on screen
  while the query changes stay still. The count and clear button and the no-match card use `popIn`.
- **`fadeIn`** (300 ms) for the library, workspace and reader pages, the reader's Notes / Chat panels and the workspace
  home's Papers / Notes / Chat panels (it replays each time a panel is shown).
- **The PDF canvas** fades in (300 ms) once it has drawn, instead of flashing from blank.
- **`pressable`** (scale to 97% while held) on filter chips, starter questions, source pills and the send button.
- **`delayedIn`** (hidden for 150 ms, then a 200 ms fade) on every loading placeholder ("Loading…", "Loading page…",
  "Loading references…"), and on a page title only while it still reads "Loading…". Most screens load in under 75 ms,
  so the placeholder never shows; before, it flashed for a few frames.
- **Page cross-fade:** a hash change to another page runs as a view transition (`withViewTransition`, called by
  `useRoute`'s one `hashchange` listener): the browser cross-fades the old page into the new one with its own 250 ms
  fade, instead of the old page vanishing and the new one fading in from the bare background. Picking a theme does the
  same. A change of query only (a reader or workspace tab, a note or chunk target; `samePage`) swaps at once: its panel
  fades in by itself, and the page takes no clicks while a transition runs (`pointer-events` on `::view-transition`
  doesn't change that in Chromium).
- **Hover colours** ease with `transition-colors duration-150`; a hand-rolled row or link that changes colour on hover
  carries it too.
- **No exit animations** (they need the element to outlive its unmount). The page cross-fade is the one outgoing fade,
  and it is the browser's snapshot of the old page, not the element itself.
- **Tooltips on adjacent triggers** (the source pills) use `TooltipProvider disableHoverableContent`: a hoverable wide
  tooltip keeps its "pointer heading to the tooltip" zone over the next pill and shows the wrong explanation.
- **E2E:** `e2e/motion.spec.ts` checks `animationName` (`enter` or `none`) under both motion settings, and records each
  view transition with what was on screen when its update finished. Hover tests move the mouse like a person
  (`glideTo`: many small steps, then a rest); instant jumps confuse Radix's pointer tracking.

## Waiting

Fix the wait before dressing it. Measured 2026-09-18 on the owner's library (headless Chrome, `e2e/loading.spec.ts`
keeps each rule):
- **One PDF.js worker** (`pdfWorker` in `reader/pdfjs.ts`) serves every document, the reader and the library preview
  alike, passed to `getDocument({ worker })` so a task's `destroy()` never ends it. A worker per document cost ~250 ms on
  every open: a paper took ~550 ms to show its pages, now ~50–120 ms.
- **Plotly starts loading when a chart looks likely** (`loadPlotly.ts`): as the Charts list opens, or when the pointer or
  focus reaches any `a[href^="#/charts/"]`. It still loads on first use (4.6 MB), so a session without charts never
  fetches it; the first chart no longer waits ~1 s for it.
- **No skeleton for a wait under 150 ms**: `delayedIn` (see Motion) keeps the placeholder out of sight.

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
- **Paper search:** `PaperList` opens with a search bar (`PaperSearch`), so the library and every workspace's Papers tab
  get it. A shadcn `InputGroup` on glass (`h-10 rounded-xl border-glass-border`): a `Search` icon that turns `primary` while
  the field has focus, the `type="search"` field "Search papers" (placeholder "Search by title, author, year or venue";
  the browser's own clear icon hidden), then a `role="status"` `.search-count` ("4 of 18", `text-xs tabular-nums`, " papers" for
  screen readers; no `aria-label`, which some would read instead) and a ghost `X` "Clear search" while a search is on. Both
  clear buttons put the cursor back in the field. Esc clears. Each word typed must start a word of the title,
  an author, the year or the venue, ignoring case and accents (`matchesPaper`). Nothing matching swaps the rows for
  `.no-matches`: the library's dashed empty-state card with `SearchX`, "No papers match “…”", "Check the spelling, or try
  an author's surname or a year." and an outline "Clear search". The preview
  hides until something matches.
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
  notes"). Answers look as in the reader (the reader's Chat section): short pills `C1`, `C2`, … then `N1`, … for cited notes, with
  the words behind hover and focus. On a workspace the words name the paper: `Source 1: Karpukhin 2020, page 3,
  section “Method”` for a passage, and `N1 · You · BERT p.4` over "The AI used this note. Click to see it in the
  paper." for a note (`describeSource`, with `paperLabel`: the first author's surname and year, the surname alone
  without a year, else the title cut to 24 characters, as in the prompt the model sees). "Using 58 of 64 notes (newest
  first)" is a `text-xs text-muted-foreground` line under the pills. Citations and pills navigate (`location.hash`, so
  Back returns to the answer): `[C…]` to the reader flashing the passage, `[N…]` to the reader focusing the note. The
  empty chat is "Ask this workspace" with starters that look across its papers. An empty workspace disables the
  starters and the question box, and the hint under the box says "Add papers to chat with this workspace."

## Data and charts

Patterns from ui-ux-pro-max (`search.py "editable data grid spreadsheet table cell editing" --domain ux`: wide tables
scroll inside their own wrapper; `search.py "chart builder configure series live preview form" --domain ux`: every
field labelled, loading then success or error on save; `--stack shadcn "select popover toggle group dialog form"`:
shadcn `Select`, never a native select) and the dataviz skill (below).
- **Data tab:** the reader's third tab. A `article.dataset-card[data-dataset-id]` per dataset: `Table2` (table) or
  `Hash` (numbers) icon, the name (truncated, full text in `title`), "p. 7 · 3 rows × 4 columns" or "5 numbers", then
  ghost buttons "Show in paper" (`Crosshair`, tables only), "Open" (a link to the dataset page) and "Quick chart"
  (`ChartColumn`).
- **Capture table:** an outline toggle "Capture table" (`Table2`, `aria-pressed`) in the reader toolbar. While on, the
  pages show a crosshair, text can't be selected, and dragging draws a `.capture-box` (2 px `primary` outline,
  `primary/10` fill, never glass). Escape or the toggle leaves the mode. Releasing opens the "Capture table" dialog
  (`max-w-5xl`, strong glass): the PDF crop rendered with PDF.js at 2× (`.capture-crop`), a "Table name" field
  pre-filled from the caption, the grid editor, and Cancel + primary "Save table". Saved tables draw a 1 px
  `primary/40` `.table-region` outline and a `.table-marker` (`Table2`, 14 pt) inside its top-right corner, in fixed
  light colours in both themes (`bg-white/90`, `ring-1 ring-blue-600/40`, a `blue-600` icon) since the page stays
  white; clicking the marker opens the Data tab. The marker is found by position like highlights (the text layer covers the page).
- **Grid editor:** a shadcn `Table` in an `overflow-auto` wrapper. Header cells are inputs "Column N name" with a
  "Column N actions" menu (Merge with next column, Split after first word, Fill down, Set unit…, Insert column left,
  Insert column right, Delete column). Each body row starts with a "Row N actions" menu (Use as header, Insert row
  above, Insert row below, Delete row). Body cells are borderless inputs "Row R, column C" (`tabular-nums`). An edited
  cell has `data-edited="true"`, a 1 px dashed `outline-muted-foreground/60` (offset 1 px) and
  `title="Edited: extraction read “…”"` (never colour alone: the tooltip says it; there is no legend). "Add row" and "Add column" are ghost
  buttons under the table.
- **Numbers:** "Add as number" (`Hash`) in the draft menu (after "Add note…") and as a ghost button in the note composer.
  It opens the "Add as number" dialog: "Label" (required), the numbers found in the selection as a `radiogroup`
  "Number found" of outline chips (`88.5 ± 0.3`), "Value" and "± error" fields filled from the chosen chip, "Unit"
  filled from the word after it, and primary "Add number". A captured number is underlined on the page with a
  `.number-mark`: a 2 px dashed bottom border in fixed `slate-900/60` in both themes (it sits on the white page),
  never violet (AI) and never a highlight fill.
- **Charts page (`#/charts`):** the library's layout, `font-heading` "Charts" over "N charts · M datasets of your own",
  outline "New dataset" and primary "New chart". A glass list of `.chart-row[data-chart-id]`: type icon, title, sources
  in muted text ("BERT, XLNet, My data"), "Used in N notes · edited 2 h ago", and a "Chart actions" menu (Edit, Rename,
  Duplicate, Delete). Rename is an inline `Input` "Chart title" (Enter saves, Escape cancels, blank cancels). Delete
  asks with `window.confirm`, saying how many notes show the chart and that they are kept. Below, "My data": a list of
  `a.own-dataset` links. The library header gains an outline "Charts" link (`ChartColumn`).
- **New dataset:** a dialog with shadcn `Tabs` "Type" (name + column count → an empty grid), "Paste" (a `Textarea`
  "Pasted data" for tab-separated or CSV text) and "Upload CSV" (a native file input "CSV file"), a "Dataset name"
  field, and primary "Create dataset"; it opens the new dataset's page.
- **Dataset page (`#/datasets/:id`):** "← Back" (to the paper's Data tab, or the Charts page for own data), the name as
  an inline-renameable `h1`, the source line, the grid editor, and a sticky footer with "Delete dataset" (destructive
  ghost), "Quick chart" and primary "Save". Saving a grid that drops columns charts use opens an `AlertDialog`-style
  shadcn `Dialog` "Charts use this data" listing those chart titles, with Cancel and destructive "Save anyway". A
  focused cell from a chart point (`?row=&column=`) is scrolled to and focused once.
- **Chart page (`#/charts/:id`):** "← Charts", the title as an inline-renameable `h1`, outline "Edit", and a "Chart
  actions" menu (Rename, Duplicate, Add to note…, Delete). The chart sits in a glass card.
- **Chart view:** `.chart-view[data-chart-type][data-series-count]`, at least 360 px tall including the axis band. While
  data refetches, including while a changed spec's data loads, the last drawing stays at `opacity-60` (no skeleton),
  still compiled from the spec that drew it, and warnings stay hidden until the new data arrives. A warning shows
  above it as `.chart-warning`
  (`role="status"`, `TriangleAlert`, text on `muted`). Plotly's mode bar keeps only "Download plot as PNG", a "Download
  SVG" button and "Reset axes"; `displaylogo: false`. Hover shows the raw text first, "· edited" when edited, then the
  series and label, then the source. Clicking a bar, point or cell opens its source. Under the chart, a ghost "View
  data table" toggle (`aria-expanded`) shows a shadcn `Table` with `aria-label="Chart data"`.
- **Builder (`#/charts/new`, `#/charts/new?dataset=`, `#/charts/:id/edit`):** two columns, controls (`22rem`) and the
  live preview. Chart type: three `role="radiogroup"`s labelled by their group, each type a toggle chip with its icon.
  Series: one `.series-card` per series ("Series N" name input, "Data" picker (a `Command` dialog "Choose data", grouped
  by paper, "My data" last), "X", "Y", "Z", "Error bars" `Select`s whose items show sample values, "Rows" checkboxes in a
  collapsible, "Colour" swatches named "Colour 1"…"Colour 6", "Trend line" `Select`, "Multiply by" number input, and a
  "Remove series" icon button); ghost "Add series". Grid charts show "Data", then their column pickers. Axes: "X axis
  label", "Y axis label", "Y axis scale" `Select`; layout: "Bar mode" (Grouped/Stacked) and a "Small multiples"
  checkbox; "Chart title". Footer: primary "Save chart"; when editing, primary "Save changes" and outline "Save as copy",
  with "Used in N notes, which will show this change" when N > 0. A refused save shows the server's message in a
  destructive `Alert` above the footer.
- **Charts in notes:** a note card shows each chart as `.note-chart[data-chart-id]`: its title as a link to the chart
  page, a small static plot (`staticPlot`, 160 px tall) drawn once the card scrolls into view, and a "Remove chart"
  icon button. The card's footer gains ghost "Attach chart", opening the "Attach chart" dialog (`Command` "Search
  charts"). The chart page's "Add to note…" creates the note and shows "Added to a note in N papers" with a link to the
  first; a chart of only your own data shows "This chart only uses your own data, so there's no paper to note it in.
  Attach it to a note instead."
- **Colours:** the series palette and blue ramp in Global Constraints (validated with the dataviz checker on `card`
  surfaces). Several series colours are under 3:1 on the surface, so every chart keeps its legend (2+ series) and its
  data table view.

## Model connections

Patterns from ui-ux-pro-max (`search.py "form password input masked secret test connection feedback" --domain ux`:
loading then success or error on submit; `search.py "destructive confirmation delete dialog" --domain ux`: confirm
before deleting; `search.py "progress bar long running download status" --domain ux`: a progress bar for long work;
`search.py "dropdown select model picker empty state" --domain ux`: an empty state names the fix and links to it;
`--stack shadcn "select dialog form password input radio group"`: shadcn `Select` and `Dialog`, never native ones).
- **Settings page (`#/settings`):** the library's page shell in a `max-w-3xl` column: a ghost "Library" link
  (`ArrowLeft`), the `font-heading` h1 "Settings", then two `section`s labelled by their h2: "Model connections" and
  "Embedding model". The library header gains an outline icon link "Settings" (`Settings` icon) before the theme toggle.
- **Model connections:** the h2 row ends with the view's one primary button, "Add connection" (`Plus`). With none, a
  dashed box says "No model connections yet. Add Ollama, Anthropic or any OpenAI-compatible server." Each connection is
  an `article.connection-card[data-connection-id]` on glass (`glass`, `ring-1 ring-glass-border`, `rounded-xl p-4`):
  the h3 label (truncated, full text in `title`); a muted line "OpenAI-compatible · openrouter.ai" (kind, then host;
  Anthropic shows api.anthropic.com); a `.cloud-tag` outline `Badge` "Cloud" (`Cloud` icon) or "Local" (`HardDrive`
  icon), so it never rests on colour; and, except for Ollama, `.key-hint` "•••• T123" (`font-mono tabular-nums`) or
  "No key". On the right: outline "Test" (`PlugZap`, "Testing…" while it runs) and icon buttons "Edit connection"
  (`Pencil`) and "Delete connection" (`Trash2`, muted until hovered, asks with `window.confirm`: "Delete "<label>" and
  its models? Saved answers keep their model names."). The test result is a `role="status"` `.test-result` line under
  the header: `CircleCheck` + "Connected · 12 models", or `CircleAlert` in `text-destructive` + the reason. Every
  other action on the card (default, remove, delete, delete from disk) reports its own refusal on that same line,
  clearing whatever was there before. A cloud
  connection shows "Passages and notes from your library are sent to <host>" (`Info` icon, `text-xs text-muted-foreground`).
- **Models on a card:** a shadcn `RadioGroup` "Default model" (`asChild` over the `ul`, so the rows are really in a
  list) whose rows are `li.model-row[data-model-id]`: the radio
  (named by the model name), the name (`font-mono text-sm`, truncated), an icon button "Remove <name> from chat" (`X`)
  and, on Ollama, "Delete <name> from disk" (`Trash2`, asks first). None yet: "No models in chat yet." A ghost "Add
  model" (`Plus`) opens the "Add a model" `Dialog`: a `Command` with the input "Search or type a model name" over the
  provider's own list (fetched when the dialog opens: "Loading models…", or a destructive `Alert` with the reason),
  models already in chat left out, and last an item `Add "<typed>"` whenever the typed name isn't listed. When the
  server has no list, a muted line says "No model list here; type model names by hand" and only that item shows.
- **Ollama pull:** under an Ollama card's models, an inline form: `Input` "Model to pull" (placeholder `qwen3:8b`) and
  outline "Pull" (`Download`), disabled while a pull runs. While pulling: shadcn `Progress` with
  `aria-label="Pulling <name>"` (its value from `describePull`; indeterminate until Ollama reports sizes) and the status
  line under it (`text-xs tabular-nums`). Done: the model is in the list and the line says "Added <name> to chat". An
  error shows in a destructive `Alert`.
- **Connection dialog:** a shadcn `Dialog` on strong glass titled "Add connection" or "Edit connection". Each field has
  a visible `Label`: "Kind" `Select` (Ollama, Anthropic, OpenAI-compatible; disabled when editing); for
  OpenAI-compatible a "Preset" `Select` (OpenAI, OpenRouter, Groq, Mistral, DeepSeek, Gemini, LM Studio, Custom) that
  fills Name and Base URL; "Name"; "Base URL" (`type="url"`, hidden for Anthropic, Ollama starts at
  `http://host.docker.internal:11434`); "API key" (`type="password"`, `autoComplete="off"`, hidden for Ollama). Editing
  a keyed connection shows "•••• T123" with outline "Replace key" (shows the empty key field) and ghost destructive
  "Remove key" (the line then reads "The key will be removed"). A stored key is never put in a field. Footer: Cancel and
  primary "Save connection" ("Saving…"). A refusal shows the server's message in a destructive `Alert`; the dialog stays open.
  Moving a keyed connection to a different host warns "Changing the address removes the saved key." near the key field
  (the owner can type a new key in the same save to keep the connection working): the server drops a stored key on any
  PATCH that moves the address to a new host unless a fresh key comes with it.
- **Chat model picker:** in `ChatPanel`'s composer, in the row under the question box and before the hint: a small
  shadcn `Select` (`size="sm"`, `aria-label="Model"`, at most `14rem`, truncating) whose items read `name · connection`,
  with a `.cloud-tag` "Cloud" badge on non-local ones, then a separator and "Manage models…" (opens `#/settings`).
  With no models at all, the row shows the link "Set up a model" (`Settings2`) instead, and the question box is
  disabled with the hint "Set up a model to chat." When the list can't be loaded at all, asking stays open (the
  server's own default answers) and a muted line says "Couldn't load your models; using the default."
- **AI mark:** its tooltip and screen-reader label read `AI · <model> · <connection> · prompt v<N>` (`aiMark`);
  answers saved before connections read `AI · <model> · prompt v<N>`.
- **Refusals:** `no_model` and `embedding_model_changed` alerts carry an outline "Open settings" link in `AlertAction`;
  `model_not_found` offers Retry, which asks with the dropdown's fallback.
- **Embedding model:** a shadcn `Select` "Embedding model" showing the configured model. Always disabled, since there
  is nothing to switch to yet, and a `Lock` icon joins its label once chunks exist; `.embedding-indexed` "indexed with nomic-ai/nomic-embed-text-v1.5 · 12,400 chunks"
  (`tabular-nums`). When some chunks came from another model, a destructive `Alert`: "N chunks were indexed with another
  model. Chat on those papers is refused until you re-index." An outline "Re-index library" (`RefreshCw`) opens the
  `Dialog` "Re-index the library?" ("Every paper's passages are embedded again with <model>, in the background."),
  with Cancel and destructive "Re-index"; then a `role="status"` line "Re-indexing N papers in the background."
- **Chat panel details:** `.chat-cite` has `outline-none focus-visible:ring-2 focus-visible:ring-ring`. While an
  answer streams, the list stays at its bottom if it was there. "Save as note" stays inside the panel
  (`saveButtonPosition`) and re-measures when the panel changes size or is shown again.
- **Follow up:** a saved paper answer's meta row ends with a ghost `xs` **Follow up** (`CornerDownRight`). Its chip
  sits just above the question box: `Following: <question>` (`text-xs text-muted-foreground`, truncated, full text
  in `title`) and an `icon-xs` ghost × named Stop following. Follow-ups are indented one level under their thread's
  first question (`ml-3 border-l border-glass-border pl-3`); workspace chat has no Follow up.

## Paper sources

- **Section:** "Paper sources" in Settings, between Model connections and Embedding model. It holds a muted intro line,
  then the contact email, then one glass list (`divide-y divide-glass-border`, `ring-1 ring-glass-border`).
- **Contact email:** a labelled `Input` with an outline Save, disabled while blank, unchanged or saving, and a ghost
  Remove once an email is saved. It is checked on submit (`noValidate`), and the server's own message shows under the
  field (`role="alert"`, `text-destructive`). Muted help says which sources receive it.
- **Source row** (`.paper-source-row[data-source-id]`): a shadcn `Checkbox` linked to the source's name
  (`font-heading`), which saves on change and is disabled while saving. Under it, indented past the checkbox: a muted
  description; for OpenAlex, an outline "May cost money" badge (`CircleDollarSign`) and its price note; for Unpaywall
  without an email, a muted `Info` note.
- **API keys** (OpenAlex, Semantic Scholar, CORE): a password `Input` whose accessible name is "<Source> API key",
  with an outline Save key. Once a key is saved, the row shows `Key ending in 1234` (`.key-hint`) and a ghost
  destructive "Remove key" that asks first. A key is never shown back, and the field clears after saving.
- **Errors:** a destructive `Alert` under the row or field whose save failed. Loading failures get Retry, as in
  Embedding model.

## Find papers

Pattern from ui-ux-pro-max (`search.py "search results list with add button in modal dialog" --domain ux`): an empty
result suggests what to try next (severity Medium). Its "autocomplete as you type" advice is declined on purpose: a
search asks every paper source that is on, and OpenAlex costs money past a small daily allowance, so search runs on
submit.
- **Find papers:** an outline button (`Search`) beside Upload PDFs, in the library header and a workspace's Papers tab,
  opens a shadcn `Dialog` (`sm:max-w-2xl`, glass like Add papers). One `Input` labelled "Title, DOI, arXiv ID or
  OpenAlex ID" and a Search submit button, disabled and reading "Searching…" while a search runs. Results scroll inside
  the dialog (`max-h-[60vh]`). Sources that failed while others answered show above the results in a non-destructive
  glass `Alert` (`Info`, `role="status"`, `.search-notices`). An error that stops the search altogether is an
  `ErrorAlert`.
- **Candidate rows** (`CandidateList`, shared with the reader's Similar tab): the title (two lines, full text in
  `title`), byline · citations, then the names of the sources that found it as small muted outline badges
  (`ul.candidate-sources`, labelled "Found by"), and a `Badge`: secondary "PDF" when a free PDF is listed, outline "No
  free PDF" otherwise. Then small buttons: Add (`Plus`; "Adding…" with a spinning `LoaderCircle`, disabled while it
  runs) or an outline "In library" link to the reader, and a ghost "Open page" link (`ExternalLink`, new tab). A failed
  add shows an `ErrorAlert` under its row, and the row keeps its Add button.
- **Similar tab:** the reader's fourth tab, after Data. An `aside` labelled "Similar papers": a muted one-line
  explanation, the candidate rows, and `LoadError` with Retry when Semantic Scholar refuses. It asks only once the tab
  has been opened; suggestions stay fresh for an hour.

## References

- **References:** the reader's fifth tab, after Similar. An `aside` labelled "References": a muted one-line
  explanation ("What this paper cites, and what has cited it since — ranked for your library."), a compact **Cited** /
  **Citing** switch (shadcn `Tabs`, default variant — already compact at `h-8`, no separate size needed), the
  summary line (`.references-summary`), then the rows. It asks Semantic Scholar (and OpenAlex, when on) only once the
  tab has been opened, like Similar — and opening it for the first time also queues the fetch (D78): a paper that has
  never been fetched goes straight to the `fetching` state, no button to click.
- **Rows** (`.reference-row`, in a `.reference-list`): reuses `CandidateList`'s row shape — title (two lines, full
  text in `title`), byline · year · citations, a **Cited by N of your papers** outline badge once 2 or more of the
  reader's own papers cite it (never at 0 or 1: the paper being read always "cites" its own references, so 1 means
  no co-citation yet); in **Citing**, where the count is the library papers a citing work cites, the badge reads
  **Cites N of your papers**. Then the same secondary "PDF" / outline "No free PDF" badge as Find papers. Actions:
  primary **Import** (`Plus`; "Importing…" with a spinning `LoaderCircle`, disabled while it runs), or an outline
  **In library** link to the reader once it is; a ghost **Open page** link (`ExternalLink`, new tab) whenever the
  reference has an identifier to link to (`pageLink`, reused from Find papers), shown alongside either action —
  independent of it, exactly as Find papers shows Open page beside Add. A failed import shows an `ErrorAlert` under
  its row, same as Find papers.
- **States:** `none` and `fetching` both show the same `role="status"` "Fetching references…" line over three
  `animate-pulse` skeleton rows (plain divs — no new dependency, no bespoke skeleton component): opening the tab on a
  never-fetched paper queues the fetch immediately, so there is nothing to click while it queues. A failed first
  fetch request (the one that queues it) shows its error in an `ErrorAlert` with outline **Try again** in place of
  the status line and skeletons, since nothing is fetching. `failed` → the stored error in an `ErrorAlert` with
  outline **Try again** (queues another fetch; distinct label from the query-level `LoadError`'s "Retry", which
  covers a transport/500 failure instead); a fetch still `fetching` after 10 minutes (the worker lost it) is listed
  as `failed` with "Fetching references failed. Try again." `ready` with no rows → "This paper's sources list no
  references."
- **Refresh:** once `ready`, a small ghost **Refresh** button (`RefreshCw`, disabled while its own fetch runs) sits
  beside the summary line (`ml-auto` in the same flex row, so it stays put whether or not a summary is shown). A
  failed refresh request shows its error in an ErrorAlert.
- **Summary line:** `{refs} cited by 3+ of your papers, {pdfs} have PDFs` in **Cited**, and `{refs} cite 3+ of your
  papers, {pdfs} have PDFs` in **Citing**, built by `referencesMeta.ts`'s `summaryLine`. Either half drops when its
  count is zero; the whole line is left out when both are.
- The switch keeps whichever direction the reader was viewing; both directions share one fetch state (the worker
  fills `cites` and `cited_by` together), so switching mid-fetch or mid-failure shows the same state either way.

## Connect Claude

Patterns from ui-ux-pro-max (2026-09-17): `search.py "submit button loading state disabled" --domain ux` (loading, then
success or error, High); `"success feedback confirmation message after action"` (a brief success message, Medium);
`"input placeholder label helper text"` (a visible label, never only a placeholder, High); `"long text overflow code
horizontal scroll"` (wide content scrolls inside its own box, High); `--stack shadcn "tabs code block"` (shadcn `Tabs`
with a set value). The onboarding, copy-button and OS-tab queries returned nothing specific.
- **Page (`#/connect-claude`):** Settings' page shell (`max-w-3xl`, ghost "Library" back link, `font-heading` h1
  "Connect Claude"), then `section`s labelled by their h2, in order: What Claude can do, What Claude receives, Your
  system, PaperLab folder, Claude Desktop, Claude Code, Check PaperLab's side, If it doesn't work. Body copy is
  `text-sm`; notes and help are `text-muted-foreground`.
- **Your system:** a shadcn `Tabs` whose `TabsList` is labelled "Your system": macOS, Windows, Windows + WSL, Linux.
  Preselected from `navigator.userAgentData.platform` or `navigator.platform` (`detectOs`); never guesses WSL. The tabs
  switch what the sections below show, so there are no `TabsContent` panels (as in References' Cited / Citing).
- **PaperLab folder:** an `Input` (`font-mono`, no spellcheck) named by its section heading (`aria-labelledby`), prefilled
  from `GET /api/mcp/setup`. While blank: `text-xs` muted help "Paste the full path of your PaperLab folder." (Windows adds
  "For example C:\Users\you\PaperLab."), and Claude Desktop and Claude Code say "The config appears here once the
  PaperLab folder is filled in." / "The command appears here once …". A failed load shows `LoadError` with Retry.
- **Code blocks:** a `pre` on `bg-muted`, `rounded-lg p-3 pr-24 font-mono text-xs leading-relaxed overflow-x-auto`, with
  an outline `sm` "Copy" button (`Copy` icon) at its top right that reads "Copied" (`Check` icon) for 2 s. A refused copy
  shows the reader's message in an `ErrorAlert` under the block. Inline paths and commands are `code` with
  `rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]`.
- **Claude Desktop:** "Edit Claude Desktop's config file:", then three numbered steps. Step 1 names the file
  (`configFileHint`) except on Linux, where the hint is the whole step. The config block follows; Linux adds a muted
  line that Claude Desktop on Linux is a beta for Ubuntu 22.04+ and Debian 12+.
- **Check PaperLab's side:** a muted line that this checks PaperLab, not Claude's config; "Check the server" is the
  view's one primary button ("Checking…" and disabled while it runs). Success is a `role="status"` line with a
  `CircleCheck` in `text-primary`; a failure is an `ErrorAlert` with the server's `detail`.
- **Entry points:** an outline "Connect Claude" button (`Plug`) in the library header, before the Settings icon; and
  Settings' last section, "Connect Claude", with one muted sentence and an outline "Open Connect Claude" link (`Plug`).

## Graph

Patterns from ui-ux-pro-max (2026-09-17): `search.py "graph canvas visualization with layer toggles" --domain ux`
returned nothing about graphs, only *Gesture Conflicts* (don't take the page's own gestures — the canvas takes wheel
and drag, the page does not pan); `"detail side panel"` and `"checkbox toggle filter"` returned nothing at all;
`"dialog form with searchable list"` gave *Submit Feedback* (High: loading, then success or error) and *Form Labels*
(High: a visible label, never a placeholder alone); `"keyboard navigation focus visible"` gave *Focus States* and
*Keyboard Navigation* (High); `"canvas accessibility screen reader"` gave *Screen Reader* and *Heading Hierarchy*.
That a canvas has no pattern here is why the canvas carries `aria-hidden` and the side panel is the real interface.
- **Page (`#/graph`):** `h-dvh` three-column grid, `14rem` controls · canvas · `20rem` panel, each column a `glass`
  card with a `border-glass-border` hairline. The header is the library's shape: `font-heading` h1 "Graph", the counts
  line under it, then an outline "Library" link and the theme toggle.
- **Counts line:** `{n} papers, {m} links` (singulars at 1), with ` · Showing the first 2000 links.` appended when the
  payload is truncated. It counts the *visible* links, so unticking a layer changes it.
- **Canvas:** `react-force-graph-2d`, loaded with a dynamic `import()` in `GraphCanvas.tsx` and nowhere else (187 kB,
  61 kB gzipped, its own chunk — the same rule as Plotly). It carries `aria-hidden` and a visually hidden line beside
  it reads `{n} papers, {m} links. Use the papers list to explore connections.` Transparent background, so the glass
  card shows through. A node's radius runs 3–9 px with its share of the links; a faded node or link draws at 12%
  opacity. Never hand force-graph a string label: float-tooltip sets a string as innerHTML, and titles come from
  PDFs and discovery sources. Every label goes through `tooltipFor`, which sets text. A `manual` link is 2.5 px wide
  with its label drawn along it above 1× zoom; every other link is 1 px; `cites` and `manual` carry an arrow at the
  target end. Focus and hops only change the accessors, so they fade the graph without moving it; a layer toggle, a
  theme change, or a saved, renamed or removed link rebuilds it. The dynamic import's failure state — an
  `ErrorAlert` and a "Reload" button — sits outside the `aria-hidden` wrapper, so a screen reader reaches what it can
  act on.
- **Colours:** `SERIES_COLORS` from `features/charts/palette.ts` through `useChartTheme()` — the same palette the
  charts use, already checked for colour-blind readers on both surfaces. A paper wears its **first** workspace's
  colour, workspaces take colours alphabetically (so a colour doesn't move when a paper joins one), and a paper in no
  workspace wears `CHART_INK[theme].muted` — the same token the charts' text uses, so it follows the theme. Past the
  sixth workspace the palette cycles; the legend still names every one.
- **Controls:** a `Checkbox` per link kind with its count, labelled exactly `Citations`, `Same workspace`, `Noted
  together`, `Same author`, `Same topic`, `Similar content`, `Your links`; **Citations** and **Similar content** are
  ticked on load, and drawing a link ticks **Your links**. Then a `Select` "Workspace" (**Whole library** first), a
  `Select` "Links out" (1–3, only while a paper is focused), and the colour legend.
- **Panel:** it always lists the papers — an h2 "Papers" over buttons (`.graph-paper`), sorted by link count then
  title, each with its count — so a keyboard user can move from paper to paper. With one focused, a "Connected papers"
  section sits above that list: the h2, the paper's title under it, a ghost "Clear focus", the outline "Link to
  another paper…" button, then an h3 per kind (plain blocks, not landmarks) over rows (`.graph-connection`) linking to
  the reader. A **Your links** row also gets ghost icon buttons "Edit label for {title}" and "Remove link to {title}";
  removal asks with `window.confirm` first. Focus follows the action: choosing a paper moves it to the "Connected
  papers" heading (`tabIndex={-1}`), "Clear focus" returns it to that paper's button, and a confirmed removal moves it
  to the heading. Both custom rows carry the app's focus ring (`outline-none focus-visible:ring-3
  focus-visible:ring-ring/50`). Switching workspace keeps the page up while the new graph loads (`keepPreviousData`).
- **Link dialog:** `Dialog` on `bg-glass-strong`, a `Command` list under the visible caption **Paper to link to**
  (searchable, the focused paper left out; once one is chosen a `role="status"` line reads `Linking to "{title}".`,
  because cmdk's highlight follows the pointer and is not the choice) and an `Input` labelled **Label** with the placeholder `builds on`, capped
  at 80 characters. cmdk overwrites any `id` passed to `CommandInput`, so the caption is plain text and the input is
  named by `Command label=` (which fills cmdk's own hidden `<label>`) plus a matching `aria-label`; the **Label**
  field keeps a real `<Label htmlFor>`, because it wraps a real `<input>`. Both rules are checked before the request
  (`labelError`), and the server's refusal lands in an `ErrorAlert` inside the dialog. A failed save clears when the
  dialog closes; a failed removal, which has no dialog, shows above the panel. The submit reads "Saving…" and
  disables while it runs.
- **Empty state:** `No links yet. Import references, add papers to a workspace, or turn on OpenAlex to fill this in.`
- **Stable test hooks:** `.graph-paper`, `.graph-connection`, `data-paper-id` on both, the "Graph" link in the library
  header, the "Workspace" and "Links out" selects, the checkbox names above, the "Connected papers" region, "Clear
  focus", "Link to another paper…", "Paper to link to", "Label", "Save link", "Edit label for …" and "Remove link to …".

## Pre-delivery check (from ui-ux-pro-max Quick Reference §1–§3)

Run through this before finishing any UI task, in **both** themes:
- [ ] Text contrast ≥ 4.5:1; focus rings visible when tabbing through every control.
- [ ] Every icon-only button has an `aria-label`; every field has a visible or `aria-label` label.
- [ ] Tab order follows the visual order; Escape closes menus and cancels the note draft.
- [ ] Errors appear in an `Alert` (`role="alert"`) near what failed, with a way to recover (Retry, dismiss).
- [ ] Buttons show a pointer cursor and a disabled state while their action runs.
- [ ] No layout shift when data loads; long titles truncate with the full text in `title`.
- [ ] No emoji as icons.
