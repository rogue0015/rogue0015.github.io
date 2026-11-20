# Brandon T. Bande — Personal Portfolio

This repository contains the source for [rogue0015.github.io](https://rogue0015.github.io/), Brandon T. Bande's personal portfolio and writing site. It presents his speaking, developer community work, areas of expertise, selected projects, contact links and blog.

## Design

The site is a hand-built static experience with no front-end framework or package manager. The home page uses a full-screen, horizontally navigable set of panels with a dark visual theme, acid-green accents, a grain overlay, a canvas background, section dots and keyboard/arrow navigation. It adapts its panel layout for smaller screens and includes semantic headings, accessible labels and metadata for search and social sharing.

The portfolio's visual language is carried through the blog pages, while the writing pages use a more conventional reading layout. Static HTML keeps the site deployable on GitHub Pages without a server-side runtime.

## Repository structure

```text
.
├── index.html                 # Portfolio, styles, and client-side behavior
├── assets/                    # Portrait, logos, icons, and install assets
├── blogs/
│   ├── index.html              # Blog listing
│   ├── page*.html              # Paginated blog listings
│   ├── *.html                  # Published articles
│   ├── blog.css                # Blog presentation styles
│   └── _post-template.md       # Required template for new article sources
├── data/
│   ├── projects.json           # Portfolio project summaries
│   ├── africa-map.json         # Map outline data
│   ├── africa-map.svg          # Local-file preview fallback for the map
│   ├── content.sample.json     # Example shape for local content overrides
│   └── speaker.sample.json     # Example shape for a local speaker snapshot
├── scripts/
│   ├── build_blog.py           # Builds blog pages, pagination, and sitemap
│   └── update_index.py         # Applies local content overrides to homepage HTML
├── sitemap.xml                # Search crawler URL list
├── robots.txt                 # Crawler guidance
└── site.webmanifest           # Progressive web app metadata
```

The `/tools/` destination is linked from the portfolio and listed in the sitemap. Its apps are published from the separate tools project, rather than stored in this repository.

## Content and data flow

- `index.html` contains the portfolio's initial, crawlable copy and the page's CSS and JavaScript. The impact map uses `data/africa-map.json` when served over HTTP and `data/africa-map.svg` as a local-file preview fallback, since browsers block JSON fetches from `file://` pages.
- The page can optionally load `data/content.json` and `data/speaker.json` as same-origin overrides/snapshots, then refresh speaker information from Sessionize. These local JSON files are intentionally not committed; the matching `*.sample.json` files document their expected shapes.
- The portfolio includes static project cards and can load project data from `data/projects.json`.
- Published blog articles are committed as generated HTML. Blog authoring Markdown files are local-only and ignored by Git, except for the shared `_post-template.md`.
- `scripts/build_blog.py` regenerates the blog listing pages and sitemap from available article sources and published pages. It also attempts to refresh `/tools/` sitemap entries when online; offline it preserves existing tool entries.
- `scripts/update_index.py` syncs known homepage copy blocks from a local `data/content.json` file into `index.html`.

## Local preview

Open `index.html` directly for a visual preview; the map outline is included through the local SVG fallback. For same-origin JSON fetching, live speaker data, and site routing, serve the repository root with any static HTTP server and visit its local URL. No dependency installation is required for the site itself; the blog builder uses Python's standard library.

To use the content override workflow, copy `data/content.sample.json` to `data/content.json`, edit the copy, and run:

```sh
python scripts/update_index.py
```

To build the blog pages and sitemap from the available sources:

```sh
python scripts/build_blog.py
```

The builder may use network access to refresh tool listing metadata. Existing `/tools/` sitemap entries are retained when that refresh is unavailable.

## Deployment

The repository is structured for static hosting and is published through GitHub Pages at `https://rogue0015.github.io/`. Keep generated blog pages and the sitemap committed so hosting does not require a build service.
