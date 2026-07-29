# Project Eleven — www.project11.online

Static website for Project Eleven, served by GitHub Pages. Originally on
Squarespace; rebuilt in July 2026 as simple hand-editable HTML.

**Building through art** — Project Eleven fosters cultural exchange between
Australian and Indonesian artists.

## How the site works

Every page is a plain HTML file that shares:

- `css/site.css` — the master stylesheet. All styling lives here.
- `js/site.js` — the site's only JavaScript (the mobile hamburger menu).
- `fonts/` — self-hosted Poppins font files.

To edit a page, open its HTML file and change the text. To add a page, copy an
existing one, edit the content between `</header>` and `<footer>`, and add a
link to the `<nav>` list in each page.

## Pages

- `index.html` — homepage (hero, mission and vision). `home.html` redirects here.
- `projects.html` — projects index with year cards.
- `projects-2016.html` … `projects-2025.html` — projects by year.
- `publications.html` — catalogues, with PDFs in `s/`.
- `eleven-gallery.html` — the gallery space in Yogyakarta (photos in `eleven-gallery/`).
- `contact.html` — contact details.

## Assets

- `images/` — all photography and artwork images (paths kept from the
  Squarespace export).
- `videos/` — self-hosted video.
- `s/` — downloadable PDF catalogues.
- `CNAME` — custom-domain config for GitHub Pages; don't delete.
