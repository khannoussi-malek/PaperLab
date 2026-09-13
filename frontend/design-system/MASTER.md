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
| `highlight` / `-active` / `-draft` | yellow 40% / orange 50% / blue 25% | same | Highlights on the (always white) PDF page |

All text pairs above meet WCAG AA (4.5:1) in their theme. Check any new pair before using it.

Fonts: body `Atkinson Hyperlegible Next Variable` (`font-sans`), headings `Crimson Pro Variable`
(`font-heading`). Radius `0.625rem`.

## PaperLab-specific rules

- **Provenance is never subtle.** Every note shows a `ProvenanceBadge` with an icon and a label
  ("You", "AI", "AI · edited"). AI notes also get the `provenance-llm-surface` background. Never
  rely on colour alone.
- **The PDF page stays white in both themes.** It is the paper. Highlights use `mix-blend-multiply`.
- **Nothing that shifts selection coordinates** goes on `.pdf-page`: no border, no padding.
- **Stable test hooks.** Keep the class names and accessible names the Playwright specs use
  (`.paper-row`, `.status`, `.pdf-page`, `.pdf-overlay`, `.highlight`, `.draft`, `.zoom-level`,
  `article.note`, `.provenance-badge`, `.note-hover-card`, the "Note" / "Save note" / "Zoom in" / "Toggle theme" names).
  Style with utility classes next to them.
- One primary button per view. Destructive actions use `text-destructive` and ask for confirmation.

## Pre-delivery check (from ui-ux-pro-max Quick Reference §1–§3)

Run through this before finishing any UI task, in **both** themes:
- [ ] Text contrast ≥ 4.5:1; focus rings visible when tabbing through every control.
- [ ] Every icon-only button has an `aria-label`; every field has a visible or `aria-label` label.
- [ ] Tab order follows the visual order; Escape closes menus and cancels the note draft.
- [ ] Errors appear in an `Alert` (`role="alert"`) near what failed, with a way to recover (Retry, dismiss).
- [ ] Buttons show a pointer cursor and a disabled state while their action runs.
- [ ] No layout shift when data loads; long titles truncate with the full text in `title`.
- [ ] No emoji as icons.
