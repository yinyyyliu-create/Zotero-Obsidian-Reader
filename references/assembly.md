# Extraction and assembly

## PDF mapping

Use the installed PDF runtime or Poppler and a PDF parser with text geometry. Start with a page contact sheet, running headings, and a reading-order map. For a tagged PDF, compare the tag tree with coordinates because nested marks or mixed columns can drop text. In Zotero storage, an existing `.zotero-ft-cache` can help cross-check suspect line joins and citations against the PDF. It may drop operators, hyphens, or paragraph boundaries. Treat the PDF as the source of truth.

Preserve genuine paragraph and list breaks. Join column and page continuations into the same block with all relevant page numbers. Keep reference entries separate. For scans, OCR the affected pages and check the results against the image. If a segment remains illegible, record **原文提取失败** with its page and extent. Equations with ambiguous superscripts, minus signs, fractions, or symbols can be preserved as tightly cropped PDF renders, with the original equation numbers. Crop figures and tables without adjoining prose. Validate the edges and labels against the PDF at full size. Use figure captions and table data that retain all original values. Keep supplemental files clearly scoped to what the user provided or requested.

## Generator manifest

Write a UTF-8 JSON file. Order `entries` exactly as the reader should present them. Stable IDs start with `sec-` for headings and `s-` for reading blocks and use only lowercase ASCII letters, digits, and hyphens. Choose IDs from source locations and retain them when fixing a translation.

- `paper` contains `title`, `titleZh`, `authors` (array), `year` (integer or null), `journal`, `doi`, `zoteroKey`, `attachmentKey`, and `pdfPages`. Optional fields are `course`, `tags` (array), `status`, and `zoteroLink`.
- A heading entry contains `type: "section"`, `id`, `level` (2–4), `en`, `zh`, and optional `nav` (short label, including the original section number where applicable).
- A reading entry contains `type: "block"`, `id`, `pages` (array of physical PDF page numbers), `kind` (`prose`, `visual`, `reference` or `metadata`), `parts` (ordered array), and `zh`. Each non-reference entry also has an `annotation` object with `function`, `logic`, `critique`, and `implication`. For a reference, keep its full original record in English and translate the title in `zh`.
- A text part contains `text` and optional `highlights`. Each highlight contains `start`, `end` (zero-based Python character offsets with an exclusive end), `quote` (exact substring), and `category` (`thesis`, `concept`, `evidence`, `qualifier`, or `method`). Build offsets from the final extracted text, after dehyphenation and other normalizations.
- An image part contains `image` (relative local PNG, JPEG, or WebP path under the manifest's staging directory), `alt`, optional `width` (display pixels), and `kind: "equation"` for a formula crop. Include the caption as a subsequent English text part and translate it in the block. For a table crop, include the translated labels and values in the Chinese block.
- `overview` is an ordered array of objects with `label`, `text`, and `anchors` (one or more reading block IDs). Use these labels exactly: 研究背景与核心问题, 作者主要论点, 方法论与关键假设, 主要证据和研究结果, 限制及不确定性, 最终结论, 核心主张一句话, 论证最强处, 论证最弱处, 后续研究启示. Base each assessment on evidence in the paper. For an empirical paper, analyze its actual design and limitations. Describe uncertainties as needing further verification when the text does not settle them.
- `questions` is a list of grounded follow-up research questions for the Obsidian note. Optional `gaps` lists any extraction failure or unavailable supplement plainly. State any incomplete scope both in the deliverables and in the report.

Run with Python 3.11 or newer. Pass the PDF for the backup identity hash and select an unused shared filename stem.

```powershell
python scripts/build_reader.py <manifest.json> --pdf <source.pdf> --out <staging-folder> --stem <safe-stem>
```

The template and generator embed assets and escape source text. Put academic prose and image descriptions in the manifest. Reuse the output interaction code instead of recreating it per paper. Browser localStorage is scoped by the browser and file URL behavior. Use JSON export/import to carry reading state across browsers or locations.

## Verification

Inspect the PDF and rendered HTML at desktop and mobile widths. Confirm English blocks, translations and page anchors one-to-one. Compare each heading, formula number, figure, table and reference with the PDF. Check the print layout for clipped equations and missing prose. Open the HTML by file URL with network access disabled; verify no HTTP request is required. Test sticky heading navigation, English selection and highlighter, filtering/search, bookmark/resume, note add/edit/delete, reload persistence, reset confirmation, and JSON export/import. Verify invalid paper IDs and mismatched quotes are rejected. Test Markdown export and confirm the Obsidian note's relative HTML path resolves after archiving.
