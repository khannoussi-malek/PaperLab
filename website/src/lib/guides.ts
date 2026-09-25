// The guides, in the order the index lists them. Each answers something people type into a search engine or ask an
// AI assistant, often before they know a tool like PaperLab exists.
export const TOPICS = ['Reading and notes', 'Finding papers', 'Literature reviews', 'Writing', 'AI in research', 'Comparisons'] as const
export type Topic = (typeof TOPICS)[number]
export type Guide = { path: string; title: string; blurb: string; topic: Topic }

export const GUIDES: Guide[] = [
  {
    path: 'guides/how-to-read-a-research-paper/',
    topic: 'Reading and notes',
    title: 'How to read a research paper efficiently',
    blurb: 'The three-pass method, what to skip, and how to keep what you read.',
  },
  {
    path: 'guides/how-to-take-notes-on-research-papers/',
    topic: 'Reading and notes',
    title: 'How to take notes on research papers',
    blurb: 'Notes you can find again and trace back to the passage they came from.',
  },
  {
    path: 'guides/find-a-free-pdf-of-a-paper/',
    topic: 'Finding papers',
    title: 'How to find a free, legal PDF of a research paper',
    blurb: 'arXiv, repositories, Unpaywall, CORE, and asking the authors.',
  },
  {
    path: 'guides/chat-with-a-pdf-locally/',
    topic: 'AI in research',
    title: 'How to chat with a PDF locally, without uploading it',
    blurb: 'Ask papers questions with a local model, and check every answer against the page.',
  },
  {
    path: 'compare/zotero/',
    topic: 'Comparisons',
    title: 'PaperLab vs Zotero',
    blurb: 'A reference manager and a reading tool do different jobs. Which one you need, or both.',
  },
  {
    path: 'guides/systematic-literature-review/',
    topic: 'Literature reviews',
    title: 'How to do a systematic literature review',
    blurb: 'Question, protocol, search, two-stage screening, snowballing and PRISMA.',
  },
  {
    path: 'guides/check-ai-answers-against-sources/',
    topic: 'AI in research',
    title: 'Can you trust AI with research papers?',
    blurb: 'Invented citations, and a five-step check for any AI answer.',
  },
  {
    path: 'guides/claude-desktop-with-your-papers/',
    topic: 'AI in research',
    title: 'How to use Claude Desktop with your papers',
    blurb: 'Connect your local library to Claude through MCP, and what gets sent.',
  },
  {
    path: 'guides/map-your-literature/',
    topic: 'Finding papers',
    title: 'How to map the literature on a topic',
    blurb: 'Citation graphs, co-citation and coupling, and tools that draw the map.',
  },
  {
    path: 'compare/ai-pdf-tools/',
    topic: 'Comparisons',
    title: 'Open-source alternative to ChatPDF, Elicit and SciSpace',
    blurb: 'Online AI paper tools compared with a local, open-source option.',
  },
  {
    path: 'guides/write-a-related-work-section/',
    topic: 'Writing',
    title: 'How to write a related work section',
    blurb: 'Organise by idea, compare papers, and check every claim.',
  },
  {
    path: 'guides/organize-research-papers/',
    topic: 'Reading and notes',
    title: 'How to organise research papers',
    blurb: 'One library, projects instead of folders, notes on the passage.',
  },
  {
    path: 'guides/local-llm-for-research/',
    topic: 'AI in research',
    title: 'Running a local LLM for research',
    blurb: 'Hardware, Ollama, choosing a model, and making it answer well.',
  },
  {
    path: 'guides/extract-data-from-papers/',
    topic: 'Literature reviews',
    title: 'How to extract data from research papers',
    blurb: 'Capture tables, keep each number’s page, chart it with yours.',
  },
  {
    path: 'guides/disclose-ai-use-in-research/',
    topic: 'Writing',
    title: 'How to disclose AI use in research',
    blurb: 'What to record, a disclosure you can adapt, and why checking matters.',
  },
  {
    path: 'compare/obsidian/',
    topic: 'Comparisons',
    title: 'PaperLab vs Obsidian',
    blurb: 'Notes on the passage vs linked Markdown notes, and using both.',
  },
]
