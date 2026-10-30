#!/usr/bin/env python3
"""Build the ROGUE0015 blog.

Converts every blogs/*.md (Markdown + front matter) into a fully SEO-optimized
static HTML page, regenerates the paginated blog index (blogs/index.html,
blogs/page2.html, ...) and regenerates sitemap.xml. Standard library only —
no installs, no Jekyll.

Post sources are local-only, so already-published posts are read back from
their generated blogs/<slug>.html when no blogs/<slug>.md exists. A .md
always wins over its .html, so to edit an old post, recreate its .md.

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
PER_PAGE = 5

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

ANALYTICS = """<script id="goatcounter-script" data-goatcounter="https://rogue0015.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>
<script>
document.getElementById('goatcounter-script').addEventListener('load', function () {
  var vc = document.getElementById('view-count');
  if (!vc) return;
  fetch('https://rogue0015.goatcounter.com/counter/' + location.pathname + '.json')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) {
      if (!data) return;
      console.log('Page views:', data.count);
      vc.textContent = data.count + ' VIEWS';
    })
    .catch(function () {});
});
</script>"""

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
<meta property="og:image" content="$image_url">
<meta property="og:image:width" content="400">
<meta property="og:image:height" content="400">
<meta property="og:image:alt" content="Brandon T. Bande — AI and developer community lead, Zimbabwe">
<meta property="article:published_time" content="$date_iso">
<meta property="article:author" content="Brandon T. Bande">
$article_tags<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@Rogue0015">
<meta name="twitter:creator" content="@Rogue0015">
<meta name="twitter:title" content="$title_attr">
<meta name="twitter:description" content="$desc_attr">
<meta name="twitter:image" content="$image_url">
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
        · <span id="view-count" class="mono" aria-label="Page views"></span>
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

$analytics

</body>
</html>
""")

