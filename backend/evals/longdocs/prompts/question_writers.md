# Question-writer prompts

Each set was written by Claude Sonnet 5.5 running as a separate agent with exactly this prompt. Paths are those of the original run, with the home folder shortened to `~`.

## Write blind benchmark questions

```text
Write a test key for a document search benchmark. You must stay blind to the search system: do not run any search, do not open any database, do not read anything under ~/try/research-note, and do not use PaperLab tools. Your only input is the page files below; they were sampled at random by a script. Read every one (they're about 70k tokens in total), in parts if needed:

~/.cache/paperlab-bench/q/pages_01.txt, pages_02.txt, pages_03.txt, pages_04.txt

Each page starts with a header: `===== doc=<file> joined_page=N source_page=M kind_hint=table|text =====`. These are real FDA approval reviews and EMA assessment reports and labels. All will be joined into a single 10,000-page PDF, and a researcher will ask questions of that one file.

Write exactly 100 questions to ~/.cache/paperlab-bench/q/questions.yaml. Use at most one question per page, except "multi" questions. Skip junk pages (boilerplate, tables of contents, reference lists, page furniture).

Quotas:
- 35 `fact`: a question using natural wording, which may share words with the passage.
- 35 `reworded`: asks for the same kind of fact, but avoids the passage's distinctive words, as a clinician who has never seen the document would ask. Use synonyms and lay or differently-technical terms. Don't simply swap one word.
- 22 `table`: asks for a specific number from a table-like page (kind_hint=table is a guide), naming the row and column concept, so the answer needs the number with its group or unit.
- 8 `multi`: needs two separate facts, each from a different sampled page of the SAME drug if you can find them, otherwise two facts from different parts of one page.

Every question must:
- Stand alone and be answerable only from that passage, naming the drug or product, since the file holds many drugs. Add the document kind (for example "in the FDA statistical review") only if the fact truly depends on it.
- Be a real question someone working on the drug might ask, not a question about layout or page numbers. Never mention pages, sections or "the passage".
- Not be guessable from general knowledge alone.

Key format, one YAML list item per question:

```yaml
- id: L001
  doc: fda_semaglutide_MedR.pdf     # the doc= value exactly
  kind: fact                        # fact|reworded|table|multi
  source_page: 123                  # joined_page value; for multi use the first page
  question: "..."
  needs:                            # every need must be met; a multi question has 2 needs, others have 1
  - - all_of:                       # a need is a list of alternatives; any one suffices
      - "exact words from the page"
```

Rules for the `all_of` strings, which are checked by a program:
- Each string is copied character for character from the page, lower or upper case doesn't matter, whitespace is collapsed. Never paraphrase.
- Keep each string within one line of the page, 8 to 70 characters, and distinctive enough to prove the right passage was found. Take care with odd characters: if a line has unusual symbols, pick words around them.
- A table question needs the number AND its row or group label as two strings in `all_of`, because the number alone appears anywhere.
- Don't use strings that span a line break in the file.

When finished, check the file parses with `python3 -c "import yaml;print(len(yaml.safe_load(open('~/.cache/paperlab-bench/q/questions.yaml'))))"` and report only: the count per kind, any quota you couldn't fill and why. Don't paste the questions into your report.
```

## Write blind questions, set 1

