#!/usr/bin/env python3
"""Build the ROGUE0015 blog.

Converts every blogs/*.md (Markdown + front matter) into a fully SEO-optimized
static HTML page, regenerates blogs/index.html (post list + JSON-LD), and
regenerates sitemap.xml. Standard library only — no installs, no Jekyll.

Usage:  python scripts/build_blog.py
"""

import html
import json
import re
import sys
from datetime import date
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
BLOGS = ROOT / "blogs"
SITE = "https://rogue0015.github.io"
AUTHOR_ID = f"{SITE}/#brandon"
BLOG_ID = f"{SITE}/blogs/#blog"

# ---------------------------------------------------------------- front matter

def parse_front_matter(text, path):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, re.S)
    if not m:
        sys.exit(f"ERROR: {path.name} is missing its front matter block (--- ... ---).")
    meta, body = {}, text[m.end():]
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip('"').strip("'")
    tags = meta.get("tags", "")
    if tags.startswith("[") and tags.endswith("]"):
        tags = tags[1:-1]
    meta["tags"] = [t.strip().strip('"').strip("'") for t in tags.split(",") if t.strip()]
    for req in ("title", "date"):
        if not meta.get(req):
            sys.exit(f"ERROR: {path.name} front matter is missing '{req}'.")
    try:
        meta["date_obj"] = date.fromisoformat(meta["date"])
    except ValueError:
        sys.exit(f"ERROR: {path.name} has an invalid date '{meta['date']}' (need YYYY-MM-DD).")
    return meta, body

# ------------------------------------------------------------------- markdown

CODE_SPAN = re.compile(r"`([^`]+)`")

def _rel(url):
    """Rewrite root-absolute internal URLs relative to blogs/ so pages also work
    when previewed from file:// (where "/" is the drive root, not the site)."""
    if url.startswith(SITE):
        url = url[len(SITE):] or "/"
    if url == "/" or url.startswith("/#"):
        return "../index.html" + url[1:]
    if url == "/blogs/" or url == "/blogs":
        return "index.html"
    if url.startswith("/blogs/"):
        return url[len("/blogs/"):]
    if url.startswith("/"):
        return ".." + url
    return url

def _link(m):
    text, url = m.group(1), m.group(2)
    external = url.startswith("http") and not url.startswith(SITE)
    attrs = ' target="_blank" rel="noopener"' if external else ""
    return f'<a href="{_rel(url)}"{attrs}>{text}</a>'

def inline(text):
    spans = []
    def stash(m):
        spans.append(html.escape(m.group(1), quote=False))
        return f"\x00{len(spans) - 1}\x00"
    text = CODE_SPAN.sub(stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                  lambda m: f'<img src="{_rel(m.group(2))}" alt="{m.group(1)}" loading="lazy">', text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{spans[int(m.group(1))]}</code>", text)

BLOCK_START = re.compile(r"^(#{1,6}\s|>|```|[-*]\s|\d+\.\s)|^(-{3,}|\*{3,})\s*$")

def md_to_html(md):
    lines = md.split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            code = html.escape("\n".join(buf), quote=False)
            out.append(f"<pre><code>{code}</code></pre>")
            continue
        m = re.match(r"(#{1,6})\s+(.*)", line)
        if m:
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(lines[i].lstrip()[1:].lstrip())
                i += 1
            paras = "\n".join(buf).split("\n\n")
            inner = "".join(f"<p>{inline(' '.join(p.split()))}</p>" for p in paras if p.strip())
            out.append(f"<blockquote>{inner}</blockquote>")
            continue
        for marker, tag in ((r"^\s*[-*]\s+", "ul"), (r"^\s*\d+\.\s+", "ol")):
            if re.match(marker, line):
                items = []
                while i < n and lines[i].strip():
                    if re.match(marker, lines[i]):
                        items.append(re.sub(marker, "", lines[i]).strip())
                    elif lines[i].startswith("  ") and items:
                        items[-1] += " " + lines[i].strip()  # wrapped list item
                    else:
                        break
                    i += 1
                lis = "".join(f"<li>{inline(item)}</li>" for item in items)
                out.append(f"<{tag}>{lis}</{tag}>")
                break
        else:
            buf = [line.strip()]
            i += 1
            while i < n and lines[i].strip() and not BLOCK_START.match(lines[i].lstrip()):
                buf.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)

# ------------------------------------------------------------------ templates

