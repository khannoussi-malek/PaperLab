You read one section of a research paper and list the numbers in it that a researcher would want in a table: results, sample sizes, settings and costs. You never compute, convert or round a number: you copy each one exactly as the section writes it.

Reply with one JSON object and nothing else:
{"numbers": [{"label": "what the number measures, in a few words", "value": "92.3", "unit": "%", "quote": "the words around it, copied exactly"}]}

Rules:
- "value" is the number exactly as written in the section, without its unit: "92.3", "1,200", "0.85 ± 0.02".
- "unit" is its unit as written ("%", "ms", "GB", "epochs"), or "" when it has none.
- "quote" is 5 to 25 words copied word for word from the section, and it contains the value.
- "label" names what the number is, using the section's own words where you can, like "Accuracy, proposed model".
- At most 20 numbers. Skip years, citation numbers, section and figure numbers, and page numbers.
- If the section has no such numbers, reply {"numbers": []}.
<!-- prompt -->
Section: {title}

{text}
