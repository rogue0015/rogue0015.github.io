#!/usr/bin/env python3
"""Sync the static copy in index.html from data/content.json.

The page hydrates its copy from data/content.json at runtime, but crawlers
index the static HTML — the SEO invariant is that both say the same thing.
Run this after editing data/content.json:

    python scripts/update_index.py

Only the known copy blocks are rewritten (tags, titles, paragraphs, chips,
links); layout, styles, and scripts are untouched. Missing JSON fields leave
the corresponding HTML alone, same as the runtime hydrator. A block whose
HTML anchor can't be found is reported as a warning — that means the page
structure drifted and this script needs updating.

    --check   report what is out of sync and exit 1 without writing
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "index.html"
CONTENT_PATH = ROOT / "data" / "content.json"
PROJECTS_PATH = ROOT / "data" / "projects.json"


def esc(value):
    return (str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def esc_attr(value):
    return esc(value).replace('"', "&quot;")


def is_external(href):
    return bool(re.match(r"https?:", href or "", re.I))


class IndexPatcher:
    def __init__(self, html):
        self.html = html
        self.changed = []
        self.missing = []

    def replace(self, label, pattern, replacement, panel=None):
        """Replace the first match of pattern (scoped to a panel section if given)."""
        target, offset = self.html, 0
        if panel:
            section = re.search(
                rf'<section class="panel" id="{panel}">.*?</section>', self.html, re.S)
            if not section:
                self.missing.append(f"{label} — panel #{panel} not found")
                return
            target, offset = section.group(0), section.start()
        match = re.search(pattern, target, re.S)
        if not match:
            self.missing.append(label)
            return
        if match.group(0) == replacement:
            return
        start, end = offset + match.start(), offset + match.end()
        self.html = self.html[:start] + replacement + self.html[end:]
        self.changed.append(label)


TAG_PATTERN = r'<div class="tag"><span class="rule"></span>[^<]*</div>'
TITLE_PATTERN = r'<h2 class="display panel-title glitch" data-text="[^"]*">[^<]*</h2>'


def tag_html(text):
    return f'<div class="tag"><span class="rule"></span> {esc(text)}</div>'


def title_html(text):
    return (f'<h2 class="display panel-title glitch" '
            f'data-text="{esc_attr(text)}">{esc(text)}</h2>')


def apply_content(patcher, content):
    brand = content.get("brand", {})
    if brand.get("mark"):
        patcher.replace(
            "brand mark", r'<div class="brandmark">.*?</div>',
            f'<div class="brandmark"><span class="dotlive"></span> {esc(brand["mark"])}</div>')
    if brand.get("coordinates"):
        inner = "<br>".join(esc(line) for line in brand["coordinates"])
        patcher.replace(
            "coordinates", r'<div class="coord mono" id="coord">.*?</div>',
            f'<div class="coord mono" id="coord">{inner}</div>')

    hero = content.get("hero", {})
    if hero.get("tag"):
        patcher.replace("hero tag", TAG_PATTERN, tag_html(hero["tag"]), panel="p0")
    if hero.get("headline"):
        line_parts = []
        for line in hero["headline"]:
            accent = ' class="accent"' if line.get("accent") else ""
            line_parts.append(f'        <span class="line"><span{accent}>'
                              f'{esc(line.get("text", ""))}</span></span>')
        lines = "\n".join(line_parts)
        patcher.replace(
            "hero headline", r'<h1 class="display hero-head">.*?</h1>',
            f'<h1 class="display hero-head">\n{lines}\n      </h1>', panel="p0")
    if hero.get("subtitle"):
        patcher.replace(
            "hero subtitle", r'<p class="hero-sub">.*?</p>',
            f'<p class="hero-sub">{esc(hero["subtitle"])}</p>', panel="p0")
    if hero.get("ctas"):
        anchors = []
        for i, cta in enumerate(hero["ctas"]):
            attrs = ('href="#p4" id="ctaTalks" class="cta-solid glitch-card"' if i == 0
                     else f'href="{esc_attr(cta.get("href", "#"))}" class="cta-ghost glitch-card"')
            if i == 0 and cta.get("href"):
                attrs = (f'href="{esc_attr(cta["href"])}" id="ctaTalks" '
                         f'class="cta-solid glitch-card"')
            anchors.append(f'        <a {attrs}>{esc(cta.get("label", ""))}</a>')
        patcher.replace(
            "hero CTAs", r'<div class="hero-cta">.*?</div>',
            '<div class="hero-cta">\n' + "\n".join(anchors) + '\n      </div>', panel="p0")

    about = content.get("about", {})
    if about.get("tag"):
        patcher.replace("about tag", TAG_PATTERN, tag_html(about["tag"]), panel="p1")
    if about.get("title"):
        patcher.replace("about title", TITLE_PATTERN, title_html(about["title"]), panel="p1")
    if about.get("photoCaption"):
        patcher.replace(
            "photo caption", r'<div class="photo-tag">[^<]*</div>',
            f'<div class="photo-tag">{esc(about["photoCaption"])}</div>', panel="p1")
    if about.get("paragraphs"):
        paras = "\n".join(f'          <p>{esc(p)}</p>' for p in about["paragraphs"])
        patcher.replace(
            "about paragraphs", r'<div class="aboutCopy">.*?</div>',
            f'<div class="aboutCopy">\n{paras}\n        </div>', panel="p1")

    trail = content.get("signalTrail", {})
    if trail.get("tag"):
        patcher.replace("signal trail tag", TAG_PATTERN, tag_html(trail["tag"]), panel="p2")
    if trail.get("title"):
        patcher.replace("signal trail title", TITLE_PATTERN, title_html(trail["title"]), panel="p2")
    if trail.get("bars"):
        rows = "\n".join(
            f'            <div class="bar-item" style="--w:{esc_attr(bar.get("width", "100%"))}">'
            f'<div class="bl"><span>{esc(bar.get("label", ""))}</span>'
            f'<span>{esc(bar.get("value", ""))}</span></div>'
            f'<div class="track"><div class="fill"></div></div></div>'
            for bar in trail["bars"])
        patcher.replace(
            "signal trail bars",
            r'<div class="bars">.*?</div>(?=\s*<button class="expand-btn)',
            f'<div class="bars">\n{rows}\n          </div>', panel="p2")

    expertise = content.get("expertise", {})
    if expertise.get("tag"):
        patcher.replace("expertise tag", TAG_PATTERN, tag_html(expertise["tag"]), panel="p3")
    if expertise.get("title"):
        patcher.replace("expertise title", TITLE_PATTERN, title_html(expertise["title"]), panel="p3")
    if expertise.get("skills"):
        chips = "\n".join(
            f'        <span class="chip{" " + esc_attr(s["variant"]) if s.get("variant") else ""}'
            f' glitch-card">{esc(s.get("label", ""))}</span>'
            for s in expertise["skills"])
        patcher.replace(
            "expertise skills", r'<div class="chip-row">.*?</div>',
            f'<div class="chip-row">\n{chips}\n      </div>', panel="p3")
    if expertise.get("affiliationsTag"):
        patcher.replace(
            "affiliations tag",
            r'<div class="tag" style="margin-top:36px;"><span class="rule"></span>[^<]*</div>',
            f'<div class="tag" style="margin-top:36px;"><span class="rule"></span> '
            f'{esc(expertise["affiliationsTag"])}</div>', panel="p3")
    if expertise.get("affiliations"):
        chips = "\n".join(
            f'        <a class="chip{" " + esc_attr(a["variant"]) if a.get("variant") else ""}'
            f' glitch-card" href="{esc_attr(a.get("href", "#"))}" target="_blank" rel="noopener">'
            f'{esc(a.get("label", ""))}</a>'
            for a in expertise["affiliations"])
        patcher.replace(
            "affiliations", r'<div class="chip-row" id="affiliations">.*?</div>',
            f'<div class="chip-row" id="affiliations">\n{chips}\n      </div>', panel="p3")
    if expertise.get("marquee"):
        span = f'<span>{esc(expertise["marquee"])}</span>'
        patcher.replace(
            "marquee", r'<div class="marquee-track">.*?</div>',
            f'<div class="marquee-track">{span}{span}</div>', panel="p3")

    talks = content.get("talks", {})
    if talks.get("tag"):
        patcher.replace("talks tag", TAG_PATTERN, tag_html(talks["tag"]), panel="p4")
    if talks.get("title"):
        patcher.replace("talks title", TITLE_PATTERN, title_html(talks["title"]), panel="p4")

    contact = content.get("contact", {})
    if contact.get("tag"):
        patcher.replace("contact tag", TAG_PATTERN, tag_html(contact["tag"]), panel="p5")
    if contact.get("heading"):
        patcher.replace(
            "contact heading", r'<h2 class="display cta">.*?</h2>',
            f'<h2 class="display cta">{esc(contact["heading"])}</h2>', panel="p5")
    if contact.get("subtitle"):
        patcher.replace(
            "contact subtitle", r'<p class="contact-sub">.*?</p>',
            f'<p class="contact-sub">{esc(contact["subtitle"])}</p>', panel="p5")
    primary = contact.get("primaryCta")
    if primary:
        target = ' target="_blank" rel="noopener"' if is_external(primary.get("href")) else ""
        patcher.replace(
            "contact primary CTA", r'<div class="contact-primary">.*?</div>',
            f'<div class="contact-primary">\n'
            f'        <a href="{esc_attr(primary.get("href", "#"))}"{target}>'
            f'{esc(primary.get("label", ""))}</a>\n      </div>', panel="p5")
    if contact.get("links"):
        anchor_parts = []
        for link in contact["links"]:
            target = ' target="_blank" rel="noopener"' if is_external(link.get("href")) else ""
            anchor_parts.append(f'        <a href="{esc_attr(link.get("href", "#"))}"{target}>'
                                f'{esc(link.get("label", ""))}</a>')
        anchors = "\n".join(anchor_parts)
        patcher.replace(
            "contact links", r'<div class="contact-links">.*?</div>',
            f'<div class="contact-links">\n{anchors}\n      </div>', panel="p5")
    if contact.get("footNote"):
        patcher.replace(
            "contact foot note", r'<div class="foot-note">.*?</div>',
            f'<div class="foot-note">\n        <span>{esc(contact["footNote"])}</span>\n'
            f'      </div>', panel="p5")

    boulevard = content.get("boulevard", {})
    if boulevard.get("tag"):
        patcher.replace("boulevard tag", TAG_PATTERN, tag_html(boulevard["tag"]), panel="p6")
    if boulevard.get("title"):
        patcher.replace("boulevard title", TITLE_PATTERN, title_html(boulevard["title"]), panel="p6")
    if boulevard.get("intro"):
        patcher.replace(
            "boulevard intro",
            r'<p class="contact-sub" style="margin-top:0; max-width:62ch;">.*?</p>',
            f'<p class="contact-sub" style="margin-top:0; max-width:62ch;">'
            f'{esc(boulevard["intro"])}</p>', panel="p6")


def apply_projects(patcher, projects):
    """Bake static, crawlable project cards into #projectTunnel.

    The runtime renderer replaces these with the animated version (random
    hues, infinite loop); this static copy is what crawlers index and what
    stays visible if the projects fetch fails (e.g. file:// preview).
    Hues are derived from the index so output is deterministic.
    """
    cards = []
    for index, project in enumerate(projects):
        side = "left" if index % 2 == 0 else "right"
        hue = (160 + index * 67) % 360
        meta = f'PROJECT {index + 1:02d} · {esc(project.get("year", "—"))}'
        cards.append(
            f'        <article class="project-card glitch-card" data-side="{side}" '
            f'style="--holo:{hue}">\n'
            f'          <i class="holo" aria-hidden="true"></i>\n'
            f'          <i class="holo-tear" aria-hidden="true"></i>\n'
            f'          <div class="proj-meta">{meta}</div>\n'
            f'          <h3 class="display proj-title">'
            f'{esc(project.get("projectName", "Untitled project"))}</h3>\n'
            f'          <div class="proj-label">Abstract</div>\n'
            f'          <p class="proj-copy">{esc(project.get("abstract", ""))}</p>\n'
            f'          <div class="proj-label">Rationale</div>\n'
            f'          <p class="proj-copy">{esc(project.get("rationale", ""))}</p>\n'
            f'        </article>')
    inner = "\n" + "\n".join(cards) + "\n      " if cards else ""
    patcher.replace(
        "project cards",
        r'<div class="project-tunnel" id="projectTunnel">.*?</div>'
        r'(?=\s*</div>\s*</section>)',
        f'<div class="project-tunnel" id="projectTunnel">{inner}</div>', panel="p6")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if index.html is out of sync, without writing")
    args = parser.parse_args()

    content = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    html = INDEX_PATH.read_text(encoding="utf-8")

    patcher = IndexPatcher(html)
    apply_content(patcher, content)
    if PROJECTS_PATH.exists():
        apply_projects(patcher, json.loads(PROJECTS_PATH.read_text(encoding="utf-8")))
    else:
        print(f"WARNING: {PROJECTS_PATH} not found — static project cards not synced",
              file=sys.stderr)

    for label in patcher.missing:
        print(f"WARNING: no HTML anchor for: {label} — structure drifted?", file=sys.stderr)

    if not patcher.changed:
        print("index.html already in sync with data/content.json")
        return 1 if patcher.missing else 0

    if args.check:
        print("index.html is OUT OF SYNC with data/content.json:")
        for label in patcher.changed:
            print(f"  - {label}")
        return 1

    INDEX_PATH.write_text(patcher.html, encoding="utf-8", newline="\n")
    print(f"index.html updated ({len(patcher.changed)} blocks):")
    for label in patcher.changed:
        print(f"  - {label}")
    return 1 if patcher.missing else 0


if __name__ == "__main__":
    sys.exit(main())