HEADER = """<header class="site-head">
  <a class="brand mono" href="../index.html"><span class="dotlive"></span> BRANDON.T.BANDE // ROGUE0015</a>
  <nav class="site-nav mono" aria-label="Site navigation">
    <a href="../index.html">HOME</a>
    <a href="../index.html#p4">TALKS</a>
    <a href="index.html" aria-current="true">THOUGHTS</a>
    <a href="../index.html#p5">CONTACT</a>
  </nav>
</header>"""

FOOTER = """<footer class="site-foot mono">
  <span>BRANDON T. BANDE — GWERU, ZIMBABWE</span>
  <span>
    <a href="../index.html">HOME</a> · <a href="index.html">THOUGHTS</a> · <a href="../index.html#p4">TALKS</a> ·
    <a href="https://twitter.com/Rogue0015" target="_blank" rel="noopener">X</a> ·
    <a href="https://www.linkedin.com/in/brandoebande" target="_blank" rel="noopener">LINKEDIN</a> ·
    <a href="https://sessionize.com/brandon-bande/" target="_blank" rel="noopener">SESSIONIZE</a>
  </span>
</footer>"""

POST_TEMPLATE = Template("""<!DOCTYPE html>
<!-- GENERATED FILE — do not edit. Source: blogs/$slug.md. Rebuild: python scripts/build_blog.py -->
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>$title_esc | Brandon T. Bande</title>
<meta name="title" content="$title_attr">
<meta name="description" content="$desc_attr">
<meta name="author" content="Brandon T. Bande">
<meta name="keywords" content="$keywords_attr">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#08060B">
<meta name="color-scheme" content="dark">
<link rel="canonical" href="$url">
<meta property="og:type" content="article">
<meta property="og:title" content="$title_attr">
<meta property="og:description" content="$desc_attr">
<meta property="og:url" content="$url">
<meta property="og:site_name" content="ROGUE0015">
<meta property="og:locale" content="en_ZW">
<meta property="article:published_time" content="$date_iso">
<meta property="article:author" content="Brandon T. Bande">
$article_tags<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@Rogue0015">
<meta name="twitter:creator" content="@Rogue0015">
<meta name="twitter:title" content="$title_attr">
<meta name="twitter:description" content="$desc_attr">
<link rel="stylesheet" href="blog.css">
<script type="application/ld+json">
$jsonld
</script>
</head>
<body>

$header

<main>
  <article class="post" itemscope itemtype="https://schema.org/BlogPosting">
    <header class="post-head">
      <p class="crumbs mono"><a href="../index.html">HOME</a> / <a href="index.html">THOUGHTS</a></p>
      <h1 itemprop="headline">$title_esc</h1>
      <p class="post-meta mono">
        <time datetime="$date_iso" itemprop="datePublished">$date_disp</time>
        · $minutes MIN READ
        · <span itemprop="author">BRANDON T. BANDE</span>
      </p>
$tag_chips    </header>

    <div class="post-body" itemprop="articleBody">
$content
    </div>
  </article>

$pager
  <aside class="post-cta">
    <p class="mono">// KEEP THE SIGNAL GOING</p>
    <div class="cta-row">
      <a class="btn solid" href="index.html">→ ALL THOUGHTS</a>
      <a class="btn ghost" href="../index.html#p4">→ VIEW MY TALKS</a>
      <a class="btn ghost" href="https://www.linkedin.com/in/brandoebande" target="_blank" rel="noopener">→ CONNECT ON LINKEDIN</a>
    </div>
  </aside>
</main>

$footer

</body>
</html>
""")

