// Who PaperLab is for, one page each at /for/<slug>/. Each names the reader's real problems, then shows which
// features answer them. Audiences follow marketing/strategy.md.
export type Audience = {
  slug: string
  name: string
  /** Short label for links: "PhD students". */
  label: string
  /** One line for the home page card. */
  blurb: string
  title: string
  description: string
  h1: string
  answer: string
  /** Problem → the feature that answers it. */
  problems: { problem: string; answer: string; feature: string }[]
  workflow: string[]
  guides: string[]
  faqs: { q: string; a: string }[]
}

export const AUDIENCES: Audience[] = [
  {
    slug: 'phd-students',
    blurb: 'Hundreds of papers, and every claim traced back to its page.',
    name: 'PhD students',
    label: 'PhD students',
    title: 'PaperLab for PhD students: read, note and cite with confidence',
    description:
      'A free, open-source reading tool for PhD students: notes anchored to the passage, answers that cite the page, a graph of your literature, all on your laptop.',
    h1: 'For PhD students who read hundreds of papers',
    answer:
      'A PhD means reading hundreds of papers and, months later, finding the exact passage behind a claim in your thesis. PaperLab is a free, open-source reader that keeps every note attached to the passage it came from, answers questions about a paper with citations you can click, groups papers by chapter in workspaces, and maps how your literature connects. It runs on your laptop, with no account, and works with free local AI models.',
    problems: [
      {
        problem: '“Where did I read that?”',
        answer: 'Every note keeps its page and position; click it and the paper opens there.',
        feature: 'anchored-notes',
      },
      {
        problem: 'Summaries you can’t trust',
        answer: 'Answers cite the passages they used, so you check a claim in one click.',
        feature: 'ask-a-paper',
      },
      {
        problem: 'Too many papers per chapter',
        answer: 'One workspace per chapter, with all its notes together and a chat across its papers.',
        feature: 'workspaces',
      },
      {
        problem: 'Missing key references',
        answer: 'References several of your papers cite are ranked first, and import in a click when free.',
        feature: 'references',
      },
      {
        problem: 'No budget for AI subscriptions',
        answer: 'Free local models through Ollama; cloud models only if you add a key.',
        feature: 'any-model',
      },
    ],
    workflow: [
      'Add the papers your chapter rests on, or find free copies by title or DOI.',
      'First pass: skim, highlight the claims, write a line on each.',
      'Ask the paper about what you didn’t follow, and keep useful answers as AI notes.',
      'Before writing, read the workspace’s notes, not the papers again.',
    ],
    guides: [
      'guides/how-to-read-a-research-paper/',
      'guides/how-to-take-notes-on-research-papers/',
      'guides/map-your-literature/',
    ],
    faqs: [
      {
        q: 'Is PaperLab free for students?',
        a: 'Yes, for everyone. It is open source under Apache-2.0. Cloud AI models you connect bill you directly; local ones cost nothing.',
      },
      {
        q: 'Will it work on my laptop?',
        a: 'It runs on macOS, Windows and Linux with Docker. Reading and notes need little; a local AI model is comfortable with 16 GB of memory.',
      },
      {
        q: 'Can I use it alongside Zotero?',
        a: 'Yes. Zotero manages references and citations while you write; PaperLab is where you read and think.',
      },
    ],
  },
  {
    slug: 'masters-students',
    blurb: 'Your first literature review, read properly and cited honestly.',
    name: 'Master’s students',
    label: 'Master’s students',
    title: 'PaperLab for master’s students: your first literature review',
    description:
      'Writing your first literature review or thesis? Read papers faster, keep notes you can cite, find free PDFs legally, and check AI answers against the page.',
    h1: 'For master’s students writing their first literature review',
    answer:
      'A master’s thesis is often the first time you have to read research papers seriously and write a literature review. PaperLab helps you read papers in passes, keep notes tied to the passage they came from, find free legal PDFs, and ask papers questions with answers that cite the page, so you learn from the paper instead of trusting a summary. It is free, open source and runs on your computer.',
    problems: [
      {
        problem: 'Papers are hard to read',
        answer: 'Ask a paper what a section means; the answer points at the passage it used.',
        feature: 'ask-a-paper',
      },
      {
        problem: 'Paywalls',
        answer: 'Find papers searches free, legal sources at once and adds free PDFs in a click.',
        feature: 'find-papers',
      },
      {
        problem: 'Notes scattered everywhere',
        answer: 'Highlights and notes live on the page, and every note leads back to its passage.',
        feature: 'pdf-highlighter',
      },
      {
        problem: 'Worried about AI and plagiarism',
        answer: 'AI text is always labelled, so you know exactly what to rewrite and disclose.',
        feature: 'anchored-notes',
      },
    ],
    workflow: [
      'Find 10–20 core papers through free sources.',
      'Read each in passes; highlight claims and methods in different colours.',
      'Ask about what you don’t understand, and check the cited passage.',
      'Write your review from your notes, citing the passages they point to.',
    ],
    guides: [
      'guides/how-to-read-a-research-paper/',
      'guides/find-a-free-pdf-of-a-paper/',
      'guides/check-ai-answers-against-sources/',
    ],
    faqs: [
      {
        q: 'Is it allowed to use AI for my thesis?',
        a: 'It depends on your university. Most allow it with disclosure. PaperLab keeps AI text labelled and apart from yours, which makes disclosure honest.',
      },
      {
        q: 'Do I need to know how to code?',
        a: 'No. Install Docker Desktop, then the PaperLab app, like any other program.',
      },
      {
        q: 'Can it write my literature review?',
        a: 'No, and it doesn’t try. It helps you read, understand and keep track, so what you write is your own.',
      },
    ],
  },
  {
    slug: 'librarians',
    blurb: 'A tool you can recommend: local, open source, no paywall tricks.',
    name: 'Academic librarians',
    label: 'Librarians',
    title: 'PaperLab for academic librarians and research-data managers',
    description:
      'An open-source, local-first reading tool to recommend to researchers: no accounts, AI clearly labelled, no paywall circumvention, and a transparent data policy.',
    h1: 'For librarians who advise researchers on tools',
    answer:
      'Librarians and research-data managers need tools they can recommend without worrying about data, licensing or paywalls. PaperLab is open source under Apache-2.0 and runs on each researcher’s own computer, with no accounts. It finds only free, legal copies of papers and never gets past a paywall. AI text is always labelled with the model that wrote it, and the README lists exactly what each setting sends and where.',
    problems: [
      {
        problem: 'Data leaving the institution',
        answer: 'Local-first: papers and notes stay on the researcher’s machine, with local models available.',
        feature: 'local-first',
      },
      {
        problem: 'Tools that bypass paywalls',
        answer: 'Only free, legal copies; otherwise a link to the publisher.',
        feature: 'find-papers',
      },
      {
        problem: 'Undisclosed AI use',
        answer: 'AI text is stored apart, keeps its model and prompt version, and is always labelled.',
        feature: 'anchored-notes',
      },
      {
        problem: 'Systematic review support',
        answer: 'Free sources, references both ways, and screening and PRISMA counts in the next release.',
        feature: 'references',
      },
    ],
    workflow: [
      'Point researchers to the download page and the privacy notes in the README.',
      'Recommend a local model for sensitive or unpublished work.',
      'Use the systematic-review workflow in library training on evidence synthesis.',
    ],
    guides: [
      'guides/systematic-literature-review/',
      'guides/find-a-free-pdf-of-a-paper/',
      'compare/zotero/',
    ],
    faqs: [
      {
        q: 'Does PaperLab store data in the cloud?',
        a: 'No. Everything is in a local database on the researcher’s computer. Only settings the researcher turns on send data, and each is documented.',
      },
      {
        q: 'Which sources does it search?',
        a: 'arXiv, Crossref, CORE, Unpaywall and Semantic Scholar are free and on by choice; OpenAlex is off until ticked.',
      },
      {
        q: 'Can we contribute a source our researchers use?',
        a: 'Yes. Adding a paper source is one of the most useful contributions; there are open issues labelled paper-source.',
      },
    ],
  },
  {
    slug: 'research-groups',
    blurb: 'Provenance you can check, from student notes to AI answers.',
    name: 'Research groups and PIs',
    label: 'Research groups',
    title: 'PaperLab for research groups and PIs: provenance you can check',
    description:
      'For supervisors and labs: every note traces back to its passage, AI text is labelled with its model, and papers stay on each member’s machine.',
    h1: 'For research groups that care where a claim came from',
    answer:
      'For a principal investigator, the question is not which features a tool has but whether its output can be trusted. PaperLab keeps every note attached to the passage it came from, labels every piece of AI text with the model and prompt that produced it, and keeps papers and notes on each member’s own machine. It is free and open source, so a group can adopt it without licences or accounts.',
    problems: [
      {
        problem: 'Students citing summaries, not papers',
        answer: 'Answers cite the passage they used; checking takes one click.',
        feature: 'ask-a-paper',
      },
      {
        problem: 'Unclear AI involvement',
        answer: 'You, AI, or AI · edited on every note; nothing passes for human-written.',
        feature: 'anchored-notes',
      },
      {
        problem: 'Unpublished work and confidentiality',
        answer: 'Local models and local storage; cloud is always a visible choice.',
        feature: 'local-first',
      },
      {
        problem: 'Onboarding new members to a literature',
        answer: 'A graph of the group’s core papers shows foundations and clusters.',
        feature: 'citation-graph',
      },
    ],
    workflow: [
      'Agree on a highlight colour scheme for the group.',
      'Use workspaces per project; share core paper lists.',
      'Ask students to show the passage behind each claim in meetings.',
    ],
    guides: ['guides/check-ai-answers-against-sources/', 'guides/map-your-literature/', 'guides/chat-with-a-pdf-locally/'],
    faqs: [
      {
        q: 'Can a group share one library?',
        a: 'Not yet: PaperLab is one user per machine. Each member keeps their own library.',
      },
      {
        q: 'Is there a cost per seat?',
        a: 'No. It is free and open source. Only cloud AI models, if you choose them, have a cost.',
      },
      {
        q: 'Can I see a demo for my group?',
        a: 'Yes. Get in touch through the PaperLab page on LinkedIn or GitHub.',
      },
    ],
  },
  {
    slug: 'developers',
    blurb: 'A full open-source RAG app to read, run and contribute to.',
    name: 'Developers and research software engineers',
    label: 'Developers',
    title: 'PaperLab for developers: an open-source RAG app worth reading',
    description:
      'FastAPI, Postgres with pgvector, React, PDF.js, an ARQ worker, an MCP server and a retrieval eval: an open-source RAG codebase to learn from and contribute to.',
    h1: 'For developers who want a real RAG codebase to read',
    answer:
      'PaperLab is a complete, open-source retrieval-augmented generation app: FastAPI and Postgres with pgvector on the back end, React and PDF.js on the front end, an ARQ worker for ingestion, an MCP server for Claude, versioned prompts, end-to-end tests against the real stack with a fake model, and a retrieval eval. It is licensed Apache-2.0, and issues labelled good first issue and paper-source are open for contributors.',
    problems: [
      {
        problem: 'Toy RAG demos',
        answer: 'A full ingestion pipeline: extraction with coordinates, chunking, embeddings, citations to exact rectangles.',
        feature: 'semantic-search',
      },
      {
        problem: 'Learning MCP',
        answer: 'A working MCP server with four tools, tested end to end.',
        feature: 'claude-desktop-mcp',
      },
      {
        problem: 'Provider lock-in',
        answer: 'Adapters for Ollama, Anthropic and any OpenAI-compatible server.',
        feature: 'any-model',
      },
      {
        problem: 'A first open-source contribution',
        answer: 'Add a paper source, or one eval question from your field, in an afternoon.',
        feature: 'find-papers',
      },
    ],
    workflow: [
      'Clone the repository and run the stack with Docker Compose.',
      'Read backend/app/core for the domain logic, free of web-framework imports.',
      'Pick an issue labelled good first issue or paper-source.',
    ],
    guides: ['guides/chat-with-a-pdf-locally/', 'guides/claude-desktop-with-your-papers/'],
    faqs: [
      {
        q: 'What is the tech stack?',
        a: 'FastAPI, Postgres 16 with pgvector, Redis and ARQ, PyMuPDF, ONNX Runtime; React, shadcn/ui and PDF.js; Electron for the desktop app.',
      },
      {
        q: 'How is retrieval evaluated?',
        a: 'A retrieval eval measures recall over a question set, and an answer eval scores model answers. Adding a question from your field is a welcome contribution.',
      },
      {
        q: 'Where do I start contributing?',
        a: 'CONTRIBUTING.md explains the setup and tests; issues labelled good first issue and paper-source are the easiest entry points.',
      },
    ],
  },
]