INDEX_TEMPLATE = Template("""<!DOCTYPE html>
<!-- GENERATED FILE — do not edit. Rebuild: python scripts/build_blog.py -->
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>$page_title</title>
<meta name="title" content="$page_title">
<meta name="description" content="$page_desc">
<meta name="author" content="Brandon T. Bande">
<meta name="keywords" content="Brandon T. Bande blog, ROGUE0015, AI Zimbabwe, tech community Africa, generative AI, developer community, thoughts">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#08060B">
<meta name="color-scheme" content="dark">
<link rel="canonical" href="$page_url">
$rel_links<meta property="og:type" content="website">
<meta property="og:title" content="$page_title">
<meta property="og:description" content="$page_desc">
<meta property="og:url" content="$page_url">
<meta property="og:site_name" content="ROGUE0015">
<meta property="og:locale" content="en_ZW">
<meta property="og:image" content="$site/assets/brandon-bande.jpg">
<meta property="og:image:width" content="400">
<meta property="og:image:height" content="400">
<meta property="og:image:alt" content="Brandon T. Bande — AI and developer community lead, Zimbabwe">
<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@Rogue0015">
<meta name="twitter:title" content="$page_title">
<meta name="twitter:description" content="$page_desc">
<meta name="twitter:image" content="$site/assets/brandon-bande.jpg">
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

  <div class="tag-filter-row">
    <label class="mono" for="tag-filter">FILTER BY TAG</label>
    <select id="tag-filter" class="mono">
      <option value="">All posts</option>
$tag_options    </select>
  </div>

  <ul class="post-list">
$cards  </ul>
$index_pager</main>

$footer

$analytics
<script>
(function () {
  var sel = document.getElementById('tag-filter');
  var items = document.querySelectorAll('.post-list > li');
  sel.addEventListener('change', function () {
    var tag = sel.value;
    items.forEach(function (li) {
      var tags = (li.getAttribute('data-tags') || '').split(' ');
      li.style.display = (!tag || tags.indexOf(tag) !== -1) ? '' : 'none';
    });
  });
})();
</script>

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

def make_post(slug, title, description, date_obj, modified, tags, content):
    return {
        "slug": slug,
        "title": title,
        "description": description,
        "date": date_obj,
        "modified": modified,
        "tags": tags,
        "content": content,
        "url": f"{SITE}/blogs/{slug}.html",
        "href": f"{slug}.html",
        "words": len(plain_words(content)),
    }

INDEX_PAGE = re.compile(r"index|page\d+")

def _grab(pattern, text, path, what):
    m = re.search(pattern, text, re.S)
    if not m:
        sys.exit(f"ERROR: {path.name}: can't find the {what} in this published post. "
                 "Recreate its .md source so the build doesn't drop it.")
    return m.group(1)

def load_published_post(path):
    """Read an already-published post back from its generated HTML, so it stays
    on the blog without its (local-only) .md source."""
    text = path.read_text(encoding="utf-8")
    title = _grab(r'<h1 itemprop="headline">(.*?)</h1>', text, path, "headline")
    desc = _grab(r'<meta name="description" content="([^"]*)">', text, path, "description")
    published = _grab(r'<time datetime="([\d-]+)" itemprop="datePublished">', text, path, "publish date")
    modified = _grab(r'"dateModified": "([^"]+)"', text, path, "dateModified")
    content = _grab(r'<div class="post-body" itemprop="articleBody">\n(.*?)\n    </div>\n  </article>',
                    text, path, "post body")
    tags = re.findall(r'<meta property="article:tag" content="([^"]*)">', text)
    return make_post(path.stem, html.unescape(title), html.unescape(desc),
                     date.fromisoformat(published), modified,
                     [html.unescape(t) for t in tags], content)

def load_posts():
    posts, sources = {}, {}
    for path in sorted(BLOGS.glob("*.md")):
        if path.name.startswith("_"):  # _post-template.md and friends — never build
            continue
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"), path)
        slug = path.stem
        check_post(path, slug, meta)
        content = md_to_html(body)
        desc = meta.get("description") or truncate(first_paragraph(content))
        posts[slug] = make_post(slug, meta["title"], desc, meta["date_obj"],
                                meta.get("last_modified_at", meta["date"]), meta["tags"], content)
        sources[slug] = "md"
    for path in sorted(BLOGS.glob("*.html")):
        if INDEX_PAGE.fullmatch(path.stem) or path.stem in posts:
            continue  # index pages are rebuilt below; a .md source always wins
        posts[path.stem] = load_published_post(path)
        sources[path.stem] = "html"
    ordered = sorted(posts.values(), key=lambda p: (p["date"], p["slug"]))  # oldest → newest
    return ordered, sources

def build_post(post, older, newer):
    jsonld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BlogPosting",
                "@id": f"{post['url']}#post",
                "headline": post["title"],
                "description": post["description"],
                "image": f"{SITE}/assets/brandon-bande.jpg",
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
        image_url=f"{SITE}/assets/brandon-bande.jpg",
        date_iso=post["date"].isoformat(),
        date_disp=post["date"].strftime("%b %d, %Y"),
        minutes=post["words"] // 180 + 1,
        article_tags=article_tags,
        jsonld=jsonld,
        header=HEADER,
        footer=FOOTER,
        analytics=ANALYTICS,
        tag_chips=tag_chips,
        content=post["content"],
        pager=pager,
    )

def page_href(n):
    return "index.html" if n == 1 else f"page{n}.html"

def page_url(n):
    return f"{SITE}/blogs/" if n == 1 else f"{SITE}/blogs/page{n}.html"

def build_index_pager(n, total):
    if total == 1:
        return ""
    parts = []
    if n > 1:
        parts.append(f'    <a class="pager-btn" href="{page_href(n - 1)}" rel="prev">'
                     '<span class="mono">← NEWER</span></a>')
    else:
        parts.append('    <span class="pager-spacer"></span>')
    nums = "".join(
        f'<span class="pager-page" aria-current="page">{i}</span>' if i == n
        else f'<a class="pager-page" href="{page_href(i)}">{i}</a>'
        for i in range(1, total + 1)
    )
    parts.append(f'    <span class="pager-pages mono">{nums}</span>')
    if n < total:
        parts.append(f'    <a class="pager-btn next" href="{page_href(n + 1)}" rel="next">'
                     '<span class="mono">OLDER →</span></a>')
    else:
        parts.append('    <span class="pager-spacer"></span>')
    return ('\n  <nav class="index-pager" aria-label="Blog pagination">\n'
            + "\n".join(parts) + "\n  </nav>\n")

def build_index_pages(posts):
    """Return {filename: html} for blogs/index.html, page2.html, ..."""
    newest_first = list(reversed(posts))
    chunks = [newest_first[i:i + PER_PAGE] for i in range(0, len(newest_first), PER_PAGE)]
    return {
        page_href(n): build_index(chunk, newest_first, n, len(chunks))
        for n, chunk in enumerate(chunks, start=1)
    }

def build_index(page_posts, newest_first, n, total):
    cards = ""
    for p in page_posts:
        cards += f"""    <li data-tags="{attr(' '.join(p['tags']))}">
      <a class="post-card" href="{p['href']}">
        <span class="date mono"><time datetime="{p['date'].isoformat()}">{p['date'].strftime('%b %d, %Y').upper()}</time></span>
        <h2>{esc(p['title'])}</h2>
        <p>{esc(truncate(p['description'], 180))}</p>
        <span class="read mono">READ POST →</span>
      </a>
    </li>
"""
    unique_tags = sorted({t for p in newest_first for t in p["tags"]})
    tag_options = "".join(
        f'      <option value="{attr(t)}">{esc(t)}</option>\n' for t in unique_tags
    )
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
    if n == 1:
        page_title = "Thoughts — Blog | Brandon T. Bande"
        page_desc = ("Thoughts on AI, tech community building, and strategy from Brandon T. Bande "
                     "— Tech Community Lead and speaker in Gweru, Zimbabwe.")
    else:
        page_title = f"Thoughts — Page {n} | Brandon T. Bande"
        page_desc = (f"Page {n} of Thoughts — AI, tech community building, and strategy notes "
                     "from Brandon T. Bande (ROGUE0015).")
    rel_links = ""
    if n > 1:
        rel_links += f'<link rel="prev" href="{page_url(n - 1)}">\n'
    if n < total:
        rel_links += f'<link rel="next" href="{page_url(n + 1)}">\n'
    return INDEX_TEMPLATE.substitute(
        site=SITE, jsonld=jsonld, header=HEADER, footer=FOOTER, analytics=ANALYTICS,
        cards=cards, tag_options=tag_options, page_title=page_title, page_desc=page_desc,
        page_url=page_url(n), rel_links=rel_links, index_pager=build_index_pager(n, total),
    )

def build_sitemap(posts, page_count):
    today = date.today().isoformat()
    newest = max((p["modified"] for p in posts), default=today)
    urls = [
        (f"{SITE}/", today, "1.0"),
        (f"{SITE}/blogs/", newest, "0.8"),
    ] + [(page_url(n), newest, "0.5") for n in range(2, page_count + 1)] \
      + [(p["url"], p["modified"], "0.7") for p in reversed(posts)]
    rows = "\n".join(
        f"  <url><loc>{u}</loc><lastmod>{m}</lastmod><priority>{pr}</priority></url>"
        for u, m, pr in urls
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{rows}\n</urlset>\n")

def main():
    posts, sources = load_posts()
    if not posts:
        sys.exit("ERROR: no posts found in blogs/ (no .md sources or published .html).")
    for i, post in enumerate(posts):
        older = posts[i - 1] if i > 0 else None
        newer = posts[i + 1] if i + 1 < len(posts) else None
        out = BLOGS / f"{post['slug']}.html"
        out.write_text(build_post(post, older, newer), encoding="utf-8")
        print(f"  built  blogs/{post['slug']}.html  ({post['words']} words, from .{sources[post['slug']]})")
    pages = build_index_pages(posts)
    for name, page in pages.items():
        (BLOGS / name).write_text(page, encoding="utf-8")
        print(f"  built  blogs/{name}")
    for stale in BLOGS.glob("page*.html"):  # the blog shrank — drop pages past the end
        if INDEX_PAGE.fullmatch(stale.stem) and stale.name not in pages:
            stale.unlink()
            print(f"  removed blogs/{stale.name}")
    (ROOT / "sitemap.xml").write_text(build_sitemap(posts, len(pages)), encoding="utf-8")
    print("  built  sitemap.xml")
    new = sum(1 for s in sources.values() if s == "md")
    print(f"OK: {len(posts)} post(s) published ({new} from .md, {len(posts) - new} kept from .html).")

if __name__ == "__main__":
    main()