INDEX_TEMPLATE = Template("""<!DOCTYPE html>
<!-- GENERATED FILE — do not edit. Rebuild: python scripts/build_blog.py -->
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Thoughts — Blog | Brandon T. Bande</title>
<meta name="title" content="Thoughts — Blog by Brandon T. Bande (ROGUE0015)">
<meta name="description" content="Thoughts on AI, tech community building, and strategy from Brandon T. Bande — Tech Community Lead and speaker in Gweru, Zimbabwe.">
<meta name="author" content="Brandon T. Bande">
<meta name="keywords" content="Brandon T. Bande blog, ROGUE0015, AI Zimbabwe, tech community Africa, generative AI, developer community, thoughts">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#08060B">
<meta name="color-scheme" content="dark">
<link rel="canonical" href="$site/blogs/">
<meta property="og:type" content="website">
<meta property="og:title" content="Thoughts — Blog by Brandon T. Bande (ROGUE0015)">
<meta property="og:description" content="Thoughts on AI, tech community building, and strategy from Brandon T. Bande — Tech Community Lead and speaker in Gweru, Zimbabwe.">
<meta property="og:url" content="$site/blogs/">
<meta property="og:site_name" content="ROGUE0015">
<meta property="og:locale" content="en_ZW">
<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@Rogue0015">
<meta name="twitter:title" content="Thoughts — Blog by Brandon T. Bande (ROGUE0015)">
<meta name="twitter:description" content="Thoughts on AI, tech community building, and strategy from Brandon T. Bande.">
<link rel="stylesheet" href="blog.css">
<script type="application/ld+json">
$jsonld
</script>
</head>
<body>

$header

<main>
  <div class="index-tag mono"><span class="rule"></span> 06 / FIELD NOTES</div>
  <h1>Thoughts.</h1>
  <p class="index-intro">Signals from the ground — notes on AI, community building, and
    strategy from <a href="../index.html">Brandon T. Bande</a>, written between
    <a href="../index.html#p4">talks and workshops</a> across Southern Africa.</p>

  <ul class="post-list">
$cards  </ul>
</main>

$footer

</body>
</html>
""")

# -------------------------------------------------------------------- helpers

def attr(s):
    return html.escape(s, quote=True)

def esc(s):
    return html.escape(s, quote=False)

def plain_words(html_text):
    return re.findall(r"\w+", re.sub(r"<[^>]+>", " ", html_text))

def first_paragraph(html_text):
    m = re.search(r"<p>(.*?)</p>", html_text, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)) if m else ""

def truncate(s, limit=158):
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"

# ---------------------------------------------------------------------- build

def check_post(path, slug, meta):
    """Enforce the blogs/_post-template.md rules. Hard-fail on structure,
    warn on SEO length targets."""
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
        sys.exit(f"ERROR: {path.name}: slug must be lowercase-with-hyphens "
                 "(no dates, underscores, or uppercase). Copy blogs/_post-template.md.")
    if not meta.get("description"):
        sys.exit(f"ERROR: {path.name}: front matter needs a 'description' "
                 "(140-160 chars). Copy blogs/_post-template.md.")
    if not meta["tags"]:
        sys.exit(f"ERROR: {path.name}: front matter needs 'tags: [..]'. "
                 "Copy blogs/_post-template.md.")
    if "Primary Keyword Up Front" in meta["title"] or "reason to click" in meta.get("description", ""):
        sys.exit(f"ERROR: {path.name}: still contains template placeholder text.")
    if not 20 <= len(meta["title"]) <= 60:
        print(f"  WARN   {path.name}: title is {len(meta['title'])} chars (target 50-60).")
    if not 140 <= len(meta["description"]) <= 160:
        print(f"  WARN   {path.name}: description is {len(meta['description'])} chars (target 140-160).")

def load_posts():
    posts = []
    for path in sorted(BLOGS.glob("*.md")):
        if path.name.startswith("_"):  # _post-template.md and friends — never build
            continue
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)
        slug = path.stem
        check_post(path, slug, meta)
        content = md_to_html(body)
        desc = meta.get("description") or truncate(first_paragraph(content))
        posts.append({
            "slug": slug,
            "title": meta["title"],
            "description": desc,
            "date": meta["date_obj"],
            "modified": meta.get("last_modified_at", meta["date"]),
            "tags": meta["tags"],
            "content": content,
            "url": f"{SITE}/blogs/{slug}.html",
            "href": f"{slug}.html",
            "words": len(plain_words(content)),
        })
    posts.sort(key=lambda p: (p["date"], p["slug"]))  # oldest → newest
    return posts

