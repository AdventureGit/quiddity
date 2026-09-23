# Quiddity

vent's personal site — essays, notes, a journal, and photographs. Built with
plain Jekyll (no theme, no build tooling) for GitHub Pages.

## Publishing

Everything lives in `_posts/`. One folder, one workflow: add a file, commit,
push. The `category` in the front matter decides where it shows up.

**Essay** (`category: essay`) — shows on the Essays page and the home feed.

```yaml
---
title: "Essay Title"
category: essay
date: 2026-09-23
excerpt: "One-sentence teaser."
---
```

**Note** (`category: note`) — a short fragment. Title is optional.

```yaml
---
category: note
date: 2026-09-23
---
```

**Journal** (`category: journal`) — dated, raw, no title.

```yaml
---
category: journal
date: 2026-09-23
---
```

**Photo** (`category: photo`) — put the image in `assets/photos/` first.

```yaml
---
category: photo
date: 2026-09-23
title: "Photo title"
image: /assets/photos/your-file.jpg
alt: "Short description for screen readers"
caption: "What you want under the photo."
---
```

Filenames still need the `_posts` convention: `YYYY-MM-DD-anything.md`.

## Preview locally (optional)

```bash
bundle install
bundle exec jekyll serve
```

Then open http://localhost:4000.
