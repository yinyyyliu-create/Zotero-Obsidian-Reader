"""Build a self-contained bilingual reader and a companion Obsidian note."""

import argparse
import base64
import hashlib
import json
import re
from html import escape
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "reader.html"
IDENTIFIER = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
CATEGORIES = {"thesis", "concept", "evidence", "qualifier", "method"}
ANNOTATIONS = [
    ("function", "段落功能"),
    ("logic", "逻辑角色"),
    ("critique", "技巧与边界"),
    ("implication", "研究启发"),
]
REQUIRED_SUMMARY = {
    "研究背景与核心问题", "作者主要论点", "方法论与关键假设", "主要证据和研究结果",
    "限制及不确定性", "最终结论", "核心主张一句话", "论证最强处", "论证最弱处", "后续研究启示",
}
EXTENSIONS = {".png":"image/png", ".jpg":"image/jpeg", ".jpeg":"image/jpeg", ".webp":"image/webp"}


def require(condition, problem):
    if not condition:
        raise ValueError(problem)


def html(value):
    return escape(str(value))


def required_text(value, name):
    require(isinstance(value, str) and value.strip(), f"Missing text: {name}")
    return value


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def highlight_text(text, spans):
    out = []
    cursor = 0
    for mark in sorted(spans, key=lambda mark: mark["start"]):
        start, end, kind = mark["start"], mark["end"], mark["category"]
        require(type(start) is int and type(end) is int and cursor <= start < end <= len(text),
                "Invalid or overlapping AI highlight")
        require(kind in CATEGORIES and text[start:end] == mark["quote"], "Invalid AI highlight category or quote")
        out.append(html(text[cursor:start]))
        out.append(f'<mark class="{kind}" data-kind="{kind}" data-author="ai">{html(text[start:end])}</mark>')
        cursor = end
    out.append(html(text[cursor:]))
    return "".join(out)


def render_part(part, base):
    if "text" in part:
        text = required_text(part["text"], "English PDF text")
        return f'<span class="selectable">{highlight_text(text, part.get("highlights", []))}</span>'
    image = (base / part["image"]).resolve()
    require(image.is_relative_to(base), f"Image outside working directory: {image}")
    mime = EXTENSIONS.get(image.suffix.lower())
    require(mime and image.is_file(), f"Missing or unsupported image: {image}")
    alt = html(required_text(part["alt"], "image description"))
    payload = image.read_bytes()
    signatures = {
        "image/png":payload.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg":payload.startswith(b"\xff\xd8\xff"),
        "image/webp":payload.startswith(b"RIFF") and payload[8:12] == b"WEBP",
    }
    require(signatures[mime], f"Image data does not match its extension: {image}")
    code = base64.b64encode(payload).decode("ascii")
    width = part.get("width")
    dims = f' width="{width}"' if type(width) is int and width > 0 else ""
    img = f'<img src="data:{mime};base64,{code}" alt="{alt}"{dims} loading="lazy">'
    if part.get("kind") == "equation":
        return f'<span class="equation">{img}</span>'
    return f'<span class="visual-asset">{img}</span>'


def notes_ui(aid):
    return (
        f'<div class="personal"><button class="note-open" type="button" data-note="{aid}">'
        '＋ 个人笔记</button><p class="note-preview" hidden></p></div>'
    )


