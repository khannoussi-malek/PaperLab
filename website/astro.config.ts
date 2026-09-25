import sitemap from '@astrojs/sitemap'
import { defineConfig } from 'astro/config'
import { BASE, SITE } from './src/lib/site'

export default defineConfig({
  site: SITE,
  base: BASE,
  trailingSlash: 'always',
  integrations: [sitemap()],
})
