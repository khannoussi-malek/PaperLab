import type { Feature } from '../features.ts'

// The library, the connections between papers, models and where PaperLab runs.
export const LIBRARY_FEATURES: Feature[] = [
  {
    slug: 'pdf-library',
    name: 'PDF library',
    tagline: 'Drop in PDFs; they are extracted, split and indexed in the background.',
    title: 'Research PDF library that runs on your computer',
    description:
      'A local library for research PDFs: upload papers, preview first pages, fill in details from OpenAlex, and see retractions. Free, open source, no account.',
    h1: 'A library for your research PDFs, on your own machine',
    answer:
      'PaperLab keeps your research PDFs in a local library. Upload a PDF and a background worker extracts its text with positions, splits it into sections and passages, and indexes it for search. Hover a paper to preview its first page and details. With OpenAlex ticked, it fills in title, authors, year, venue and topics, which you can correct by hand. A retracted paper shows a banner in the reader that can’t be dismissed.',
    shot: 'feature-library',
    shotAlt:
      'The library list with two papers still processing, a hovered paper’s first-page preview with its authors, year and venue, and the Edit details card.',
    points: [
      'Upload PDFs; each is extracted, split into sections and passages, and indexed.',
      'See each paper’s status while it processes, or the reason it failed.',
      'Hover a paper to preview its first page and details.',
      'Fill in title, authors, year, venue and topics from OpenAlex, off until you tick it.',
      'Correct any detail with Edit details; your corrections survive reprocessing.',
      'A retracted paper shows a banner at the top of the reader that can’t be dismissed.',
    ],
    steps: [
      { title: 'Extract', body: 'PyMuPDF pulls out the text with its coordinates, so highlights and citations point at exact spots.' },
      { title: 'Split', body: 'The text is divided into sections and passages sized for search and questions.' },
      { title: 'Index', body: 'Passages are embedded for semantic search once a search model is set up.' },
    ],
    tips: [
      'Start with the ten papers your project rests on, not everything you have.',
      'Fix a wrong title or year once with Edit details: it stays fixed.',
    ],
    faqs: [
      {
        q: 'Do I need an account?',
        a: 'No. PaperLab is one user on one machine, with no accounts. Your library lives in a local Postgres database.',
      },
      {
        q: 'Does it work without internet?',
        a: 'Uploading, reading, highlighting and notes work offline. Finding papers and looking up details need the network.',
      },
      {
        q: 'What happens if a paper fails to process?',
        a: 'Its status shows the reason. Enrichment never fails a paper: with no OpenAlex match or no network, it is still ready.',
      },
    ],
    related: ['find-papers', 'workspaces', 'semantic-search', 'local-first'],
    guides: ['guides/how-to-read-a-research-paper/', 'compare/zotero/', 'guides/organize-research-papers/'],
  },
  {
    slug: 'find-papers',
    name: 'Find papers',
    tagline: 'Search arXiv, Crossref, CORE, Unpaywall and Semantic Scholar at once.',
    title: 'Find research papers and free PDFs across five sources',
    description:
      'Search arXiv, Crossref, CORE, Unpaywall and Semantic Scholar at once by title, DOI or arXiv ID, and add a paper in a click when a free PDF exists.',
    h1: 'Find papers everywhere at once, and add free PDFs in a click',
    answer:
      'Find papers searches by title, DOI or arXiv ID across every paper source you turn on: arXiv, Crossref, CORE, Unpaywall and Semantic Scholar are free, and OpenAlex can be ticked too. It shows one merged list with the sources that found each paper, and adds a paper in a click when a free PDF exists on arXiv, a repository or an open-access publisher. A paper with no free copy links to its page: nothing gets past a paywall.',
    points: [
      'Search by title, DOI or arXiv ID.',
      'Ask every source you enable at once, and see which ones found each paper.',
      'Add a paper in a click when a free PDF exists.',
      'Papers without a free copy link to their page, so you can get them yourself.',
      'Choose sources, optional API keys and a contact email in Settings → Paper sources.',
      'OpenAlex stays off until you tick it, since heavy use can cost money.',
    ],
    tips: [
      'Paste a DOI when you have one: it is the most exact search.',
      'Add a contact email in Settings: Unpaywall needs one, and it gets you polite-pool access elsewhere.',
    ],
    faqs: [
      {
        q: 'Is Find papers free?',
        a: 'arXiv, Crossref, CORE, Unpaywall and Semantic Scholar are free. OpenAlex is free up to a small daily budget and stays off until you tick it.',
      },
      {
        q: 'What is sent to these sources?',
        a: 'What you type, sent to each enabled source that can answer it, then the results’ DOIs to Semantic Scholar and, for results without a free PDF, to Unpaywall. Never a paper’s text.',
      },
      {
        q: 'Can it get paywalled papers?',
        a: 'No. It adds only free, legal copies and otherwise links to the publisher.',
      },
    ],
    related: ['pdf-library', 'references', 'follow-citations'],
    guides: ['guides/find-a-free-pdf-of-a-paper/', 'guides/systematic-literature-review/'],
  },
  {
    slug: 'workspaces',
    name: 'Workspaces',
    tagline: 'Group papers by project; chat across a whole workspace.',
    title: 'Research workspaces: group papers and chat across them',
    description:
      'Group papers into workspaces by project, see all their notes in one place, and ask questions across a whole workspace with answers that cite each paper.',
    h1: 'Group papers by project, and ask across all of them',
    answer:
      'A workspace in PaperLab groups the papers of one project; a paper can be in several. It shows every note from its papers in one place, and its chat answers questions across the whole workspace, citing passages from each paper and your notes. It is where a literature review, a thesis chapter or a reading group lives.',
    shot: 'feature-workspaces',
    shotAlt:
      'A workspace called Dense retrieval, open on its Chat tab, where an AI answer cites passages from its papers and one of your notes.',
    points: [
      'Put a paper in as many workspaces as it serves.',
      'See all notes from a workspace’s papers together.',
      'Chat with the whole workspace; answers cite passages from its papers and your notes.',
      'Workspaces show up as a layer in the library graph.',
    ],
    tips: [
      'One workspace per question or chapter works better than one per topic.',
      'Ask the workspace “where do these papers disagree?” and check the citations.',
    ],
    faqs: [
      {
        q: 'Can one paper be in several workspaces?',
        a: 'Yes. Its notes and highlights are shared, so you never duplicate work.',
      },
      {
        q: 'What does workspace chat need?',
        a: 'A chat model and the search model, because it searches passages across all the workspace’s papers.',
      },
      {
        q: 'Can Claude Desktop search a workspace?',
        a: 'Yes. The MCP server’s search_library can search the whole library or one workspace.',
      },
    ],
    related: ['ask-a-paper', 'anchored-notes', 'citation-graph', 'claude-desktop-mcp'],
    guides: ['guides/systematic-literature-review/', 'guides/how-to-take-notes-on-research-papers/', 'guides/write-a-related-work-section/', 'guides/organize-research-papers/'],
  },
  {
    slug: 'references',
    name: 'References and similar papers',
    tagline: 'What a paper cites and who cited it since, ranked for your library.',
    title: 'References, citing papers and similar papers, ranked for you',
    description:
      'See what a paper cites and what has cited it since, ranked for your library, import free PDFs in a click, and find similar papers via Semantic Scholar.',
    h1: 'Follow a paper’s references both ways, ranked for your library',
    answer:
      'A paper’s References tab in PaperLab lists what it cites and what has cited it since, ranked for your library: references several of your papers cite come first, then ones close to what you write notes about, then ones with a free PDF. Import a reference in a click when a free PDF exists. The Similar tab suggests papers like it from Semantic Scholar, added the same way.',
    shot: 'feature-references',
    shotAlt:
      'A paper’s References tab ranked for your library, one reference marked In library and one offering Import, beside the Similar panel suggesting papers that read alike.',
    points: [
      'Backward: every reference the paper cites.',
      'Forward: papers that have cited it since.',
      'Ranked by how many of your papers cite each, then by closeness to your notes, then by free PDF.',
      'Import in a click when a free PDF exists; In library shows what you already have.',
      'Similar suggests papers that read alike, from Semantic Scholar.',
    ],
    tips: [
      'A reference three of your papers cite is a foundation: add it first.',
      'Use forward citations to see whether a result held up.',
    ],
    faqs: [
      {
        q: 'Where do references come from?',
        a: 'From Semantic Scholar, by the paper’s DOI, arXiv ID or title, and from OpenAlex when you tick it. Never the paper’s text.',
      },
      {
        q: 'What is the ranking based on?',
        a: 'Co-citation in your own library first, then closeness to what you write notes about, then whether a free PDF exists.',
      },
      {
        q: 'Is this snowballing?',
        a: 'It is the manual version: backward and forward references for one paper. The systematic-review workflow snowballs across included papers.',
      },
    ],
    related: ['follow-citations', 'citation-graph', 'find-papers'],
    guides: ['guides/map-your-literature/', 'guides/systematic-literature-review/', 'guides/write-a-related-work-section/'],
  },
  {
    slug: 'citation-graph',
    name: 'Library graph',
    tagline: 'Citations, authors, topics, notes and similar content, in five views.',
    title: 'Citation graph of your research library, in five views',
    description:
      'See your papers as a network: citations, workspaces, shared notes, authors, topics and similar content. Explore in 2D, 3D, a matrix, a timeline or rings.',
    h1: 'See how the papers in your library connect',
    answer:
      'PaperLab’s Graph page draws your library as a network. Each kind of link is a layer you switch on or off: what cites what, papers in the same workspace, a note anchored on two papers, a shared author or topic, and papers that simply read alike. Click a paper to focus it and list its connections, draw your own labelled link like “builds on”, and switch between five views: 2D, 3D, Matrix, Timeline and Rings.',
    shot: 'feature-see-connections',
    shotAlt:
      'The library as a graph: papers as dots coloured by workspace, joined by citations and similar content, with the link layers and their counts, and tabs for the 2D, 3D, Matrix, Timeline and Rings views.',
    points: [
      'Layers: citations, shared workspace, shared note, shared author, shared topic, similar content.',
      'Click a paper to focus it and list its connections.',
      'Draw your own link between two papers, with a label like “builds on”.',
      '2D map, and a 3D one you can turn when clusters overlap.',
      'Matrix: exactly which papers connect and how, as a table a screen reader can read.',
      'Timeline by year published or date added, and Rings of distance from one paper.',
    ],
    tips: [
      'Turn on one layer at a time: citations first, then similar content, to spot papers that read alike but never cite each other.',
      'Use Rings around your key paper to find what is two links away.',
    ],
    faqs: [
      {
        q: 'Is the graph accessible?',
        a: 'Yes. The Matrix view shows every connection as a table a screen reader can read cell by cell.',
      },
      {
        q: 'Where does “similar content” come from?',
        a: 'From the same embeddings search uses, so it needs a search model.',
      },
      {
        q: 'How is this different from Connected Papers?',
        a: 'Connected Papers maps papers from an online database. PaperLab graphs the papers you actually have, with your notes and workspaces, on your machine.',
      },
    ],
    related: ['references', 'workspaces', 'semantic-search'],
    guides: ['guides/map-your-literature/', 'compare/obsidian/'],
  },
  {
    slug: 'any-model',
    name: 'Any model',
    tagline: 'Ollama, Anthropic or any OpenAI-compatible server, picked per question.',
    title: 'Use any AI model: Ollama, Anthropic or OpenAI-compatible',
    description:
      'Pick the model per question: a local Ollama model, Anthropic with your key, or any OpenAI-compatible server. Pull Ollama models with live progress.',
    h1: 'Use the model you trust, local or cloud',
    answer:
      'PaperLab doesn’t lock you to one AI provider. Add connections in Settings: a local Ollama model, Anthropic with your own key, or any OpenAI-compatible server, including OpenAI, OpenRouter, Groq, Mistral, DeepSeek, Gemini, LM Studio, vLLM and llama.cpp. Pick the model per question in the chat panel. Cloud models are tagged “Cloud”, and every answer keeps the model and connection that wrote it.',
    points: [
      'Connect Ollama, Anthropic or any OpenAI-compatible server.',
      'Test a connection, choose which models chat lists, and set the default.',
      'Pull and delete Ollama models from Settings, with live progress.',
      'Pick the model per question from the chat panel.',
      'Cloud models are tagged “Cloud”; local ones keep your text on your machine.',
      'Keys stay in your local database and are never sent back to the browser.',
    ],
    tips: [
      'Try qwen3:8b on Ollama as a first local model on a 16 GB laptop.',
      'Use a cloud model for hard questions on published papers, and a local one for unpublished work.',
    ],
    faqs: [
      {
        q: 'Which local models work?',
        a: 'Any model Ollama, LM Studio, vLLM or llama.cpp serves. Small models around 7–8 billion parameters run on a 16 GB laptop.',
      },
      {
        q: 'Where are API keys stored?',
        a: 'In your local database. They are never sent back to the browser.',
      },
      {
        q: 'Do I need a model at all?',
        a: 'No. Reading, highlighting and notes work without one. Chat and suggestions need one.',
      },
    ],
    related: ['ask-a-paper', 'local-first', 'semantic-search'],
    guides: ['guides/chat-with-a-pdf-locally/', 'compare/ai-pdf-tools/', 'guides/local-llm-for-research/'],
  },
  {
    slug: 'semantic-search',
    name: 'Semantic search',
    tagline: 'Search passages by meaning, with a built-in model or one you pick.',
    title: 'Semantic search across your research papers',
    description:
      'Search your papers by meaning, not keywords. A built-in local search model, or Ollama, OpenAI, Gemini or an OpenAI-compatible server if you prefer.',
    h1: 'Search your papers by meaning, not just words',
    answer:
      'PaperLab indexes every passage of your papers as a vector, so search, chat on long papers and workspaces find text by meaning rather than exact words. The built-in search model, nomic-embed-text v1.5, runs on your machine and downloads once (548 MB). You can also choose Ollama’s nomic-embed-text, OpenAI, Gemini or an OpenAI-compatible server; a cloud source asks first, with an estimate of what it sends and costs.',
    points: [
      'Every passage is embedded and stored in a local Postgres database with pgvector.',
      'The built-in model runs locally on ONNX Runtime and downloads once.',
      'Reading, notes and chat on short papers work before it is downloaded.',
      'The graph’s similar-content layer and the References ranking use the same index.',
      'Choose another source in Settings → Search; switching re-embeds in the background (next release).',
      'A cloud source asks before the first send, with a cost estimate (next release).',
    ],
    steps: [
      { title: 'Embed', body: 'Each passage becomes 768 numbers describing its meaning.' },
      { title: 'Store', body: 'The vectors live next to your papers in a local database.' },
      { title: 'Match', body: 'A question is embedded the same way, and the closest passages are returned.' },
    ],
    tips: [
      'Ask in full sentences: meaning-based search works better with context than with keywords.',
      'Keep the built-in model if privacy matters most: nothing leaves your machine.',
    ],
    faqs: [
      {
        q: 'Do I need the search model?',
        a: 'For chatting with long papers, workspace chat, Claude’s library search, similar content and note ranking, yes. Reading and notes work without it.',
      },
      {
        q: 'How big is the search model?',
        a: 'About 548 MB, downloaded once into a local volume.',
      },
      {
        q: 'Can I use OpenAI or Gemini embeddings?',
        a: 'Yes, from the next release: pick them in Settings → Search. PaperLab asks before sending anything to a cloud source.',
      },
    ],
    related: ['ask-a-paper', 'citation-graph', 'any-model'],
    guides: ['guides/chat-with-a-pdf-locally/', 'guides/check-ai-answers-against-sources/', 'guides/local-llm-for-research/'],
  },
  {
    slug: 'claude-desktop-mcp',
    name: 'Claude Desktop (MCP)',
    tagline: 'An MCP server lets Claude search and quote your library.',
    title: 'MCP server for research papers: PaperLab in Claude Desktop',
    description:
      'Connect Claude Desktop or Claude Code to your local research library with PaperLab’s MCP server: search papers, read notes, find connections, save notes.',
    h1: 'Your research library, inside Claude Desktop',
    answer:
      'PaperLab includes an MCP server, so Claude Desktop, Claude Code or another MCP client can work with your library. It offers four tools: search_library finds the passages closest to a question in the library or one workspace, get_paper reads a paper’s details, outline and notes, related_papers finds connected papers, and create_note saves a note on a passage Claude quotes exactly, marked AI. Connect Claude sets it up for your system.',
    points: [
      'search_library: passages closest to a question, in the library or one workspace.',
      'get_paper: a paper’s details, section outline, workspaces and every note with its author.',
      'related_papers: library papers connected to one, up to three links away.',
      'create_note: a note on a passage Claude quotes exactly, marked AI and highlighted.',
      'Connect Claude fills in the config for macOS, Windows or Linux and checks the connection.',
    ],
    tips: [
      'Keep PaperLab running (Keep running in Settings) so Claude can reach it with the window closed.',
      'Ask Claude to quote passages with pages, then open them in PaperLab to check.',
    ],
    faqs: [
      {
        q: 'What does Claude receive?',
        a: 'What its tools return: passages, paper details, workspace names and notes. Claude Desktop sends those to Anthropic with the conversation.',
      },
      {
        q: 'Does it work with Claude Code?',
        a: 'Yes, with claude mcp add. Connect Claude shows the exact command.',
      },
      {
        q: 'Can Claude change my notes?',
        a: 'It can add notes on passages it quotes, always marked AI. It can’t edit or delete yours.',
      },
    ],
    related: ['workspaces', 'anchored-notes', 'desktop-app', 'semantic-search'],
    guides: ['guides/claude-desktop-with-your-papers/', 'guides/chat-with-a-pdf-locally/'],
  },
  {
    slug: 'desktop-app',
    name: 'Desktop app',
    tagline: 'macOS, Windows and Linux; announces updates, never installs them.',
    title: 'PaperLab desktop app for macOS, Windows and Linux',
    description:
      'Download PaperLab for macOS, Windows or Linux: no repository to clone, no server to run. Optional setup, menu-bar mode, update notices and backups.',
    h1: 'A desktop app for macOS, Windows and Linux',
    answer:
      'PaperLab installs like any desktop app for macOS, Windows or Linux, with Docker as the one thing to install first. It starts everything it needs, with no repository to clone and no server to run. A short first run offers a chat model and a search model, both optional. Turn on Keep running and it stays in the menu bar for Claude Desktop. It announces updates but never installs them, and saves a database backup before each new version first starts.',
    shot: 'feature-the-app',
    shotAlt:
      'The PaperLab window showing the first-run setup offering a chat model with a Skip setup line, and the menu-bar icon with Open PaperLab and Quit PaperLab.',
    points: [
      'Installers for macOS (Apple silicon and Intel), Windows, and Linux (AppImage or .deb).',
      'A first run that offers a chat and a search model; both can be skipped.',
      'Closing the window stops PaperLab; Keep running leaves it in the menu bar.',
      'Checks GitHub for updates on launch and offers a link; never installs by itself.',
      'Saves a database backup before a new version first starts.',
    ],
    tips: [
      'Open Docker Desktop once before the first launch.',
      'Turn off the update check in Settings → Desktop app if you want zero network requests at launch.',
    ],
    faqs: [
      {
        q: 'Why does it need Docker?',
        a: 'PaperLab runs its database, search and background worker in containers, so the app stays small and your library stays in one place.',
      },
      {
        q: 'Is the app signed?',
        a: 'Not yet, so your system asks before the first launch. The download page shows the steps for each system.',
      },
      {
        q: 'Does it phone home?',
        a: 'Only the update check on launch, which asks GitHub whether a newer version exists. You can turn it off.',
      },
    ],
    related: ['local-first', 'claude-desktop-mcp', 'pdf-library'],
    guides: ['guides/chat-with-a-pdf-locally/', 'guides/claude-desktop-with-your-papers/'],
  },
  {
    slug: 'local-first',
    name: 'Local-first and private',
    tagline: 'One user, one machine, no account; you choose what leaves it.',
    title: 'Private, local-first research tool: your papers stay yours',
    description:
      'PaperLab keeps PDFs, notes and search on your computer. No account. Local models keep text on your machine, and every setting that sends data says so.',
    h1: 'Your papers and notes stay on your computer',
    answer:
      'PaperLab is local-first: one user, one machine, no accounts. Your PDFs, notes and search index live in a local Postgres database. With a local model, the text of your papers and notes never leaves your computer. A model or search source tagged “Cloud” receives what is sent to it, and PaperLab asks before the first send to a cloud search source. The README lists what every setting sends and where.',
    points: [
      'No account, no sign-up, no telemetry.',
      'PDFs, notes and the search index live in a local database.',
      'Local models keep all text on your machine; cloud ones are tagged “Cloud”.',
      'Metadata lookups send a DOI or title, never a paper’s text.',
      'The only automatic request is the update check, which you can turn off.',
      'AI text is stored apart from yours and always labelled.',
    ],
    tips: [
      'For unpublished work or peer reviews, use a local model and the built-in search model.',
      'Read the README’s Principles section: it lists every request, source by source.',
    ],
    faqs: [
      {
        q: 'Is PaperLab GDPR-friendly?',
        a: 'With local models, your documents never leave your machine, which keeps most data-protection questions simple. Cloud models and sources are your choice, per connection.',
      },
      {
        q: 'Does PaperLab collect analytics?',
        a: 'No. The desktop app’s only automatic request is the update check.',
      },
      {
        q: 'Can I back up my library?',
        a: 'Yes. The app saves a backup before each upgrade, and a one-line command exports the database any time.',
      },
    ],
    related: ['any-model', 'desktop-app', 'semantic-search'],
    guides: ['guides/chat-with-a-pdf-locally/', 'compare/ai-pdf-tools/', 'guides/local-llm-for-research/'],
  },
]