```text
Write a test key for a document search benchmark. You must stay blind to the search system: do not run any search, do not open any database, do not read anything under ~/try/research-note, and do not use PaperLab tools. Your only input is the page files below; they were sampled at random by a script. Read every one (about 70k tokens in total), in parts if needed:

~/.cache/paperlab-bench/q2/1/pages_01.txt, pages_02.txt, pages_03.txt, pages_04.txt

Each page starts with a header: `===== doc=<file> joined_page=N source_page=M kind_hint=table|text =====`. These are real FDA approval reviews and EMA assessment reports and labels. All will be joined into a single 10,000-page PDF, and a researcher will ask questions of that one file.

Write exactly 100 questions to ~/.cache/paperlab-bench/q2/1/questions.yaml. Use at most one question per page, except "multi" questions. Skip junk pages (boilerplate, tables of contents, reference lists, page furniture), and prefer substantive content over addresses or administrative lines.

Quotas:
- 35 `fact`: a question using natural wording, which may share words with the passage.
- 35 `reworded`: asks for the same kind of fact, but avoids the passage's distinctive words, as a clinician who has never seen the document would ask. Use synonyms and lay or differently-technical terms. Don't simply swap one word.
- 22 `table`: asks for a specific number from a table-like page (kind_hint=table is a guide), naming the row and column concept, so the answer needs the number with its group or unit.
- 8 `multi`: needs two separate facts, each from a different sampled page of the SAME drug if you can find them, otherwise two facts from different parts of one page.

Every question must:
- Stand alone and be answerable only from that passage, naming the drug or product, since the file holds many drugs. Add the document kind (for example "in the FDA statistical review") only if the fact truly depends on it.
- Be a real question someone working on the drug might ask, not a question about layout or page numbers. Never mention pages, sections or "the passage".
- Not be guessable from general knowledge alone.

Key format, one YAML list item per question, ids M001 to M100:

```yaml
- id: M001
  doc: fda_semaglutide_MedR.pdf     # the doc= value exactly
  kind: fact                        # fact|reworded|table|multi
  source_page: 123                  # joined_page value; for multi use the first page
  question: "..."
  needs:                            # every need must be met; a multi question has 2 needs, others have 1
  - - all_of:                       # a need is a list of alternatives; any one suffices
      - "exact words from the page"
```

Rules for the `all_of` strings, which are checked by a program:
- Each string is copied character for character from the page, lower or upper case doesn't matter, whitespace is collapsed. Never paraphrase.
- Keep each string within one line of the page, 8 to 70 characters, and distinctive enough to prove the right passage was found. If a line has unusual symbols, pick words around them.
- A table question needs the number AND its row or group label as two strings in `all_of`, because the number alone appears anywhere.
- Don't use strings that span a line break in the file.

When finished, check the file parses with `python3 -c "import yaml;print(len(yaml.safe_load(open('~/.cache/paperlab-bench/q2/1/questions.yaml'))))"` and report only: the count per kind, and any quota you couldn't fill and why. Don't paste the questions into your report.
```

## Write blind questions, set 2

```text
Write a test key for a document search benchmark. You must stay blind to the search system: do not run any search, do not open any database, do not read anything under ~/try/research-note, and do not use PaperLab tools. Your only input is the page files below; they were sampled at random by a script. Read every one (about 70k tokens in total), in parts if needed:

~/.cache/paperlab-bench/q2/2/pages_01.txt, pages_02.txt, pages_03.txt, pages_04.txt

Each page starts with a header: `===== doc=<file> joined_page=N source_page=M kind_hint=table|text =====`. These are real FDA approval reviews and EMA assessment reports and labels. All will be joined into a single 10,000-page PDF, and a researcher will ask questions of that one file.

Write exactly 100 questions to ~/.cache/paperlab-bench/q2/2/questions.yaml. Use at most one question per page, except "multi" questions. Skip junk pages (boilerplate, tables of contents, reference lists, page furniture), and prefer substantive content over addresses or administrative lines.

Quotas:
- 35 `fact`: a question using natural wording, which may share words with the passage.
- 35 `reworded`: asks for the same kind of fact, but avoids the passage's distinctive words, as a clinician who has never seen the document would ask. Use synonyms and lay or differently-technical terms. Don't simply swap one word.
- 22 `table`: asks for a specific number from a table-like page (kind_hint=table is a guide), naming the row and column concept, so the answer needs the number with its group or unit.
- 8 `multi`: needs two separate facts, each from a different sampled page of the SAME drug if you can find them, otherwise two facts from different parts of one page.

Every question must:
- Stand alone and be answerable only from that passage, naming the drug or product, since the file holds many drugs. Add the document kind (for example "in the FDA statistical review") only if the fact truly depends on it.
- Be a real question someone working on the drug might ask, not a question about layout or page numbers. Never mention pages, sections or "the passage".
- Not be guessable from general knowledge alone.

Key format, one YAML list item per question, ids N001 to N100:

```yaml
- id: N001
  doc: fda_semaglutide_MedR.pdf     # the doc= value exactly
  kind: fact                        # fact|reworded|table|multi
  source_page: 123                  # joined_page value; for multi use the first page
  question: "..."
  needs:                            # every need must be met; a multi question has 2 needs, others have 1
  - - all_of:                       # a need is a list of alternatives; any one suffices
      - "exact words from the page"
