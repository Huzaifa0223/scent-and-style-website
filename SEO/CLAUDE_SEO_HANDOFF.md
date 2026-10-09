# ScentAndStyle.pk SEO Handoff

## Purpose

Continue SEO work for the live ScentAndStyle.pk website. This note is for Claude Code and the person responsible for SEO implementation.

This is also a beginner guide. SEO is not one magic setting and it is not an instant traffic
switch. It is the repeated process of helping search engines discover pages, understand them,
trust them, and show them to people who are searching for those products.

The safe learning rule is: observe first, change one thing at a time, record what changed, and
wait long enough to measure it. Do not make many unrecorded changes and then guess which one helped.

## Live Site

- Domain: `https://scentandstyle.pk/`
- App VPS directory: `/root/scent-and-style-website`
- Service: `scentandstyle.service`
- Front door: Caddy
- Database: PostgreSQL database `ecommerce`
- Separate site that must not be touched: `mps.scentandstyle.pk`

## Important Safety Rules

- Work only on `scentandstyle.pk` and `/root/scent-and-style-website`.
- Do not access, inspect, modify, restart, or migrate anything for `mps.scentandstyle.pk`.
- Do not query or export customer/order data unless explicitly required and approved.
- Never expose passwords, `.env` values, database credentials, or customer information in chat.
- Back up before any VPS configuration or database change.
- Do not run destructive commands such as `git reset --hard`, database drops, or history rewrites.
- Do not push to GitHub without explicit owner approval.

## Current GSC Verification

The Google Search Console HTML verification file is:

`SEO/google0dd277f225f2406a.html`

It is live at:

`https://scentandstyle.pk/google0dd277f225f2406a.html`

Expected response body:

`google-site-verification: google0dd277f225f2406a.html`

The previous token `googlea0804ef5f37cef71.html` was removed from the VPS after the new URL returned
the exact expected body; a follow-up check confirmed the previous URL returns 404. The file is served
by an exact-path Caddy handler. The original Caddy configuration was backed up under:

`/root/scentandstyle-deploy-backups/20261003-google-gsc-*/Caddyfile.before`

Do not add a DNS verification record unless Google Search Console specifically requires DNS verification or the HTML method fails. The HTML method is already working.

## Beginner Definitions

### Google Search Console (GSC)

GSC is Google's report for this website. It shows whether Google can discover, crawl, and index the
site, and which searches and pages produce impressions and clicks. GSC does not automatically fix
SEO issues; it reports them.

### Crawl, index, and rank

- **Crawl:** Googlebot visits a URL and reads the page.
- **Index:** Google decides whether the page is eligible to appear in search results.
- **Rank:** Google chooses the page's position for a particular search query.

A page can be crawlable but not indexed, indexed but have no impressions yet, or receive impressions
but no clicks. These are different situations and must not be treated as the same error.

### Sitemap

`/sitemap.xml` is a list of important public URLs. It helps discovery, but submitting a sitemap does
not guarantee indexing or ranking. Only public, useful, canonical URLs belong in it.

### Robots.txt

`/robots.txt` tells crawlers which areas they should not request. It is not a security system and
must never be used to hide private data. Login and portal access are protected by the application,
not by robots.txt.

### Canonical URL

The canonical URL tells Google which URL should represent a page when similar URLs exist. For example,
filtered listing URLs may have query strings, but the clean product URL should normally be canonical.

### DNS verification versus HTML verification

These are two different ways to prove ownership in GSC:

- **HTML verification:** Google checks a specific file at the website root. This is already working
   for ScentAndStyle.pk.
- **DNS verification:** Google checks a TXT record at the domain DNS provider. This is useful for a
   domain property, but it is not necessary when the working HTML verification is sufficient.

Never add a DNS record from memory. Copy the exact record type, host/name, and value shown by Google.

### Cloudflare versus a normal DNS provider

Cloudflare is both a DNS provider and a reverse proxy/CDN. In Cloudflare, DNS changes are made in
**Websites -> scentandstyle.pk -> DNS -> Records**. A normal provider has a similar DNS Records or
Zone Editor screen, but the labels may differ.

