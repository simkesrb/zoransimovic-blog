# zoransimovic.com — review site repo

A static review blog with a browser-based admin panel (Pages CMS).
Write in the browser → commit to GitHub → Cloudflare builds and publishes.

## Editing

1. Go to **https://app.pagescms.org**
2. Log in with GitHub, pick this repository
3. Click **Reviews** → pick one → edit → **Save**

Every save commits to GitHub. Cloudflare rebuilds in about 40 seconds and the
change is live. No terminal, no Python, no asking anyone.

To add a review: **Reviews → Add entry**. Fill the form, upload a screenshot,
hit Save. It appears on the homepage, its category page, and the sitemap.

## What each field does

| Field | Where it shows |
|---|---|
| `product` | Title, CTA, card |
| `slug` | The URL: `/reviews/<slug>/` — never change it after publishing |
| `cat` | Category page + nav section |
| `score` | The big number, stars, and the Google star-rating snippet |
| `pros` / `cons` | The green and red boxes |
| `scores` | The score bars |
| `best_for` / `skip_if` | The "who it's for" section |
| `verdict` | The conclusion box |
| `faq` | The accordion **and** FAQ schema for Google |
| `affiliate_url` | Where every "Check price" button points |
| `draft` | Ticked = excluded from the build |
| `body` | The long-form article |

## Building locally (optional)

```bash
python3 build_review_site.py     # writes ./dist
```

No dependencies needed — PyYAML is used if present, otherwise a built-in
parser handles the front matter. Output is byte-identical either way.

## Cloudflare Pages settings

| Setting | Value |
|---|---|
| Framework preset | None |
| Build command | `python3 build_review_site.py` |
| Build output directory | `dist` |
| Environment variable | `PYTHON_VERSION` = `3.12` |

## Files

```
.pages.yml                 admin panel definition (fields, categories)
content/reviews/*.md       one file per review — the only thing you edit
public/images/             uploaded images (Pages CMS puts them here)
build_review_site.py       renders Markdown → static HTML in dist/
_redirects.src             old URL → new URL map, copied into dist/
```

## Before going live with AdSense

1. Replace the 6 placeholder reviews with your own writing (they describe
   invented products — they are a design demo, not real reviews)
2. Put your publisher ID in `ads.txt` (currently `pub-0000000000000000`)
3. Replace the `AD(...)` placeholders in `build_review_site.py` with real
   AdSense units — search for `ADSENSE`
4. Add a real photo to the About page
