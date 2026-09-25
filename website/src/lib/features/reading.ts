import type { Feature } from '../features.ts'

// Reading, noting and asking: the features you use inside one paper.
export const READING_FEATURES: Feature[] = [
  {
    slug: 'pdf-highlighter',
    name: 'Highlights',
    tagline: 'Highlight PDFs in five colours or your own, and edit notes in place.',
    title: 'PDF highlighter for research papers, with notes on the page',
    description:
      'Highlight research PDFs in five colours or your own, add a note to any highlight, and edit or recolour it in place. Free, open source, runs on your computer.',
    h1: 'Highlight research papers, and keep the note on the page',
    answer:
      'PaperLab is a free, open-source PDF reader for research papers with a highlighter built for note-taking. Select text to highlight it in one of five colours or a custom one, and add a note if you want. Hover a highlight to see, edit, recolour or delete its note in place, or right-click it to copy the quote. The page stays white in every theme, so colours read the same.',
    shot: 'feature-reading',
    shotAlt:
      'A page of the BERT paper highlighted in five colours, the note card that opens when you hover a highlight, and the right-click menu with Copy quote.',
    points: [
      'Highlight in yellow, green, blue, pink or orange, or pick any custom colour.',
      'Add a note while highlighting, or later from the highlight’s card.',
      'Hover a highlight to read, edit, recolour or delete its note without leaving the page.',
      'Right-click a highlight for the same actions and Copy quote.',
      'Read with zoom in a light, dark or system theme; the PDF page stays white.',
      'Resize the side panel by dragging its edge; it remembers the width.',
    ],
    steps: [
      { title: 'Select', body: 'Drag across the words you want, as in any PDF reader.' },
      { title: 'Pick a colour', body: 'Choose one of five presets or a custom colour. Violet is left out: it means AI.' },
      { title: 'Write, if you want', body: 'Add a note now or later. It stays attached to exactly that passage.' },
    ],
    tips: [
      'Give each colour one meaning and keep it: for example yellow for claims, green for methods, blue for numbers.',
      'Highlight less than you think. A highlight with a one-line note is worth ten without.',
      'Use Copy quote when writing, so the quotation matches the paper exactly.',
    ],
    faqs: [
      {
        q: 'Can I use my own highlight colours?',
        a: 'Yes. Pick one of five presets or any custom colour. Violet is not a preset because PaperLab uses it only for AI.',
      },
      {
        q: 'Does dark mode change the PDF colours?',
        a: 'No. The app follows your light, dark or system theme, but the PDF page itself stays white, so highlights look the same.',
      },
      {
        q: 'Where are my highlights stored?',
        a: 'In a local database on your computer, with the exact position of each passage on its page. Nothing is uploaded.',
      },
    ],
    related: ['anchored-notes', 'ask-a-paper', 'follow-citations'],
    guides: ['guides/how-to-read-a-research-paper/', 'guides/how-to-take-notes-on-research-papers/'],
  },
  {
    slug: 'anchored-notes',
    name: 'Anchored notes',
    tagline: 'Every note keeps its page and passage, and says who wrote it.',
    title: 'Research notes anchored to the passage they came from',
    description:
      'Notes that keep the page and position of their passage. Click one to jump back. Each shows who wrote it: You, AI or AI · edited. Filter by author.',
    h1: 'Notes that remember exactly where they came from',
    answer:
      'In PaperLab every note is anchored to the passage it is about: it keeps the page and the position on that page, and clicking the note opens the paper right there. Each note also says who wrote it, You, AI or AI · edited, and the notes list filters by author. So months later you can cite a note with confidence and still tell your own thinking from a model’s.',
    shot: 'feature-notes',
    shotAlt:
      'A page with two highlights, each linked to its note: one marked You and one marked AI, both on page 4, under You and AI filter chips.',
    points: [
      'Every note keeps the page and position of its passage.',
      'Click a note to jump back to the passage in the paper.',
      'Each note shows who wrote it: You, AI, or AI · edited.',
      'Filter the notes list to your notes, AI notes, or both.',
      'Editing an AI note marks it “AI · edited”, never “You”.',
      'Workspaces show every note from their papers in one place.',
    ],
    tips: [
      'Write the note in your own words, and say whether it is the paper’s claim or your opinion.',
      'Before writing a section, read the notes for that workspace instead of rereading papers.',
      'Keep AI notes as drafts to check, not conclusions.',
    ],
    faqs: [
      {
        q: 'What happens to a note if I edit an AI note?',
        a: 'It becomes “AI · edited”. PaperLab never relabels model text as yours, so your provenance stays honest.',
      },
      {
        q: 'Can I see all notes across papers?',
        a: 'Yes, per workspace: a workspace lists every note from its papers, and each still links back to its passage.',
      },
      {
        q: 'Are notes stored with the AI model that wrote them?',
        a: 'Yes. AI text keeps the model and the prompt version that produced it, stored apart from your own writing.',
      },
    ],
    related: ['pdf-highlighter', 'workspaces', 'note-suggestions'],
    guides: ['guides/how-to-take-notes-on-research-papers/', 'guides/check-ai-answers-against-sources/', 'guides/write-a-related-work-section/', 'guides/disclose-ai-use-in-research/', 'compare/obsidian/'],
  },
  {
    slug: 'ask-a-paper',
    name: 'Ask a paper',
    tagline: 'Chat with a paper; every answer cites the passage it used.',
    title: 'Chat with a research paper, with answers that cite the page',
    description:
      'Ask a research paper questions and get answers that cite passages like [C1]. Click a citation to see it on the page. Local or cloud models, your choice.',
    h1: 'Ask a paper questions, and check every answer on the page',
    answer:
      'PaperLab lets you chat with one research paper at a time. Answers stream in and cite the passages they used, like [C1]: hover a citation to see its page and section, click it and the paper scrolls to that passage and flashes it. Your notes on the paper go to the model too, and answers can cite them like [N1]. Select part of an answer and save it as a note, anchored on the passage it cites and marked AI.',
    shot: 'feature-ask-a-paper',
    shotAlt:
      'A question and an AI answer citing [C1] and [C2]; hovering [C1] shows its page and section, a line leads to that passage flashed on the page, and part of the answer is saved as an AI note.',
    points: [
      'Answers stream in as they are written, and cite passages like [C1].',
      'Hover a citation for its page and section; click it to scroll the paper there.',
      'A short paper is sent whole; a long one is searched first, and only the best passages are sent.',
      'Your notes are sent too, marked You or AI, and answers can cite them like [N1].',
      'Press Follow up to ask about an answer; the model sees your questions and passages, never its own earlier answers.',
      'Pick the model per question, and each answer keeps the model that wrote it.',
      'Select part of an answer and Save as note: anchored on the cited passage, marked AI.',
    ],
    steps: [
      { title: 'Retrieve', body: 'The question is matched against the paper’s passages, or the whole short paper is used.' },
      { title: 'Answer', body: 'The model answers from those passages and your notes, and cites each one it uses.' },
      { title: 'Check', body: 'Click a citation: the paper scrolls to the passage and flashes it.' },
    ],
    tips: [
      'Ask narrow questions (“What is the masking rate?”) before broad ones (“Summarise the method”).',
      'Check every citation behind a claim you will reuse.',
      'Use a local model for unpublished work; cloud models are tagged “Cloud”.',
    ],
    faqs: [
      {
        q: 'Does PaperLab send my whole paper to the model?',
        a: 'Only a short paper is sent whole. For a long one, PaperLab searches it first and sends only the most relevant passages, plus your notes on it.',
      },
      {
        q: 'Why doesn’t a follow-up include the earlier answer?',
        a: 'So a model’s mistake doesn’t compound. A follow-up gets your earlier questions and the passages they used, never the model’s own earlier answers.',
      },
      {
        q: 'Which models can answer?',
        a: 'A local Ollama model, Anthropic with your key, or any OpenAI-compatible server such as OpenAI, OpenRouter, Groq, Mistral, DeepSeek, Gemini, LM Studio, vLLM or llama.cpp.',
      },
    ],
    related: ['any-model', 'anchored-notes', 'note-suggestions', 'semantic-search'],
    guides: ['guides/chat-with-a-pdf-locally/', 'guides/check-ai-answers-against-sources/', 'compare/ai-pdf-tools/', 'guides/disclose-ai-use-in-research/'],
  },
  {
    slug: 'note-suggestions',
    name: 'Note suggestions',
    tagline: 'One click suggests passages worth a note; keep the ones you want.',
    title: 'AI note suggestions for research papers, one click',
    description:
      'Ask PaperLab to suggest notes: a model proposes passages worth noting, you keep the ones you want, marked AI. It skips passages you already noted.',
    h1: 'Let a model suggest notes, and keep only the good ones',
    answer:
      'Suggest notes asks the model you chose to propose a few passages of the paper worth a note, each with a draft. You keep the ones you want: each becomes a note anchored on its passage and marked AI, and the rest disappear. Asking again skips every passage that already has a note, whether you wrote it or kept a suggestion, so each round covers new ground.',
    next: true,
    points: [
      'One click asks the model for passages worth a note, spread across the paper.',
      'Each suggestion shows its passage and a draft note.',
      'Keep a suggestion and it becomes a note anchored on that passage, marked AI.',
      'Asking again skips passages that already have a note.',
      'When every passage is covered, it says so instead of calling the model.',
    ],
    tips: [
      'Use it after your own first pass, to catch what you skipped.',
      'Edit a kept note into your own words: it then shows “AI · edited”.',
      'A local model keeps the paper on your machine.',
    ],
    faqs: [
      {
        q: 'Are suggested notes saved automatically?',
        a: 'No. Nothing is saved until you keep a suggestion. Kept ones are marked AI like every other model-written note.',
      },
      {
        q: 'Will it suggest the same passage twice?',
        a: 'No. A new round skips passages that already have a note, including ones you wrote by hand.',
      },
      {
        q: 'When is it available?',
        a: 'It is built and arrives with the next desktop release.',
      },
    ],
    related: ['anchored-notes', 'ask-a-paper', 'any-model'],
    guides: ['guides/how-to-take-notes-on-research-papers/', 'guides/check-ai-answers-against-sources/'],
  },
  {
    slug: 'follow-citations',
    name: 'Follow a citation',
    tagline: 'Hover [51] to see which paper it is, then open or add it.',
    title: 'Follow in-text citations in a PDF, and come back',
    description:
      'Hover an in-text citation like [51] to see which paper it is, open it if it is in your library or add it when a free PDF exists, then jump back to your page.',
    h1: 'See which paper a citation is, without losing your place',
    answer:
      'When a PDF links its numbered citations, PaperLab turns each one into a card. Hover [51] to see which paper it is: its details once the references are looked up, with Open in PaperLab when it is in your library or Add to library when a free PDF exists, and otherwise the entry exactly as the reference list prints it. Click to jump to the entry, and Back to page N returns you to where you were.',
    shot: 'feature-follow-a-citation',
    shotAlt:
      'Hovering a numbered citation opens its reference: one already in your library with Open in PaperLab, one not yet added with Add to library, and a Back to page 4 pill.',
    points: [
      'Hover a numbered citation to see its paper’s details.',
      'Open in PaperLab when the cited paper is in your library.',
      'Add to library in a click when a free PDF exists.',
      'Click to jump to the reference entry; Back to page N takes you back.',
      'Tab reaches every citation, for keyboard reading.',
    ],
    tips: [
      'Add the references you meet three times: they are usually the foundations.',
      'Use Back to page N instead of scrolling, so you never lose your place.',
    ],
    faqs: [
      {
        q: 'Does it work on every PDF?',
        a: 'It works where the PDF links its citations to the reference list, which most publisher and arXiv PDFs do.',
      },
      {
        q: 'Can it download paywalled references?',
        a: 'No. It offers Add to library only when a free, legal PDF exists, and otherwise shows the entry as printed.',
      },
      {
        q: 'Can I use it with a keyboard?',
        a: 'Yes. Tab moves through every citation on the page.',
      },
    ],
    related: ['references', 'find-papers', 'citation-graph'],
    guides: ['guides/how-to-read-a-research-paper/', 'guides/map-your-literature/'],
  },
  {
    slug: 'data-and-charts',
    name: 'Data and charts',
    tagline: 'Capture a table or a number, chart it next to your own CSV.',
    title: 'Extract tables from research PDFs and chart the results',
    description:
      'Draw a box over a table in a PDF to capture it, keep a number like 88.5 ± 0.3, add your CSV, and chart them together. Every point links back to its page.',
    h1: 'Capture a paper’s results, and chart them against yours',
    answer:
      'PaperLab turns results in a PDF into data you can chart. Draw a box over a table to capture it, or select a number like 88.5 ± 0.3 to keep it. Add your own results from a CSV and chart them side by side. Every point on a chart remembers where it came from: click it and the paper opens at the table on its page.',
    shot: 'feature-chart-your-data',
    shotAlt: 'A chart of a paper’s F1 scores next to your own runs from a CSV; clicking a point opens the table on its page in the paper.',
    points: [
      'Capture a table by drawing a box over it.',
      'Keep a single number with its uncertainty, like 88.5 ± 0.3.',
      'Add your own results from a CSV.',
      'Chart papers’ numbers and yours side by side.',
      'Click any point to open its page in the paper.',
    ],
    tips: [
      'Capture the table once and chart it many ways, instead of retyping numbers.',
      'Keep the ± value: comparisons without it mislead.',
      'Name your CSV columns like the paper’s, so charts line up.',
    ],
    faqs: [
      {
        q: 'Can I extract a table from a scanned PDF?',
        a: 'Capture works on PDFs with a text layer, which covers most born-digital papers. Scanned pages without text need OCR first.',
      },
      {
        q: 'Where does a number on the chart come from?',
        a: 'Each point keeps its paper, page and position. Click it and the paper opens there.',
      },
      {
        q: 'Can I use my own data?',
        a: 'Yes. Add a CSV and chart it next to the numbers captured from papers.',
      },
    ],
    related: ['pdf-highlighter', 'workspaces', 'anchored-notes'],
    guides: ['guides/systematic-literature-review/', 'guides/how-to-read-a-research-paper/', 'guides/extract-data-from-papers/'],
  },
]