For a Google TXT record, the common values are:

- Type: `TXT`
- Name/Host: `@` or the root-domain field required by that provider
- Content/Value: the exact value copied from Google
- TTL: `Auto` or the provider default

For a CNAME record, use the exact target Google gives. Do not convert a CNAME into a TXT record or
add quotes unless the provider's UI specifically requires them. Cloudflare proxying is normally
irrelevant for TXT records; leave the DNS record in the provider's normal DNS-only mode when the UI
offers a proxy choice.

## What the SEO Person Should Send Back

After each step, send a short report with:

```text
Date:
Property:
URL or setting checked:
Action taken:
Result:
Screenshot or error:
Next action:
```

For URL Inspection, use:

```text
URL:
Google can fetch: yes/no
Indexing allowed: yes/no
Indexed: yes/no/unknown
User-declared canonical:
Google-selected canonical:
Mobile result:
Reason for any exclusion:
```

## Beginner Order of Work

Do these in order. Do not skip to backlinks, ads, or keyword claims before the technical foundation
is confirmed.

1. Verify ownership in GSC.
2. Submit and confirm `/sitemap.xml`.
3. Inspect a sample of homepage, category, brand, and product URLs.
4. Fix crawl, canonical, redirect, broken-link, or accidental noindex problems first.
5. Improve product content using real merchant-provided information.
6. Check mobile layout and page speed.
7. Start measuring impressions, clicks, queries, and indexed pages weekly.
8. Only then plan keyword/content expansion or link-building work.

## How to Read the Main GSC Metrics

- **Impressions:** how often a result from the site was shown.
- **Clicks:** how often a searcher opened the result.
- **CTR:** clicks divided by impressions. A tiny sample can produce misleading percentages.
- **Average position:** the average position when the site appeared; it is not a permanent ranking.
- **Queries:** the searches that produced visibility. Some low-volume queries may be omitted for privacy.
- **Pages:** which URLs receive search visibility.

The current workbook has only two impressions and two clicks in one day. Do not call this success or
failure yet. Wait for at least two to four weeks of data, preferably with a weekly export.

## What Not To Do

- Do not keyword-stuff product names or descriptions.
- Do not copy another store's text, reviews, or product claims.
- Do not create fake reviews, fake ratings, or fake backlinks.
- Do not add hidden text or doorway pages for search engines.
- Do not submit every query-string filter URL as a separate sitemap URL.
- Do not change canonical tags, robots rules, DNS, or Caddy without recording the reason and checking
   the live result afterward.
- Do not request indexing repeatedly; Google controls crawl timing.

## Weekly SEO Routine

Once per week, export or record:

1. Total clicks and impressions.
2. CTR and average position.
3. Top five queries.
4. Top five landing pages.
5. Indexed pages and excluded-page reasons.
6. Any mobile usability, Core Web Vitals, sitemap, or security warnings.
7. One or two product pages checked manually on mobile.

Keep the reports dated. A trend across several weeks is useful; a single day is usually not.

## Current SEO Endpoints

- `https://scentandstyle.pk/robots.txt` returns a robots file with the sitemap URL.
- `https://scentandstyle.pk/sitemap.xml` returns the Django sitemap.
- `https://scentandstyle.pk/brands/` is live and lists published brands.
- Product pages include canonical tags, Open Graph/Twitter tags, breadcrumbs, and Product JSON-LD.
- The homepage, brand directory, product listing, and PDPs are server-rendered.

## GSC Workbook Findings

Workbook:

`SEO/https___scentandstyle.pk_-Performance-on-Search-2026-09-30.xlsx`

The workbook is a Google Search Console export covering the last 24 hours:

- Clicks: 2
- Impressions: 2
- CTR: 100%
- Average position: 1.5
- Country: Pakistan
- Device: Desktop
- Top page: `https://scentandstyle.pk/`
- Search queries: none exposed in the export

This is too little data for SEO conclusions. Treat it as an initial indexing signal, not a performance baseline.