def render_block(block, base, page_count):
    aid = block["id"]
    pages = block["pages"]
    require(pages and all(type(page) is int and 1 <= page <= page_count for page in pages), f"Invalid PDF anchor: {aid}")
    locator = "、".join(map(str, sorted(set(pages))))
    kind = block.get("kind", "prose")
    require(kind in {"prose","visual","reference","metadata"}, f"Invalid block kind: {aid}")
    zh = html(required_text(block["zh"], f"{aid} Chinese"))
    parts = block["parts"]
    require(parts, f"Missing English source block: {aid}")
    english = "".join(render_part(part, base) for part in parts)
    annotation = block.get("annotation")
    if kind != "reference":
        require(isinstance(annotation, dict), f"Missing AI annotation: {aid}")
        description = "".join(
            f"<div><dt>{label}</dt><dd>{html(required_text(annotation.get(key), aid + ' ' + key))}</dd></div>"
            for key, label in ANNOTATIONS
        )
        ai = f'<div class="ai"><h3>AI 论证批注</h3><dl>{description}</dl></div>'
    else:
        ai = ""
    return (
        f'<article class="reading-row {kind}" id="{aid}"><div class="paper-block">'
        f'<div class="source-line"><a href="#{aid}">{html(aid.upper())}</a><span>PDF {locator} 页</span></div>'
        f'<div class="en" lang="en">{english}</div><div class="zh" lang="zh-Hans">{zh}</div></div>'
        f'<aside class="annotation">{ai}{notes_ui(aid)}</aside></article>'
    )


def render_section(aid, en, zh, level):
    require(level in {2, 3, 4}, f"Invalid heading level: {aid}")
    return (
        f'<header class="section-head level-{level}" id="{aid}">'
        f'<h{level}>{html(en)}<span>{html(zh)}</span></h{level}>'
        f'<button class="bookmark" type="button" data-section="{aid}" aria-label="切换章节书签" '
        'aria-pressed="false">☆</button></header>'
    )


