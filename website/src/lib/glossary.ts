// Terms researchers look up, one page each at /glossary/<slug>/. Each defines the term first, in plain words,
// then says where it shows up in PaperLab, linking the features and guides that use it.
export type Term = {
  slug: string
  name: string
  /** <title>, 70 characters at most. */
  title: string
  /** Meta description, 160 characters at most. */
  description: string
  /** The definition: the paragraph a search snippet or an assistant can quote. */
  definition: string
  more: string[]
  /** Where it appears in PaperLab; may name the feature. */
  inPaperLab: string
  features: string[]
  guides: string[]
  related: string[]
}

export const TERMS: Term[] = [
  {
    slug: 'rag',
    name: 'Retrieval-augmented generation (RAG)',
    title: 'What is retrieval-augmented generation (RAG)?',
    description: 'RAG explained simply: find the relevant passages in real documents first, then ask a language model to answer from them, and cite them.',
    definition:
      'Retrieval-augmented generation (RAG) is a way of answering questions with a language model in two steps: first retrieve the passages from real documents that are closest to the question, then have the model answer from those passages. Because the answer is built on retrieved text, it can cite its sources, and it invents less than a model answering from memory.',
    more: [
      'A RAG system splits documents into passages, turns each into an embedding, and stores them in a vector index. A question is embedded the same way, and the nearest passages are sent to the model with instructions to answer only from them.',
      'RAG doesn’t remove mistakes: retrieval can miss the right passage, and a model can still misread one. That is why answers should cite the passages they used.',
    ],
    inPaperLab:
      'PaperLab’s chat is RAG over your own PDFs: a long paper is searched first and only the closest passages are sent; answers cite them like [C1].',
    features: ['ask-a-paper', 'semantic-search'],
    guides: ['guides/check-ai-answers-against-sources/', 'guides/chat-with-a-pdf-locally/'],
    related: ['embeddings', 'vector-database', 'hallucination'],
  },
  {
    slug: 'embeddings',
    name: 'Embeddings',
    title: 'What are embeddings? Text as numbers, explained',
    description: 'Embeddings turn text into lists of numbers so that texts with similar meaning sit close together. The basis of semantic search and RAG.',
    definition:
      'An embedding is a list of numbers that represents the meaning of a piece of text, produced by an embedding model. Texts with similar meaning get embeddings that are close together, so comparing embeddings finds related passages even when they share no words. Embeddings power semantic search, recommendations and retrieval-augmented generation.',
    more: [
      'A typical text embedding has a few hundred to a few thousand numbers. Closeness is usually measured with cosine similarity.',
      'Embedding models are much smaller than chat models and can run on a laptop, which makes private search possible.',
    ],
    inPaperLab:
      'PaperLab stores a 768-number embedding for every passage, made by the built-in nomic-embed-text model on your machine or by a source you choose.',
    features: ['semantic-search', 'citation-graph'],
    guides: ['guides/chat-with-a-pdf-locally/'],
    related: ['rag', 'vector-database', 'semantic-search-term'],
  },
  {
    slug: 'semantic-search-term',
    name: 'Semantic search',
    title: 'What is semantic search? Searching by meaning',
    description: 'Semantic search finds text by meaning instead of exact words, by comparing embeddings. How it differs from keyword search, and when to use each.',
    definition:
      'Semantic search finds documents or passages by meaning rather than by matching words. It embeds the query and every passage, then returns the passages whose embeddings are closest to the query’s. A search for “how the model is trained” can find “we pre-train on two tasks”, which keyword search would miss.',
    more: [
      'Keyword search is still better for exact names, codes and quotations. Many systems combine both.',
      'Asking in full sentences helps: the embedding captures more of what you mean.',
    ],
    inPaperLab:
      'Semantic search sits behind PaperLab’s chat on long papers, workspace chat, Claude’s search_library tool and the graph’s similar-content layer.',
    features: ['semantic-search', 'workspaces', 'claude-desktop-mcp'],
    guides: ['guides/chat-with-a-pdf-locally/'],
    related: ['embeddings', 'vector-database', 'rag'],
  },
  {
    slug: 'vector-database',
    name: 'Vector database',
    title: 'What is a vector database? pgvector and friends',
    description: 'A vector database stores embeddings and finds the nearest ones fast. What it is, why RAG needs one, and how pgvector adds it to Postgres.',
    definition:
      'A vector database stores embeddings and finds the ones nearest to a query embedding quickly. It is the index behind semantic search and retrieval-augmented generation. It can be a dedicated product or an extension of a regular database, such as pgvector for PostgreSQL, which keeps vectors next to the rest of your data.',
    more: [
      'Nearest-neighbour search over millions of vectors uses approximate indexes such as HNSW or IVF, trading a little accuracy for a lot of speed.',
      'For a personal library of hundreds or thousands of papers, a single Postgres database with pgvector is plenty.',
    ],
    inPaperLab: 'PaperLab keeps papers, notes and passage embeddings in one local Postgres database with pgvector.',
    features: ['semantic-search', 'local-first'],
    guides: ['guides/chat-with-a-pdf-locally/'],
    related: ['embeddings', 'rag', 'semantic-search-term'],
  },
  {
    slug: 'hallucination',
    name: 'AI hallucination',
    title: 'What is an AI hallucination? Invented facts and citations',
    description: 'An AI hallucination is a confident statement a model made up, like a fake citation. Why it happens and how to check answers about papers.',
    definition:
      'An AI hallucination is a statement a language model produces confidently that isn’t supported by its sources or by reality, such as a claim a paper never makes or a citation to a paper that doesn’t exist. It happens because models generate likely-sounding text; grounding answers in retrieved passages and citing them reduces it and makes it easy to catch.',
    more: [
      'Invented references are the classic case in research: plausible authors, title and journal, no such paper.',
      'The fix is verification: open the cited passage, and resolve every DOI.',
    ],
    inPaperLab:
      'PaperLab answers from your own PDFs and cites each passage, so checking a claim is one click; AI text is always labelled.',
    features: ['ask-a-paper', 'anchored-notes'],
    guides: ['guides/check-ai-answers-against-sources/'],
    related: ['rag', 'doi'],
  },
  {
    slug: 'mcp',
    name: 'Model Context Protocol (MCP)',
    title: 'What is the Model Context Protocol (MCP)? MCP servers explained',
    description: 'MCP is an open protocol that lets AI apps like Claude Desktop call tools on your machine through MCP servers. What it is and how it is used.',
    definition:
      'The Model Context Protocol (MCP) is an open protocol that lets AI applications such as Claude Desktop, Claude Code and other clients call tools and read data provided by separate programs called MCP servers. A server might search your files, query a database or read your research library; the client decides when to call it and sends what it returns to the model.',
    more: [
      'An MCP server runs locally or remotely and describes its tools with names, inputs and descriptions the model can read.',
      'What a tool returns becomes part of the conversation, so it goes wherever the conversation goes, for Claude Desktop to Anthropic.',
    ],
    inPaperLab:
      'PaperLab ships an MCP server with four tools, search_library, get_paper, related_papers and create_note, so Claude can work with your library.',
    features: ['claude-desktop-mcp'],
    guides: ['guides/claude-desktop-with-your-papers/'],
    related: ['local-llm', 'rag'],
  },
  {
    slug: 'local-llm',
    name: 'Local LLM',
    title: 'What is a local LLM? Running AI models on your own computer',
    description: 'A local LLM is a language model that runs on your own computer, through Ollama or LM Studio, so your text never leaves it. What you need and why.',
    definition:
      'A local LLM is a large language model that runs on your own computer instead of a provider’s servers, usually through Ollama, LM Studio, llama.cpp or vLLM. Your prompts and documents never leave the machine, there is no per-question cost, and it works offline. The trade-off is that models small enough for a laptop are less capable than the largest cloud models.',
    more: [
      'Models of about 7–8 billion parameters run on a laptop with 16 GB of memory; Apple silicon and modern GPUs make them faster.',
      'For questions about one paper with the right passages supplied, a small local model is often enough.',
    ],
    inPaperLab: 'PaperLab works with Ollama and other local servers out of the box; cloud models are tagged “Cloud”.',
    features: ['any-model', 'local-first'],
    guides: ['guides/chat-with-a-pdf-locally/', 'compare/ai-pdf-tools/'],
    related: ['mcp', 'rag'],
  },
  {
    slug: 'doi',
    name: 'DOI (Digital Object Identifier)',
    title: 'What is a DOI? Digital Object Identifiers for papers',
    description: 'A DOI is a permanent identifier for a paper, like 10.1000/xyz123. What it is, how to resolve it, and why it is the best way to find a paper.',
    definition:
      'A DOI (Digital Object Identifier) is a permanent identifier for a published work, such as a journal article, written like 10.48550/arXiv.1810.04805. Putting https://doi.org/ in front of it always leads to the work’s current page, even if the publisher moves it. DOIs are the most reliable way to find, cite and check a paper.',
    more: [
      'Crossref and DataCite register most scholarly DOIs; their records hold the title, authors and more.',
      'A citation whose DOI doesn’t resolve, or resolves to a different paper, is a red flag.',
    ],
    inPaperLab: 'Find papers searches by DOI, and metadata lookups send only a DOI or title, never a paper’s text.',
    features: ['find-papers', 'references'],
    guides: ['guides/find-a-free-pdf-of-a-paper/', 'guides/check-ai-answers-against-sources/'],
    related: ['open-access', 'preprint'],
  },
  {
    slug: 'preprint',
    name: 'Preprint',
    title: 'What is a preprint? arXiv, bioRxiv and peer review',
    description: 'A preprint is a paper shared publicly before peer review, on servers like arXiv or bioRxiv. How preprints differ from published papers.',
    definition:
      'A preprint is a version of a research paper that its authors share publicly before, or alongside, peer review, on a server such as arXiv, bioRxiv, medRxiv or SSRN. Preprints make research free to read and fast to share. They haven’t necessarily been peer-reviewed, so check whether a published version exists and what changed.',
    more: [
      'An accepted manuscript, or postprint, is the peer-reviewed text before the publisher’s formatting.',
      'Many fields, from physics to machine learning, read preprints first.',
    ],
    inPaperLab: 'PaperLab searches arXiv among its free sources and adds a preprint’s PDF in a click.',
    features: ['find-papers', 'pdf-library'],
    guides: ['guides/find-a-free-pdf-of-a-paper/'],
    related: ['open-access', 'doi'],
  },
  {
    slug: 'open-access',
    name: 'Open access',
    title: 'What is open access? Gold, green and free-to-read papers',
    description: 'Open access means research anyone can read for free. Gold and green open access explained, and how to find the free version of a paper.',
    definition:
      'Open access means a research output can be read online for free, without a subscription. In gold open access the publisher makes the final version free; in green open access the author deposits a version in a repository or on a preprint server. Services such as Unpaywall and CORE find these free, legal copies from a DOI.',
    more: [
      'Many funders require open access, so a free version of recent research often exists somewhere.',
      'Legal free copies are safer than shadow libraries, whose files can be altered.',
    ],
    inPaperLab: 'PaperLab adds a paper only when a free, legal copy exists, and otherwise links to the publisher.',
    features: ['find-papers', 'references'],
    guides: ['guides/find-a-free-pdf-of-a-paper/'],
    related: ['preprint', 'doi'],
  },
  {
    slug: 'co-citation',
    name: 'Co-citation',
    title: 'What is co-citation? How papers become related',
    description: 'Two papers are co-cited when a third paper cites both. How co-citation reveals related work, and how it differs from bibliographic coupling.',
    definition:
      'Co-citation is when two papers are both cited by a third paper. The more often two papers are cited together, the more the research community treats them as related. Co-citation analysis maps the intellectual structure of a field, and is the idea behind many “related papers” tools.',
    more: [
      'Co-citation favours older, well-cited papers, since it needs citing papers to accumulate.',
      'Its mirror, bibliographic coupling, relates papers that cite the same sources.',
    ],
    inPaperLab:
      'PaperLab’s References tab ranks first the references that several papers in your library cite: co-citation within your own library.',
    features: ['references', 'citation-graph'],
    guides: ['guides/map-your-literature/'],
    related: ['bibliographic-coupling', 'snowballing'],
  },
  {
    slug: 'bibliographic-coupling',
    name: 'Bibliographic coupling',
    title: 'What is bibliographic coupling? Papers that cite the same work',
    description: 'Two papers are bibliographically coupled when they cite the same sources. Why it finds recent related work that co-citation misses.',
    definition:
      'Bibliographic coupling links two papers that cite one or more of the same sources. The more references they share, the more likely they work on the same problem. Because it depends only on a paper’s own reference list, it relates new papers immediately, before anyone has cited them.',
    more: [
      'Coupling is fixed once a paper is published; co-citation grows over time.',
      'Together they give a good map: coupling for recent work, co-citation for foundations.',
    ],
    inPaperLab: 'PaperLab’s graph links your papers by citations, shared authors, topics and similar content, in five views.',
    features: ['citation-graph', 'references'],
    guides: ['guides/map-your-literature/'],
    related: ['co-citation', 'snowballing'],
  },
  {
    slug: 'snowballing',
    name: 'Snowballing',
    title: 'What is snowballing in a literature review?',
    description: 'Snowballing finds studies by following the references of included papers backward and their citations forward. How to do it systematically.',
    definition:
      'Snowballing is a literature search method that starts from papers you have already included and follows their references (backward snowballing) and the papers that cite them (forward snowballing). New relevant papers are screened with the same criteria and snowballed in turn, until no new studies appear. It catches studies that database searches miss.',
    more: [
      'Report snowballed studies separately in your PRISMA flow diagram.',
      'Forward snowballing needs a citation index, such as Semantic Scholar, OpenAlex or Crossref.',
    ],
    inPaperLab:
      'PaperLab’s References tab shows both directions for any paper; systematic snowballing across included papers arrives in the next release.',
    features: ['references', 'follow-citations'],
    guides: ['guides/systematic-literature-review/', 'guides/map-your-literature/'],
    related: ['prisma', 'systematic-review', 'co-citation'],
  },
  {
    slug: 'prisma',
    name: 'PRISMA',
    title: 'What is PRISMA? The flow diagram and checklist explained',
    description: 'PRISMA 2020 is the reporting guideline for systematic reviews: a checklist and a flow diagram of records found, screened, excluded and included.',
    definition:
      'PRISMA (Preferred Reporting Items for Systematic Reviews and Meta-Analyses) is a reporting guideline for systematic reviews. Its 2020 version has a 27-item checklist and a flow diagram showing how many records were identified, removed as duplicates, screened, excluded with reasons, and included. Most journals ask systematic reviews to follow it.',
    more: [
      'The flow diagram is easy when you count at each stage as you go, and painful to reconstruct at the end.',
      'Extensions exist for scoping reviews (PRISMA-ScR) and other review types.',
    ],
    inPaperLab: 'PaperLab counts records at every stage and shows the PRISMA numbers, from the next release.',
    features: ['workspaces', 'find-papers'],
    guides: ['guides/systematic-literature-review/'],
    related: ['systematic-review', 'snowballing'],
  },
  {
    slug: 'systematic-review',
    name: 'Systematic review',
    title: 'What is a systematic review? Definition and steps',
    description: 'A systematic review answers a focused question with a predefined, reproducible method for finding, selecting and appraising all relevant studies.',
    definition:
      'A systematic review answers a focused research question by finding, selecting and appraising all the relevant studies with a predefined, reproducible method. Its protocol fixes the search, the inclusion criteria and the analysis in advance, and its report, usually following PRISMA, shows every step. It differs from a narrative review, which the author shapes freely.',
    more: [
      'A meta-analysis is a statistical combination of the results, often part of a systematic review.',
      'Scoping reviews map a field more broadly, with less appraisal.',
    ],
    inPaperLab: 'See PaperLab for systematic reviews: free sources, references both ways, screening and PRISMA counts.',
    features: ['workspaces', 'find-papers', 'references'],
    guides: ['guides/systematic-literature-review/'],
    related: ['prisma', 'snowballing'],
  },
  {
    slug: 'chunking',
    name: 'Chunking',
    title: 'What is chunking? Splitting documents for AI search',
    description: 'Chunking splits a long document into passages small enough to embed, search and send to a model. Why chunk size matters for AI answers.',
    definition:
      'Chunking is splitting a long document into smaller passages, or chunks, before indexing it for search or retrieval-augmented generation. Each chunk is embedded and retrieved on its own, so chunk size is a trade-off: too small and a passage loses its context, too large and it mixes topics and wastes the model’s context window.',
    more: [
      'Good chunkers follow the document’s structure, such as sections and paragraphs, instead of cutting at a fixed number of characters.',
      'Keeping each chunk’s page and position lets an answer cite exactly where its text came from.',
    ],
    inPaperLab: 'PaperLab splits each paper into sections and passages that keep their page coordinates, so a cited passage can be flashed on the page.',
    features: ['pdf-library', 'ask-a-paper'],
    guides: ['guides/chat-with-a-pdf-locally/'],
    related: ['rag', 'embeddings', 'context-window'],
  },
  {
    slug: 'context-window',
    name: 'Context window',
    title: 'What is a context window? How much an AI model can read',
    description: 'A context window is how much text a language model can take in at once, measured in tokens. Why long papers need retrieval, not just a bigger window.',
    definition:
      'A context window is the maximum amount of text a language model can consider at once, counted in tokens (roughly three quarters of a word each). Everything in one request has to fit: instructions, the documents you supply, the conversation and the answer. A short paper can fit whole; a long paper or a library needs retrieval to pick what goes in.',
    more: [
      'Local models often have smaller windows than the largest cloud models, which makes choosing the right passages more important.',
      'Filling the window with barely relevant text can make answers worse, not better.',
    ],
    inPaperLab: 'PaperLab sends a short paper whole and searches a long one first, sending only the most relevant passages and your notes.',
    features: ['ask-a-paper', 'any-model'],
    guides: ['guides/local-llm-for-research/'],
    related: ['rag', 'chunking', 'local-llm'],
  },
  {
    slug: 'citation-graph',
    name: 'Citation graph',
    title: 'What is a citation graph? Networks of papers explained',
    description: 'A citation graph is a network where papers are nodes and citations are links. How to read one to find foundations, clusters and new directions.',
    definition:
      'A citation graph is a network in which each paper is a node and each citation is a directed link from the citing paper to the cited one. Reading it shows a field’s foundations (heavily cited nodes), its sub-topics (clusters) and the papers that bridge them. Related measures such as co-citation and bibliographic coupling are computed from it.',
    more: [
      'Large citation graphs are built from databases such as Crossref, OpenAlex and Semantic Scholar.',
      'A personal graph of the papers you have read is smaller but tells you about your own coverage and blind spots.',
    ],
    inPaperLab: 'PaperLab graphs your library by citations and more, in 2D, 3D, a matrix, a timeline or rings around one paper.',
    features: ['citation-graph', 'references'],
    guides: ['guides/map-your-literature/'],
    related: ['co-citation', 'bibliographic-coupling', 'snowballing'],
  },
  {
    slug: 'retraction',
    name: 'Retraction',
    title: 'What is a retracted paper? Retractions and how to spot them',
    description: 'A retraction withdraws a published paper because of serious errors or misconduct. How to check whether a paper you cite was retracted.',
    definition:
      'A retraction is the formal withdrawal of a published paper by its journal, because of serious errors, unreliable data, plagiarism or misconduct. The paper usually stays online with a retraction notice. Citing a retracted paper as valid evidence is a real risk, since many retracted papers keep being cited for years.',
    more: [
      'Check a paper’s publisher page, Crossref metadata or the Retraction Watch database before relying on it.',
      'A correction (erratum) fixes part of a paper; a retraction withdraws it.',
    ],
    inPaperLab: 'A retracted paper in PaperLab shows a banner at the top of the reader that can’t be dismissed.',
    features: ['pdf-library', 'find-papers'],
    guides: ['guides/check-ai-answers-against-sources/', 'guides/systematic-literature-review/'],
    related: ['doi', 'peer-review'],
  },
  {
    slug: 'reference-manager',
    name: 'Reference manager',
    title: 'What is a reference manager? Zotero, Mendeley and more',
    description: 'A reference manager stores the papers you cite and formats citations and bibliographies. How it differs from a reading tool, and when you need both.',
    definition:
      'A reference manager, or citation manager, stores bibliographic records for the sources you use and inserts formatted citations and bibliographies into your writing in styles such as APA or IEEE. Zotero, Mendeley and EndNote are common examples. It answers “how do I cite this?”, while a reading tool answers “what does this paper say, and where?”.',
    more: [
      'Most reference managers capture records from the browser and sync them across devices.',
      'Many researchers pair a reference manager for citing with a separate tool for reading and notes.',
    ],
    inPaperLab: 'PaperLab is a reading tool, not a citation formatter: use it alongside a reference manager.',
    features: ['pdf-library', 'anchored-notes'],
    guides: ['compare/zotero/', 'guides/organize-research-papers/'],
    related: ['doi', 'systematic-review'],
  },
  {
    slug: 'scoping-review',
    name: 'Scoping review',
    title: 'What is a scoping review? How it differs from a systematic review',
    description: 'A scoping review maps the research on a broad topic to show what exists and where the gaps are, with a systematic search but lighter appraisal.',
    definition:
      'A scoping review maps the existing research on a broad topic: what has been studied, how, and where the gaps are. Like a systematic review it uses a documented, reproducible search, but it asks a wider question and usually doesn’t appraise study quality or pool results. It is often a first step before a systematic review.',
    more: [
      'Scoping reviews are reported with the PRISMA-ScR extension.',
      'They are common in health, education and emerging fields where evidence is scattered.',
    ],
    inPaperLab: 'PaperLab’s free-source search, references in both directions and workspaces support the mapping; screening and PRISMA counts arrive in the next release.',
    features: ['find-papers', 'references', 'citation-graph'],
    guides: ['guides/systematic-literature-review/', 'guides/map-your-literature/'],
    related: ['systematic-review', 'prisma', 'meta-analysis'],
  },
  {
    slug: 'meta-analysis',
    name: 'Meta-analysis',
    title: 'What is a meta-analysis? Combining results across studies',
    description: 'A meta-analysis statistically combines the results of comparable studies into one estimate. When it applies, and the data it needs from each paper.',
    definition:
      'A meta-analysis combines the numerical results of several comparable studies into a single overall estimate, weighting each study by its precision. It is often the quantitative part of a systematic review. It needs each study’s effect size and uncertainty, so careful data extraction, with the page each number came from, is essential.',
    more: [
      'Heterogeneity, how much studies disagree, decides whether pooling is meaningful.',
      'When studies are too different to pool, a narrative synthesis is the honest alternative.',
    ],
    inPaperLab: 'PaperLab captures tables and single numbers with their uncertainty, and every charted value links back to its page.',
    features: ['data-and-charts', 'workspaces'],
    guides: ['guides/extract-data-from-papers/', 'guides/systematic-literature-review/'],
    related: ['systematic-review', 'scoping-review', 'prisma'],
  },
  {
    slug: 'pico',
    name: 'PICO',
    title: 'What is PICO? Framing a research question',
    description: 'PICO frames a focused research question: Population, Intervention, Comparison, Outcome. How to use it to plan a literature search.',
    definition:
      'PICO is a framework for writing a focused research question, especially in health research: Population (who), Intervention (what is done), Comparison (compared with what) and Outcome (what is measured). Each element becomes a block of search terms, and the blocks set the inclusion criteria of a systematic review.',
    more: [
      'Variants add Time or Study design (PICOT, PICOS). Outside health, similar frames such as SPIDER or a plain scope statement do the same job.',
      'A clear PICO makes screening faster, because each record is checked against the same four questions.',
    ],
    inPaperLab: 'Your PICO terms become Find papers searches across free sources, grouped in one workspace for the review.',
    features: ['find-papers', 'workspaces'],
    guides: ['guides/systematic-literature-review/'],
    related: ['systematic-review', 'scoping-review', 'prisma'],
  },
  {
    slug: 'grey-literature',
    name: 'Grey literature',
    title: 'What is grey literature? Reports, theses and preprints',
    description: 'Grey literature is research published outside journals and books: reports, theses, preprints, conference papers. Why reviews should search it.',
    definition:
      'Grey literature is research produced outside commercial journal and book publishing: government and NGO reports, theses and dissertations, conference papers, working papers, preprints and technical reports. Systematic reviews search it to reduce publication bias, since studies with null or negative results are less likely to reach journals.',
    more: [
      'Institutional repositories, preprint servers and CORE are good places to find it.',
      'Its quality varies, so appraise it with the same care as journal articles.',
    ],
    inPaperLab: 'PaperLab searches arXiv and CORE among its free sources, which cover preprints and repository deposits.',
    features: ['find-papers'],
    guides: ['guides/systematic-literature-review/', 'guides/find-a-free-pdf-of-a-paper/'],
    related: ['preprint', 'open-access', 'systematic-review'],
  },
  {
    slug: 'peer-review',
    name: 'Peer review',
    title: 'What is peer review? How papers are checked before publication',
    description: 'Peer review is the evaluation of a paper by independent experts before publication. What it checks, what it misses, and why preprints skip it.',
    definition:
      'Peer review is the evaluation of a research paper by independent experts in the field before a journal or conference publishes it. Reviewers judge the question, methods, analysis and claims, and recommend acceptance, revision or rejection. It filters out many problems but not all: reviewers rarely re-run analyses, and errors still reach print.',
    more: [
      'Single-blind, double-blind and open review differ in who knows whose identity.',
      'Confidentiality rules usually forbid uploading a manuscript under review to online AI tools.',
    ],
    inPaperLab: 'With a local model, a manuscript under review can be read and questioned in PaperLab without leaving your computer.',
    features: ['local-first', 'any-model'],
    guides: ['guides/local-llm-for-research/', 'guides/disclose-ai-use-in-research/'],
    related: ['preprint', 'retraction'],
  },
]
