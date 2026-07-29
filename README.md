# Project Eleven — www.project11.online

Static archive of the Project Eleven website, migrated from Squarespace to GitHub Pages in July 2026.

**Building through art** — Project Eleven fosters cultural exchange between Australian and Indonesian artists.

## Structure

- `index.html` / `home.html` — homepage
- `about-us.html`, `contact.html`, `publications.html` — main pages
- `projects-2016.html` … `projects-2025.html` — projects by year
- `s/` — downloadable PDF catalogues
- `videos/` — self-hosted video (formerly Squarespace-hosted)
- `images.squarespace-cdn.com/`, `static1.squarespace.com/`, `assets.squarespace.com/`, `definitions.sqspcdn.com/`, `file.squarespace-cdn.com/` — all site assets, downloaded from the Squarespace CDN so the site is fully self-contained

## Hosting

Served by GitHub Pages from the `main` branch root. The custom domain is set via the `CNAME` file.

## Known limitations

- The newsletter signup (homepage) and contact form previously posted to Squarespace's backend and no longer submit. To restore them, wire the forms to a service such as Formspree, Basin, or Netlify Forms.
- The shopping cart page (`cart.html`) is a leftover from Squarespace commerce and is not linked from navigation.
