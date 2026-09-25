# PaperLab website

The public site at https://paperlab.tn: a static [Astro](https://astro.build/) build,
deployed to GitHub Pages by `.github/workflows/pages.yml` on every push to `main` that touches it, and once a day so
the star count and the release version in the install command stay current.

```sh
npm install
npm run dev     # http://localhost:4321/
npm test        # builds, then checks every page's SEO tags, calls to action, structured data and images
```

- Screenshots come from `.github/assets/` (the README's), copied into `public/shots/` by `npm run shots` before each
  build, so updating a README picture updates the site.
- Every outside link lives in `src/lib/site.ts`. The domain is `SITE` there, plus `public/CNAME`,
  and `public/robots.txt`.
- Star, LinkedIn, download and contribute links carry `data-goal` and `data-where`, ready for an analytics script's
  outbound-click events.
- Copy follows the README: when a feature changes, change the README first, then the page that describes it.