```

Rules for the `all_of` strings, which are checked by a program:
- Each string is copied character for character from the page, lower or upper case doesn't matter, whitespace is collapsed. Never paraphrase.
- Keep each string within one line of the page, 8 to 70 characters, and distinctive enough to prove the right passage was found. If a line has unusual symbols, pick words around them.
- A table question needs the number AND its row or group label as two strings in `all_of`, because the number alone appears anywhere.
- Don't use strings that span a line break in the file.

When finished, check the file parses with `python3 -c "import yaml;print(len(yaml.safe_load(open('~/.cache/paperlab-bench/q2/2/questions.yaml'))))"` and report only: the count per kind, and any quota you couldn't fill and why. Don't paste the questions into your report.
```

## Write blind SE and creativity questions

```text
Write a test key for a document search benchmark. You must stay blind to the search system: do not run any search, do not open any database, do not read anything under ~/try/research-note, and do not use PaperLab tools. Your only input is the page files below; a script sampled them at random. Read every one, in parts if needed:

~/.cache/paperlab-bench/secr/q/pages_01.txt, pages_02.txt, pages_03.txt, pages_04.txt

Each page starts with a header: `===== doc=<file> title="<paper title>" page=N kind_hint=table|text =====`. These are research papers on software engineering, creativity, music and computational creativity, from one researcher's library of about 340 papers. The researcher will ask questions of the whole library.

Write exactly 100 questions to ~/.cache/paperlab-bench/secr/q/questions.yaml. Use at most one question per page, except "multi" questions. Skip junk pages: front matter, author lists, acknowledgements, reference lists, and page furniture.

Quotas:
- 35 `fact`: natural wording, which may share words with the passage.
- 35 `reworded`: the same kind of fact, but avoiding the passage's distinctive words, the way a researcher who hasn't read the paper would ask. Don't just swap one word.
- 20 `table`: a specific number from a table or figure-like page (kind_hint=table is a guide), naming the row and column concept. If fewer table pages are usable, fill with `fact`, and say so.
- 10 `multi`: two separate facts from different sampled pages of the SAME paper if you can find them; otherwise two facts from different parts of one page.

Every question must:
- Stand alone and be answerable only from that paper. Identify the paper the way a researcher would: by its topic, system name, method or study (for example "in the study of novice live-coders using Sonic Pi"). Don't quote the full title unless nothing else works.
- Be a real research question, not about layout or page numbers. Never mention pages, sections or "the passage".
- Not be guessable from general knowledge alone.

Key format, one YAML list item per question, ids S001 to S100:

```yaml
- id: S001
  doc: 90472193-c885-4457-8185-2f58fc520a82.pdf   # the doc= value exactly
  kind: fact                                      # fact|reworded|table|multi
  source_page: 7                                  # page= value; for multi use the first page
  question: "..."
  needs:                                          # every need must be met; a multi has 2 needs, others 1
  - - all_of:                                     # a need is a list of alternatives; any one suffices
      - "exact words from the page"
```

Rules for the `all_of` strings, which a program checks:
- Copied character for character from the page. Case doesn't matter, and whitespace is collapsed. Never paraphrase.
- Within one line of the page, 8 to 70 characters, and distinctive enough to prove the right passage was found. If a line has odd symbols, pick words around them.
- A table question needs the number AND its row or group label as two strings in `all_of`.
- No string may span a line break.

When finished, check the file parses with `python3 -c "import yaml;print(len(yaml.safe_load(open('~/.cache/paperlab-bench/secr/q/questions.yaml'))))"`. Report only the count per kind, and any quota you couldn't fill and why. Don't paste the questions.
```

