# Quiddity

*on the thoughts that shape our being*

Plain Jekyll. No npm, no theme. GitHub Pages builds it on push.
Live at https://adventuregit.github.io/quiddity/

## Publishing

| What | Folder | Filename |
|---|---|---|
| Essay | `_posts/essays/` | `2026-10-01-on-attention.md` |
| Note | `_posts/notes/` | `2026-10-01-anything.md` |
| Journal | `_posts/journal/` | `2026-10-01-entry.md` |
| Photograph | `_photos/` + image in `assets/photos/` | `2026-10-01-title.md` |

The folder decides section, layout and URL. Front matter:

    ---
    title: "On Attention"
    description: "Optional one-liner under the title"
    tags: [attention, identity]
    ---

Then:

    git add .
    git commit -m "new essay"
    git push

## Photographs

    ---
    title: Window sun
    date: 2026-09-14
    image: /assets/photos/window-sun.jpg
    alt: A small sun drawn on a fogged jeepney window
    caption: Someone drew a sun on the fogged glass. It lasted two stops.
    place: Quezon City
    camera: 35mm
    ---

    Optional longer reflection. It sits beside the photograph on wide screens.

Resize to ~2000px on the long edge before committing. Photos inside a post:

    {% include figure.html src="/assets/photos/rain.jpg" caption="Taft Avenue, after four." meta="Manila · 2026 · 35mm" %}

## Background drawing

Scan a botanical line drawing (dark ink on white), save as `assets/img/botanical.png`, and uncomment `botanical:` in `_config.yml`. It sits faintly in the corner and inverts in dark mode.

## Design

Built on the Classical system (`assets/css/classical.css`: Cormorant Garamond + Lora, gold accent, hairline rules, matted photo plates). Site layer and cream/dark themes live in `assets/css/style.css`.

## Local preview (optional, needs Ruby)

    bundle install
    bundle exec jekyll serve --baseurl /quiddity