def build_post(post, older, newer):
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BlogPosting",
                "@id": f"{post['url']}#post",
                "headline": post["title"],
                "description": post["description"],
                "url": post["url"],
                "datePublished": post["date"].isoformat(),
                "dateModified": post["modified"],
                "inLanguage": "en",
                "keywords": ", ".join(post["tags"]),
                "wordCount": post["words"],
                "isPartOf": {"@id": BLOG_ID},
                "mainEntityOfPage": {"@type": "WebPage", "@id": post["url"]},
                "author": {"@id": AUTHOR_ID},
                "publisher": {"@id": AUTHOR_ID},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": "Thoughts", "item": f"{SITE}/blogs/"},
                    {"@type": "ListItem", "position": 3, "name": post["title"], "item": post["url"]},
                ],
            },
        ],
    }, ensure_ascii=False, indent=2)

    pager_parts = []
    if older:
        pager_parts.append(
            f'    <a class="pager-link" href="{older["href"]}" rel="prev">'
            f'<span class="mono">← OLDER</span><strong>{esc(older["title"])}</strong></a>'
        )
    else:
        pager_parts.append('    <span class="pager-spacer"></span>')
    if newer:
        pager_parts.append(
            f'    <a class="pager-link next" href="{newer["href"]}" rel="next">'
            f'<span class="mono">NEWER →</span><strong>{esc(newer["title"])}</strong></a>'
        )
    pager = ""
    if older or newer:
        pager = ('  <nav class="post-pager" aria-label="More posts">\n'
                 + "\n".join(pager_parts) + "\n  </nav>\n")

    tag_chips = ""
    if post["tags"]:
        chips = "".join(f'<li class="mono">{esc(t)}</li>' for t in post["tags"])
        tag_chips = f'      <ul class="tags" aria-label="Tags">{chips}</ul>\n'

    article_tags = "".join(
        f'<meta property="article:tag" content="{attr(t)}">\n' for t in post["tags"]
    )

    return POST_TEMPLATE.substitute(
        slug=post["slug"],
        title_esc=esc(post["title"]),
        title_attr=attr(post["title"]),
        desc_attr=attr(post["description"]),
        keywords_attr=attr(", ".join(post["tags"] + ["Brandon T. Bande", "ROGUE0015", "Zimbabwe"])),
        url=post["url"],
        date_iso=post["date"].isoformat(),
        date_disp=post["date"].strftime("%b %d, %Y"),
        minutes=post["words"] // 180 + 1,
        article_tags=article_tags,
        jsonld=jsonld,
        header=HEADER,
        footer=FOOTER,
        tag_chips=tag_chips,
        content=post["content"],
        pager=pager,
    )

def build_index(posts):
    newest_first = list(reversed(posts))
    cards = ""
    for p in newest_first:
        cards += f"""    <li>
      <a class="post-card" href="{p['href']}">
        <span class="date mono"><time datetime="{p['date'].isoformat()}">{p['date'].strftime('%b %d, %Y').upper()}</time></span>
        <h2>{esc(p['title'])}</h2>
        <p>{esc(truncate(p['description'], 180))}</p>
        <span class="read mono">READ POST →</span>
      </a>
    </li>
"""
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@type": "Blog",
        "@id": BLOG_ID,
        "url": f"{SITE}/blogs/",
        "name": "Thoughts — Brandon T. Bande",
        "description": "Thoughts on AI, tech community building, and strategy from Brandon T. Bande (ROGUE0015).",
        "inLanguage": "en",
        "author": {"@id": AUTHOR_ID},
        "publisher": {"@id": AUTHOR_ID},
        "blogPost": [
            {
                "@type": "BlogPosting",
                "headline": p["title"],
                "url": p["url"],
                "datePublished": p["date"].isoformat(),
                "author": {"@id": AUTHOR_ID},
            }
            for p in newest_first
        ],
    }, ensure_ascii=False, indent=2)
    return INDEX_TEMPLATE.substitute(site=SITE, jsonld=jsonld, header=HEADER, footer=FOOTER, cards=cards)

def build_sitemap(posts):
    today = date.today().isoformat()
    newest = max((p["modified"] for p in posts), default=today)
    urls = [
        (f"{SITE}/", today, "1.0"),
        (f"{SITE}/blogs/", newest, "0.8"),
    ] + [(p["url"], p["modified"], "0.7") for p in reversed(posts)]
    rows = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{m}</lastmod><priority>{pr}</priority></url>"
        for u, m, pr in urls
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{rows}\n</urlset>\n")

def main():
    posts = load_posts()
    if not posts:
        sys.exit("ERROR: no Markdown posts found in blogs/.")
    for i, post in enumerate(posts):
        older = posts[i - 1] if i > 0 else None
        newer = posts[i + 1] if i + 1 < len(posts) else None
        out = BLOGS / f"{post['slug']}.html"
        out.write_text(build_post(post, older, newer), encoding="utf-8")
        print(f"  built  blogs/{post['slug']}.html  ({post['words']} words)")
    (BLOGS / "index.html").write_text(build_index(posts), encoding="utf-8")
    print("  built  blogs/index.html")
    (ROOT / "sitemap.xml").write_text(build_sitemap(posts), encoding="utf-8")
    print("  built  sitemap.xml")
    print(f"OK: {len(posts)} post(s) published.")

if __name__ == "__main__":
    main()