def write_outputs(spec_path, source_pdf, out_dir, stem):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", stem) is not None, "Use a file-safe stem")
    spec = json.loads(spec_path.read_text(encoding="utf-8-sig"))
    metadata = spec["paper"]
    title = required_text(metadata["title"], "title")
    zh_title = required_text(metadata["titleZh"], "titleZh")
    course = metadata.get("course") or "学术论文精读"
    authors = metadata["authors"]
    require(isinstance(authors, list) and authors and all(isinstance(a, str) and a.strip() for a in authors), "Missing authors")
    year = metadata["year"]
    require(year is None or (type(year) is int and 1000 <= year <= 9999), "Invalid publication year")
    doi = metadata.get("doi") or ""
    key = metadata["zoteroKey"]
    attachment = metadata["attachmentKey"]
    for value in (key, attachment):
        require(isinstance(value, str) and re.fullmatch("[A-Z0-9]{8}", value), "Invalid Zotero key")
    journal = metadata.get("journal") or "期刊未记载"
    pages = metadata["pdfPages"]
    require(type(pages) is int and pages > 0, "Invalid PDF page count")
    require(source_pdf.is_file(), "Source PDF is missing")

    used = set()
    nav = []
    content = []
    block_ids = set()
    for entry in spec["entries"]:
        aid = entry["id"]
        require(IDENTIFIER.fullmatch(aid) and aid.startswith(("sec-", "s-")) and aid not in used, f"Invalid or duplicate ID: {aid}")
        used.add(aid)
        if entry["type"] == "section":
            en = required_text(entry["en"], aid + " heading")
            zh = required_text(entry["zh"], aid + " heading translation")
            nav.append((aid, entry.get("nav") or zh))
            content.append(render_section(aid, en, zh, entry["level"]))
        else:
            require(entry["type"] == "block", f"Unknown entry type: {aid}")
            block_ids.add(aid)
            content.append(render_block(entry, spec_path.parent.resolve(), pages))
    require(nav and block_ids, "Reader needs at least one section and a source block")

    overview_sections = []
    overview_md = []
    summary = spec["overview"]
    require(REQUIRED_SUMMARY == {item["label"] for item in summary} and len(summary) == len(REQUIRED_SUMMARY),
            "Missing or duplicate argument map topics")
    for item in summary:
        label = item["label"]
        para = required_text(item["text"], label)
        anchors = item["anchors"]
        require(anchors and all(anchor in block_ids for anchor in anchors), f"Invalid argument map source anchor: {label}")
        links = " ".join(f'<a href="#{aid}">{html(aid.upper())}</a>' for aid in anchors)
        overview_sections.append(f'<section><h3>{html(label)}</h3><p>{html(para)}</p><div class="citations">{links}</div></section>')
        md_links = " · ".join(f"[{aid.upper()}](../HTML/{stem}.html#{aid})" for aid in anchors)
        overview_md.append(f"## {label}\n\n{para}\n\n{md_links}")
    nav.append(("overview", "论证总览"))
    content.extend([render_section("overview", "Argument map", "全文论证结构总览", 2),
                    f'<div class="overview">{"".join(overview_sections)}</div>'])

    gaps = spec.get("gaps", [])
    report = f"来源：Zotero {key} · PDF {attachment} · {pages} 页。"
    listing = "".join(f"<li>{html(gap)}</li>" for gap in gaps)
    content.append(f'<footer><p>{html(report)}</p>{("<ul>"+listing+"</ul>") if listing else ""}</footer>')
    nav_html = "".join(f'<a href="#{aid}">{html(label)}</a>' for aid,label in nav)
    top = (
        f'<header class="masthead"><div class="wrap"><p class="course">{html(course)}</p>'
        f'<h1 lang="en">{html(title)}</h1><p class="subtitle">{html(zh_title)}</p>'
        f'<p class="byline">{html(", ".join(authors))}</p><p class="metadata">'
        f'<span>{html(journal)}</span><span>{html(year or "年份未记载")}</span>'
        f'<span>DOI {html(doi or "未记载")}</span></p></div></header>'
    )
    paper = json.dumps(dict(doi=doi, zoteroKey=key, sourceFingerprint=digest(source_pdf)[:24], title=title), ensure_ascii=True)
    markers = dict(PAGE_TITLE=html(zh_title + " · " + course), MASTHEAD=top, NAV=nav_html, CONTENT="\n".join(content),
                   PAPER=paper.replace("<", r"\u003c"))
    template = TEMPLATE.read_text(encoding="utf-8")
    reader = re.sub(r"@@([A-Z_]+)@@", lambda match: markers[match[1]], template)
    frontmatter = dict(title=title, authors=authors, year=year, doi=doi, zotero_key=key,
                       tags=metadata.get("tags", ["文献精读"]), status=metadata.get("status", "待读"))
    yaml = "\n".join(f"{k}: {json.dumps(v,ensure_ascii=False)}" for k,v in frontmatter.items())
    zotero_link = metadata.get("zoteroLink", f"zotero://select/library/items/{key}")
    require(re.fullmatch(r"zotero://select/(?:library|groups/[0-9]+)/items/[A-Z0-9]{8}", zotero_link) is not None,
            "Invalid Zotero select link")
    note = (
        f"---\n{yaml}\n---\n\n# {zh_title}\n\n"
        f"- {', '.join(authors)}. *{journal}* ({year or '年份未记载'}).\n"
        f"- [离线双语阅读器](../HTML/{stem}.html)\n- [在 Zotero 中打开]({zotero_link})\n\n"
        + "\n\n".join(overview_md)
        + "\n\n## 待思考问题\n\n"
        + "\n".join(f"- {required_text(q,'research question')}" for q in spec["questions"])
        + ("\n\n## 来源限制\n\n" + "\n".join(f"- {gap}" for gap in gaps) if gaps else "") + "\n"
    )

    html_path = out_dir / f"{stem}.html"
    md_path = out_dir / f"{stem}.md"
    require(not html_path.exists() and not md_path.exists(), "Output exists. Choose a new stem or staging directory.")
    out_dir.mkdir(parents=True, exist_ok=True)
    with html_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(reader)
    with md_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(note)
    print(json.dumps({"html":str(html_path.resolve()),"notes":str(md_path.resolve()),"pdfPages":pages,
                      "sourceSections":len(nav)-1,"readingBlocks":len(block_ids)}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--stem", required=True)
    args = parser.parse_args()
    write_outputs(args.manifest, args.pdf, args.out, args.stem)