## SEO Person: Recommended Step-by-Step Workflow

### Step 1: Confirm ownership and property

1. Open Google Search Console.
2. Confirm the property is the exact domain property for `scentandstyle.pk`, not only a URL-prefix property for another protocol or hostname.
3. Click Verify using the existing HTML method.
4. Confirm that this URL loads before verification:
   `https://scentandstyle.pk/googlea0804ef5f37cef71.html`
5. Do not request DNS changes if HTML verification succeeds.

### Step 2: Submit the sitemap

1. In Search Console, open **Indexing -> Sitemaps**.
2. Submit:
   `https://scentandstyle.pk/sitemap.xml`
3. Confirm the sitemap status becomes **Success**.
4. Record the discovered URL count and any parse errors.
5. Do not submit random sitemap URLs or `/robots.txt` as a sitemap.

### Step 3: Inspect indexing and coverage

1. Use URL Inspection for:
   - `https://scentandstyle.pk/`
   - one category URL
   - one brand URL such as `https://scentandstyle.pk/brands/`
   - one product URL such as `https://scentandstyle.pk/product/zumar/`
2. For each URL record:
   - whether Google can fetch it
   - whether indexing is allowed
   - canonical selected by Google
   - last crawl status
   - mobile usability status
3. Request indexing only for important URLs after verifying the page is final.
4. Do not repeatedly request indexing for the entire catalog.

### Step 4: Validate technical SEO

Check the following before changing code:

- One canonical URL per public page.
- No accidental `noindex` on homepage, categories, brands, products, or sitemap-linked pages.
- `robots.txt` does not block public catalog pages.
- `/admin-portal/`, `/django-admin/`, `/accounts/`, `/cart/`, and `/checkout/` remain blocked or non-indexable.
- Product pages have unique title and meta description values.
- Product JSON-LD is valid and contains product name, image where available, SKU, price, currency, availability, and URL.
- Breadcrumb JSON-LD matches visible breadcrumbs.
- Images have meaningful alt text where they communicate content.
- No broken links, redirect chains, or mixed HTTP/HTTPS URLs.
- Mobile layout works at 390px width.

### Step 5: Improve content, not just metadata

Prioritize:

1. Add accurate product descriptions.
2. Add top, heart, and base notes where known.
3. Add scent family and occasion where known.
4. Add concentration through the existing variant attribute named `Concentration`.
5. Do not invent fragrance notes, authenticity claims, ratings, or reviews.
6. Use real customer reviews only through the delivered-order verification and merchant moderation flow.

### Step 6: Monitor for at least 2-4 weeks

Track weekly:

- Impressions
- Clicks
- CTR
- Average position
- Indexed pages
- Excluded pages and reasons
- Queries
- Top landing pages
- Mobile vs desktop performance
- Pakistan performance

Do not judge SEO from a one-day export with two impressions.

## Current Application Features Relevant to SEO

- Brand homepage tiles and full `/brands/` directory.
- Brand-filtered product URLs such as `/products/?brand=afnan`.
- Product detail pages with trending products based on recent qualifying order quantities.
- Verified moderated product reviews.
- Mobile filter drawer for listing pages.
- Favicon and Facebook footer link.
- Sitemap and robots endpoints.

## Potential Follow-Up Improvement

The current sitemap includes published products, published categories, homepage, product listing, and order tracking. Consider adding `/brands/` to the sitemap as a small SEO improvement, then regenerate, test, deploy, and verify it in Search Console.

Before making that change, confirm the current sitemap output and add a focused test that the brand directory URL is included.

## Deployment Notes

The last ScentAndStyle deployment:

- Backup directory: `/root/scentandstyle-deploy-backups/20260929-222953/`
- Database backup: `ecommerce-before.dump`
- File/static backup: `app-static-before.tgz`
- Three additive migrations were applied for fragrance fields, review rate-limit scope, and ProductReview.
- Only `scentandstyle.service` was restarted.
- `mps.scentandstyle.pk` was not accessed or changed.

Any future deployment must repeat the backup-first process and verify the live domain after deployment.
