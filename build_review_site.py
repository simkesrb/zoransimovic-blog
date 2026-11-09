#!/usr/bin/env python3
"""
Build zoransimovic.com — clean affiliate review blog, from scratch.

    python3 build_review_site.py

Output: ../reviewsite/
  index.html                    homepage (featured + grid)
  reviews/<slug>/index.html     full review pages (pros/cons, score, CTA, schema)
  category/<slug>/index.html    category archives
  about / privacy / contact / disclosure / 404
  sitemap.xml  robots.txt  ads.txt  _redirects
  images/*.jpg

Every review page carries Review + FAQPage + BreadcrumbList JSON-LD, which is what
gets star ratings and FAQ dropdowns into Google results.
No external requests: fonts, CSS and images all local.
"""
import html
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dist")
IMGS = os.path.join(HERE, "public", "images")
INVENTORY = os.path.join(HERE, "_redirects.src")

SITE = "Zoran Simović"
DOMAIN = "https://zoransimovic.com"
YEAR = "2026"
EMAIL = "simkekg@gmail.com"
ADSENSE = "ca-pub-0000000000000000"
HOST = "Kragujevac, Serbia"

CATS = {
    "email-marketing": ("Email Marketing", "📧", "Autoresponders, deliverability and list building."),
    "page-builders": ("Page Builders", "🧱", "Tools for building landing pages without a developer."),
    "social-media": ("Social Media", "📱", "Scheduling, publishing and growing an audience."),
}

# --------------------------------------------------------------- content
# Reviews live in content/reviews/*.md — YAML front matter + free-form Markdown body.
# That means you (or a CMS) can add a review by creating one file. No Python needed.
CONTENT = os.path.join(HERE, "content", "reviews")
ROOT = HERE   # loose files from web uploads land here



def _mini_yaml(text):
    """Dependency-free parser for the YAML subset Pages CMS writes.

    Handles: key: value, quoted values, numbers, booleans, lists of scalars,
    lists of objects (with indented sub-keys), and folded continuation lines.
    Used only when PyYAML is unavailable (e.g. a bare Cloudflare build image).
    """
    data, key, i = {}, None, 0
    lines = text.replace("\r\n", "\n").split("\n")

    def coerce(v):
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            return v[1:-1]
        low = v.lower()
        if low in ("true", "false"):
            return low == "true"
        if low in ("null", "~", ""):
            return None
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return v

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        indent = len(raw) - len(raw.lstrip())

        if indent == 0 and ":" in line and not line.startswith("- "):
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip()
            if v:
                data[k] = coerce(v)
                key = None
            else:
                data[k] = None
                key = k
            i += 1
            continue

        if line.startswith("- "):
            item = line[2:].strip()
            if key is None:
                i += 1
                continue
            if data.get(key) is None:
                data[key] = []
            # object list item: "- name: X" followed by deeper "- " pairs
            if ":" in item and not item.startswith(("http", "//")):
                obj = {}
                k2, _, v2 = item.partition(":")
                obj[k2.strip()] = coerce(v2)
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    nt = nxt.strip()
                    ni = len(nxt) - len(nxt.lstrip())
                    if not nt:
                        i += 1
                        continue
                    if ni <= indent and nt.startswith("- "):
                        break
                    if ":" in nt:
                        k3, _, v3 = nt.partition(":")
                        obj[k3.strip()] = coerce(v3)
                        i += 1
                        continue
                    break
                data[key].append(obj)
                continue
            data[key].append(coerce(item))
            i += 1
            continue

        # continuation of a multi-line scalar
        if key and isinstance(data.get(key), str):
            data[key] = (data[key] + " " + line).strip()
        elif key and isinstance(data.get(key), list) and data[key] and isinstance(data[key][-1], str):
            data[key][-1] = (data[key][-1] + " " + line).strip()
        i += 1
    return data


def parse_frontmatter(text):
    head = text[3:text.find("\n---", 3)]
    try:
        import yaml
        return yaml.safe_load(head) or {}
    except Exception:
        return _mini_yaml(head)


def review_files():
    """Reviews live in content/reviews/. Files ending -review.md at the repo root
    are also accepted (they happen when files are uploaded through the web UI)."""
    found = []
    if os.path.isdir(CONTENT):
        found += [os.path.join(CONTENT, f) for f in sorted(os.listdir(CONTENT))
                  if f.endswith((".md", ".markdown"))]
    else:
        print(f"note: {CONTENT} does not exist yet")
    found += [os.path.join(ROOT, f) for f in sorted(os.listdir(ROOT))
              if f.endswith("-review.md")]
    return found


def find_image(name):
    """Images may sit in public/images or at the repo root."""
    for d in (os.path.join(HERE, "public", "images"), HERE):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    return None


def load_reviews():
    out = []
    for path in review_files():
        fn = os.path.basename(path)
        raw = open(path, encoding="utf-8").read()
        if not raw.startswith("---"):
            continue
        end = raw.find("\n---", 3)
        meta = parse_frontmatter(raw)
        body = raw[end + 4:]
        if meta.get("draft"):
            continue
        slug = meta.get("slug") or fn.rsplit(".", 1)[0]
        r = {
            "slug": slug,
            "product": meta.get("product", slug),
            "cat": meta.get("cat", "email-marketing"),
            "emoji": meta.get("emoji", "⭐"),
            "score": float(meta.get("score", 8)),
            "badge": meta.get("badge", "Reviewed"),
            "price": meta.get("price", ""),
            "image": meta.get("image", "review-email.jpg"),
            "verified": meta.get("verified", "Tested"),
            "tagline": (meta.get("tagline") or "").strip(),
            "summary": (meta.get("summary") or "").strip(),
            "pros": meta.get("pros") or [],
            "cons": meta.get("cons") or [],
            "best_for": (meta.get("best_for") or "").strip(),
            "skip_if": (meta.get("skip_if") or "").strip(),
            "verdict": (meta.get("verdict") or "").strip(),
            "scores": [(d["name"], d["value"]) for d in (meta.get("scores") or [])],
            "faq": [(d["q"], d["a"]) for d in (meta.get("faq") or [])],
            "body_md": body,
            "affiliate_url": meta.get("affiliate_url", "#"),
            "date": str(meta.get("date", f"{YEAR}-01-15")),
        }
        if not r["scores"]:
            r["scores"] = [("Overall", r["score"])]
        r["has_image"] = find_image(r["image"]) is not None
        # a sparse entry (saved from the CMS with only a few fields filled) should
        # still render a sensible page rather than blank boxes
        if not r["tagline"]:
            r["tagline"] = r["summary"] or ""
        if not r["summary"]:
            r["summary"] = r["tagline"]
        r["cat_name"] = CATS.get(r["cat"], ("Reviews", "⭐", ""))[0]
        r["cat_emoji"] = CATS.get(r["cat"], ("Reviews", "⭐", ""))[1]
        r["url"] = f"/reviews/{r['slug']}/"
        out.append(r)
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


REVIEWS = load_reviews()
BY_SLUG = {r["slug"]: r for r in REVIEWS}


# ------------------------------------------------------------------------- CSS
CSS = """
*{box-sizing:border-box}
:root{
 --bg:#ffffff; --soft:#f6f7f9; --ink:#12141a; --ink2:#33373f; --muted:#6b7280;
 --line:#e6e8ec; --brand:#4f46e5; --brand2:#6366f1; --green:#059669; --red:#dc2626;
 --gold:#f59e0b; --radius:14px;
 --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
body{margin:0;background:var(--bg);color:var(--ink);font:400 17px/1.7 var(--sans);
 -webkit-font-smoothing:antialiased}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
img{max-width:100%;display:block}
.wrap{max-width:1080px;margin:0 auto;padding:0 22px}
.narrow{max-width:760px;margin:0 auto;padding:0 22px}

/* header */
header{border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(255,255,255,.94);
 backdrop-filter:blur(10px);z-index:50}
.hd{max-width:1080px;margin:0 auto;padding:0 22px;height:66px;display:flex;align-items:center;
 justify-content:space-between;gap:20px}
.logo{font-weight:800;font-size:19px;letter-spacing:-.02em;color:var(--ink)}
.logo em{font-style:normal;color:var(--brand)}
nav.top{display:flex;gap:24px;font-size:14.5px;font-weight:600}
nav.top a{color:var(--ink2)}
nav.top a:hover{color:var(--brand);text-decoration:none}
@media(max-width:760px){.hd{height:auto;flex-direction:column;align-items:flex-start;gap:8px;padding:12px 22px}
 nav.top{gap:14px;font-size:13px;width:100%;overflow-x:auto}}

/* hero */
.hero{background:linear-gradient(180deg,#fafaff 0%,#fff 100%);border-bottom:1px solid var(--line);
 padding:54px 0 44px;text-align:center}
.hero h1{font-size:clamp(2rem,5vw,3.1rem);line-height:1.1;letter-spacing:-.03em;margin:0 auto 16px;
 max-width:20ch;font-weight:800}
.hero h1 span{background:linear-gradient(120deg,var(--brand),#a855f7);-webkit-background-clip:text;
 background-clip:text;-webkit-text-fill-color:transparent}
.hero p{font-size:19px;color:var(--muted);max-width:56ch;margin:0 auto 24px}
.trust{display:flex;gap:22px;justify-content:center;flex-wrap:wrap;font-size:13.5px;
 color:var(--muted);font-weight:600}
.trust span{display:flex;align-items:center;gap:7px}

/* section */
.sec{padding:46px 0}
.sec-h{display:flex;align-items:baseline;justify-content:space-between;margin:0 0 26px}
.sec-h h2{font-size:1.6rem;letter-spacing:-.02em;margin:0;font-weight:800}
.sec-h a{font-size:14px;font-weight:700}

/* featured */
.feat{display:grid;grid-template-columns:1.05fr .95fr;gap:0;border:1px solid var(--line);
 border-radius:var(--radius);overflow:hidden;box-shadow:0 10px 30px rgba(18,20,26,.06)}
@media(max-width:820px){.feat{grid-template-columns:1fr}}
.feat .img{min-height:300px;background:#eee}
.feat .img img{width:100%;height:100%;object-fit:cover}
.feat .body{padding:34px 32px;display:flex;flex-direction:column;justify-content:center}
.tag{display:inline-flex;align-items:center;gap:6px;background:#eef2ff;color:#4338ca;
 font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;padding:6px 11px;
 border-radius:999px;margin-bottom:14px;width:fit-content}
.feat h3{font-size:1.75rem;line-height:1.2;letter-spacing:-.02em;margin:0 0 10px;font-weight:800}
.feat h3 a{color:var(--ink)}
.feat p{color:var(--muted);margin:0 0 20px;font-size:16px}
.scoreline{display:flex;align-items:center;gap:12px;margin-bottom:18px}
.score{background:var(--green);color:#fff;font-weight:800;font-size:15px;padding:5px 12px;
 border-radius:8px;letter-spacing:-.01em}
.stars{color:var(--gold);font-size:16px;letter-spacing:2px}

/* grid */
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:26px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:620px){.grid{grid-template-columns:1fr}}
.card{border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;
 display:flex;flex-direction:column;transition:transform .16s,box-shadow .16s;background:#fff}
.card:hover{transform:translateY(-3px);box-shadow:0 14px 34px rgba(18,20,26,.10)}
.card .thumb{aspect-ratio:16/10;overflow:hidden;background:#f1f2f5}
.card .thumb img{width:100%;height:100%;object-fit:cover;transition:transform .3s}
.card:hover .thumb img{transform:scale(1.04)}
.card .cb{padding:20px;display:flex;flex-direction:column;flex:1}
.card .meta{font-size:11.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;
 color:var(--brand);margin-bottom:9px}
.card h3{font-size:1.12rem;line-height:1.32;margin:0 0 8px;font-weight:800;letter-spacing:-.01em}
.card h3 a{color:var(--ink)}
.card p{font-size:14.5px;color:var(--muted);margin:0 0 16px;flex:1;line-height:1.6}
.cardfoot{display:flex;align-items:center;justify-content:space-between;border-top:1px solid var(--line);
 padding-top:13px}
.price{font-weight:800;font-size:15px}
.price small{font-weight:600;color:var(--muted);font-size:12px}
.readmore{font-size:13px;font-weight:800;color:var(--brand)}

/* article */
.arthead{padding:44px 0 0}
.kicker{display:inline-flex;gap:7px;align-items:center;background:#f3f4f6;color:var(--ink2);
 font-size:12px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;padding:6px 12px;
 border-radius:999px;margin-bottom:16px}
.arthead h1{font-size:clamp(1.9rem,4.4vw,2.9rem);line-height:1.13;letter-spacing:-.03em;
 margin:0 0 14px;font-weight:800;max-width:24ch}
.dek{font-size:19px;color:var(--muted);margin:0 0 18px;max-width:62ch}
.byline{font-size:13.5px;color:var(--muted);display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.byline b{color:var(--ink2)}
.hero-img{margin:26px 0 0;border-radius:var(--radius);overflow:hidden;border:1px solid var(--line)}
.hero-img img{width:100%;aspect-ratio:16/8;object-fit:cover}

/* score box */
.scorebox{display:grid;grid-template-columns:auto 1fr;gap:28px;align-items:center;
 border:1px solid var(--line);border-radius:var(--radius);padding:24px 26px;margin:30px 0;
 background:linear-gradient(180deg,#fbfcff,#fff)}
@media(max-width:620px){.scorebox{grid-template-columns:1fr;gap:18px}}
.bigscore{text-align:center;padding-right:26px;border-right:1px solid var(--line)}
@media(max-width:620px){.bigscore{border-right:0;border-bottom:1px solid var(--line);padding:0 0 16px}}
.bigscore .n{font-size:3rem;font-weight:800;line-height:1;letter-spacing:-.04em;color:var(--green)}
.bigscore .d{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;
 letter-spacing:.1em;margin-top:6px}
.bars{display:flex;flex-direction:column;gap:9px}
.bar{display:grid;grid-template-columns:120px 1fr 34px;gap:12px;align-items:center;font-size:13.5px}
@media(max-width:520px){.bar{grid-template-columns:92px 1fr 30px;font-size:12.5px}}
.bar .t{color:var(--ink2);font-weight:600}
.track{height:8px;background:#edeff3;border-radius:99px;overflow:hidden}
.fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--brand),#a855f7)}
.bar .v{font-weight:800;text-align:right;color:var(--ink2)}

/* pros cons */
.pc{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin:30px 0}
@media(max-width:700px){.pc{grid-template-columns:1fr}}
.pc .box{border-radius:var(--radius);padding:22px 24px;border:1px solid}
.pc .pros{background:#f0fdf4;border-color:#bbf7d0}
.pc .cons{background:#fef2f2;border-color:#fecaca}
.pc h3{margin:0 0 14px;font-size:1rem;font-weight:800;display:flex;align-items:center;gap:8px}
.pc .pros h3{color:#166534}
.pc .cons h3{color:#991b1b}
.pc ul{margin:0;padding:0;list-style:none}
.pc li{position:relative;padding-left:26px;margin-bottom:11px;font-size:15px;line-height:1.55}
.pc .pros li{color:#14532d}
.pc .cons li{color:#7f1d1d}
.pc .pros li:before{content:"✓";position:absolute;left:0;font-weight:800;color:var(--green)}
.pc .cons li:before{content:"✕";position:absolute;left:0;font-weight:800;color:var(--red)}
.pc li:last-child{margin-bottom:0}

/* cta */
.cta{border:1px solid #d9d6fe;background:linear-gradient(135deg,#eef2ff,#faf5ff);
 border-radius:var(--radius);padding:28px;text-align:center;margin:32px 0}
.cta h3{margin:0 0 8px;font-size:1.25rem;font-weight:800}
.cta p{margin:0 0 18px;color:var(--muted);font-size:15px}
.btn{display:inline-block;background:var(--brand);color:#fff;font-weight:800;font-size:16px;
 padding:15px 30px;border-radius:11px;box-shadow:0 8px 20px rgba(79,70,229,.28);
 transition:transform .14s,box-shadow .14s}
.btn:hover{text-decoration:none;transform:translateY(-2px);box-shadow:0 12px 26px rgba(79,70,229,.34)}
.btn small{display:block;font-weight:600;font-size:11.5px;opacity:.85;margin-top:3px}

/* body prose */
.prose{max-width:760px;margin:0 auto}
.prose h2{font-size:1.55rem;letter-spacing:-.02em;margin:44px 0 14px;font-weight:800}
.prose h3{font-size:1.18rem;margin:32px 0 10px;font-weight:800}
.prose p{margin:0 0 20px;color:var(--ink2)}
.prose ul,.prose ol{padding-left:22px;color:var(--ink2);margin:0 0 20px}
.prose li{margin-bottom:9px}
.prose blockquote{margin:26px 0;padding:4px 0 4px 20px;border-left:3px solid var(--brand);
 color:var(--muted);font-style:italic}
.prose table{width:100%;border-collapse:collapse;margin:26px 0;font-size:15px}
.prose th,.prose td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left}
.prose th{font-weight:800;font-size:12.5px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}
.toc{border:1px solid var(--line);border-radius:var(--radius);padding:20px 24px;margin:30px 0;
 background:var(--soft)}
.toc h4{margin:0 0 10px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
.toc ol{margin:0;padding-left:20px;font-size:15px}
.toc li{margin-bottom:6px}

/* callouts */
.note{border-left:4px solid var(--gold);background:#fffbeb;padding:16px 20px;border-radius:0 10px 10px 0;
 margin:26px 0;font-size:15.5px;color:#78350f}
.note b{color:#78350f}
.verdict{border:2px solid var(--brand);border-radius:var(--radius);padding:26px 28px;margin:34px 0;
 background:#fafaff}
.verdict h3{margin:0 0 10px;font-size:1.15rem;font-weight:800;display:flex;gap:9px;align-items:center}
.verdict p{margin:0;color:var(--ink2)}

/* faq */
.faq{margin:38px 0}
.faq details{border:1px solid var(--line);border-radius:11px;padding:0;margin-bottom:10px;
 background:#fff;overflow:hidden}
.faq summary{cursor:pointer;padding:17px 20px;font-weight:700;font-size:16px;list-style:none;
 display:flex;justify-content:space-between;gap:14px;align-items:center}
.faq summary::-webkit-details-marker{display:none}
.faq summary:after{content:"+";font-size:22px;font-weight:400;color:var(--brand);line-height:1}
.faq details[open] summary:after{content:"–"}
.faq .a{padding:0 20px 18px;color:var(--ink2);font-size:15.5px;line-height:1.65}

/* ads */
.ad{border:1px dashed #d8dbe2;border-radius:10px;background:#fafbfc;text-align:center;
 padding:12px;margin:30px auto;max-width:760px}
.ad span{font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;color:#b0b5bd;font-weight:700}
.ad .ph{min-height:86px;display:grid;place-items:center;color:#c3c7ce;font-size:12px}

/* honesty strip */
.honest{background:var(--soft);border-top:1px solid var(--line);border-bottom:1px solid var(--line);
 padding:26px 0;margin:0}
.honest .in{display:flex;gap:16px;align-items:flex-start;max-width:760px;margin:0 auto;padding:0 22px;
 font-size:14.5px;color:var(--ink2);line-height:1.6}
.honest b{color:var(--ink)}

/* footer */
footer{border-top:1px solid var(--line);background:#fbfbfc;margin-top:50px;padding:40px 0 50px}
.fgrid{display:grid;grid-template-columns:1.4fr 1fr 1fr;gap:34px;font-size:14px}
@media(max-width:700px){.fgrid{grid-template-columns:1fr;gap:24px}}
footer h4{font-size:11.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);
 margin:0 0 12px;font-weight:800}
footer ul{list-style:none;margin:0;padding:0}
footer li{margin-bottom:9px}
footer a{color:var(--ink2)}
.fbot{margin-top:32px;padding-top:20px;border-top:1px solid var(--line);font-size:13px;color:var(--muted);
 display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.disc{font-size:12.5px;color:var(--muted);line-height:1.6;max-width:44ch}
"""


def simple_md(md):
    """Minimal Markdown -> HTML for review bodies (headings, lists, paras, bold, links)."""
    out = []
    for block in re.split(r"\n\s*\n", md or ""):
        b = block.strip()
        if not b:
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", b, re.S)
        if m:
            lvl = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{lvl}>{inline_md(m.group(2))}</h{lvl}>")
            continue
        if b.startswith("!["):
            for src in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", b):
                out.append(f'<figure><img src="{html.escape(src)}" alt="" loading="lazy"></figure>')
            continue
        if re.match(r"^[-*]\s+", b):
            items = "".join(f"<li>{inline_md(re.sub(r'^[-*]\\s+', '', l))}</li>"
                            for l in b.splitlines() if l.strip())
            out.append(f"<ul>{items}</ul>")
            continue
        out.append(f"<p>{inline_md(b)}</p>")
    return "\n".join(out)


def inline_md(s):
    s = html.escape(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def stars(score):
    n = score / 2
    full = int(round(n))
    return "★" * full + "☆" * (5 - full)


def header():
    return f"""<header><div class="hd">
<a class="logo" href="/">Zoran<em>Reviews</em></a>
<nav class="top">
<a href="/">Home</a>
<a href="/category/email-marketing/">Email</a>
<a href="/category/page-builders/">Builders</a>
<a href="/category/social-media/">Social</a>
<a href="/about">About</a>
</nav></div></header>"""


def footer():
    return f"""<footer><div class="wrap">
<div class="fgrid">
  <div>
    <div class="logo" style="margin-bottom:10px">Zoran<em>Reviews</em></div>
    <p class="disc">Honest reviews of the tools I actually use to run an online business.
    Written in {HOST}. Some links are affiliate links — if you buy through them I may earn
    a commission at no extra cost to you.</p>
  </div>
  <div><h4>Categories</h4><ul>
    <li><a href="/category/email-marketing/">Email Marketing</a></li>
    <li><a href="/category/page-builders/">Page Builders</a></li>
    <li><a href="/category/social-media/">Social Media</a></li>
  </ul></div>
  <div><h4>Site</h4><ul>
    <li><a href="/about">About</a></li>
    <li><a href="/contact">Contact</a></li>
    <li><a href="/disclosure">Affiliate Disclosure</a></li>
    <li><a href="/privacy">Privacy</a></li>
  </ul></div>
</div>
<div class="fbot">
  <span>© {YEAR} {SITE}</span>
  <span>Built in {HOST} · <a href="/sitemap.xml">Sitemap</a></span>
</div></div></footer>"""


def shell(title, desc, content, canonical, extra_head="", og_image=None):
    og = f"{DOMAIN}/images/{og_image}" if og_image else f"{DOMAIN}/images/review-email.jpg"
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(desc[:158])}">
<link rel="canonical" href="{DOMAIN}{canonical}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc[:158])}">
<meta property="og:url" content="{DOMAIN}{canonical}">
<meta property="og:image" content="{og}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary_large_image">
<meta name="robots" content="index,follow,max-image-preview:large">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='18' fill='%234f46e5'/><text x='50' y='70' font-size='58' font-family='sans-serif' font-weight='bold' fill='white' text-anchor='middle'>Z</text></svg>">
<style>{CSS}</style>
{extra_head}
</head><body>
{header()}
{content}
{footer()}
</body></html>"""


AD = lambda label: f"""<div class="ad"><span>Advertisement</span><div class="ph">{label}</div></div>"""


# --------------------------------------------------------------------- pages
def review_card(r, show_cat=True):
    thumb = (f'<a href="{r["url"]}" class="thumb"><img src="/images/{r["image"]}"'
             f' alt="{html.escape(r["product"])} review — {html.escape(r["cat_name"])}"'
             f' loading="lazy"></a>') if r["has_image"] else ""
    return f"""<article class="card">
{thumb}
<div class="cb">
  <div class="meta">{r['cat_emoji']} {r['cat_name']}</div>
  <h3><a href="{r['url']}">{html.escape(r['product'])} Review {YEAR}: {html.escape(r['badge'])}</a></h3>
  <p>{html.escape(r['tagline'][:118])}…</p>
  <div class="cardfoot">
    <div class="price">{r['price']}</div>
    <div class="stars" title="{r['score']} out of 10">{stars(r['score'])}</div>
  </div>
</div></article>"""


def build_home():
    if not REVIEWS:
        body = """
<section class="hero"><div class="wrap">
  <h1>Reviews are on the way. <span>Add the first one.</span></h1>
  <p>This site is wired up and ready. Open Pages CMS, click
     <b>Reviews → Add an entry</b>, fill in the form and save —
     the first review appears here automatically.</p>
  <div class="trust">
    <span>✅ Site builds and deploys on save</span>
    <span>⚡ Live in about 40 seconds</span>
  </div>
</div></section>"""
        return shell("Reviews coming soon | ZoranReviews",
                     "Software reviews with real testing, pros and cons.",
                     body, "/")
    feat = REVIEWS[0]
    others = REVIEWS[1:]
    body = f"""
<section class="hero"><div class="wrap">
  <h1>Tools tested. <span>Verdicts without the fluff.</span></h1>
  <p>I buy the software, use it for at least a month, and write down what actually
     happened — including the parts that annoyed me. 🕵️</p>
  <div class="trust">
    <span>✅ 6 in-depth reviews</span>
    <span>⏱️ 30+ days testing each</span>
    <span>💸 Affiliate links disclosed</span>
  </div>
</div></section>

<section class="sec"><div class="wrap">
  <div class="sec-h"><h2>⭐ Top pick this month</h2></div>
  <div class="feat">
    <div class="img"><img src="/images/{feat['image']}" alt="{html.escape(feat['product'])} review" loading="lazy"></div>
    <div class="body">
      <span class="tag">🏆 {feat['badge']}</span>
      <h3><a href="{feat['url']}">{html.escape(feat['product'])} Review {YEAR}</a></h3>
      <p>{html.escape(feat['tagline'])}</p>
      <div class="scoreline">
        <span class="score">{feat['score']}/10</span>
        <span class="stars">{stars(feat['score'])}</span>
      </div>
      <a class="btn" href="{feat['url']}">Read the full review →<small>{feat['verified']}</small></a>
    </div>
  </div>
</div></section>

{AD("Leaderboard · 970×90")}

<section class="sec"><div class="wrap">
  <div class="sec-h"><h2>🔥 All reviews</h2><a href="/category/email-marketing/">Browse by category →</a></div>
  <div class="grid">{''.join(review_card(r) for r in others)}</div>
</div></section>

<section class="sec" style="background:var(--soft);border-top:1px solid var(--line)">
  <div class="wrap"><div class="sec-h"><h2>📬 How I test</h2></div>
  <div class="grid" style="grid-template-columns:repeat(3,1fr)">
    <div><h3 style="margin:0 0 8px;font-size:1rem">1. I pay for it 💳</h3>
      <p style="font-size:14.5px;color:var(--muted);margin:0">Every tool here was bought at the
      normal price. No free accounts, no favours, no sponsored placements.</p></div>
    <div><h3 style="margin:0 0 8px;font-size:1rem">2. A month of real use ⏱️</h3>
      <p style="font-size:14.5px;color:var(--muted);margin:0">Minimum 30 days, doing the work
      the tool is actually for — not clicking around a demo.</p></div>
    <div><h3 style="margin:0 0 8px;font-size:1rem">3. Cons are mandatory ✍️</h3>
      <p style="font-size:14.5px;color:var(--muted);margin:0">If a review has no downsides,
      it isn't a review. Every verdict lists what I didn't like.</p></div>
  </div></div>
</section>
"""
    ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": f"{SITE} Reviews",
        "url": DOMAIN,
        "description": "Honest software reviews with pros, cons and real testing.",
    }
    return shell(
        f"Software Reviews {YEAR} — Tested, Rated, and Honest | ZoranReviews",
        "Honest reviews of email marketing, page builder and social media tools. "
        "30+ days of real testing each, with pros, cons and a clear verdict.",
        body, "/",
        extra_head=f'<script type="application/ld+json">{json.dumps(ld)}</script>',
        og_image=feat["image"],
    )


def build_review(r):
    related = [x for x in REVIEWS if x["cat"] == r["cat"] and x["slug"] != r["slug"]][:2]
    related += [x for x in REVIEWS if x["slug"] != r["slug"]][:2]
    related = related[:3]

    bars = "".join(
        f'<div class="bar"><div class="t">{html.escape(name)}</div>'
        f'<div class="track"><div class="fill" style="width:{v*10}%"></div></div>'
        f'<div class="v">{v}</div></div>'
        for name, v in r["scores"]
    )
    pros = "".join(f"<li>{html.escape(p)}</li>" for p in r["pros"])
    cons = "".join(f"<li>{html.escape(c)}</li>" for c in r["cons"])
    faq_html = "".join(
        f"<details><summary>{html.escape(q)}</summary>"
        f'<div class="a">{html.escape(a)}</div></details>'
        for q, a in r["faq"]
    )
    sections = [("what-is-it", f"What is {r['product']}?")]
    if r["pros"] or r["cons"]:
        sections.append(("pros-cons", "Pros and cons"))
    sections += [("scores", "How it scored"), ("who-for", "Who it's for")]
    if r["verdict"]:
        sections.append(("verdict", "Verdict"))
    if r["faq"]:
        sections.append(("faq", "FAQ"))
    toc = "".join(f'<li><a href="#{a}">{html.escape(t)}</a></li>' for a, t in sections)

    body_html = simple_md(r["body_md"])

    pc_block = ""
    if r["pros"] or r["cons"]:
        p_ = "".join(f"<li>{html.escape(x)}</li>" for x in r["pros"]) or "<li>—</li>"
        c_ = "".join(f"<li>{html.escape(x)}</li>" for x in r["cons"]) or "<li>—</li>"
        pc_block = (f'<div class="narrow" style="padding-top:0"><div class="pc">'
                    f'<div class="box pros"><h3>✅ What I liked</h3><ul>{p_}</ul></div>'
                    f'<div class="box cons"><h3>❌ What I didn\'t</h3><ul>{c_}</ul></div>'
                    f'</div></div>')

    faq_block = ""
    if r["faq"]:
        fq = "".join(f"<details><summary>{html.escape(q)}</summary>"
                     f'<div class="a">{html.escape(a)}</div></details>' for q, a in r["faq"])
        faq_block = ('<div class="prose"><h2 id="faq">Frequently asked questions ❓</h2></div>'
                     f'<div class="faq">{fq}</div>')

    cta_line = ("Best price I found — " + html.escape(r["price"]) + ". The link below supports this site at no extra cost to you."
                if r["price"] else
                "The link below supports this site at no extra cost to you.")
    btn_sub = (html.escape(r["price"]) + " · affiliate link") if r["price"] else "affiliate link"
    dek = f'<p class="dek">{html.escape(r["tagline"])}</p>' if r["tagline"] else ""
    summary_p = f'<p>{html.escape(r["summary"])}</p>' if r["summary"] else ""
    verdict_block = (f'<div class="verdict"><h3>🏁 The verdict</h3>'
                     f'<p>{html.escape(r["verdict"])}</p></div>') if r["verdict"] else ""
    hero_img = (f'<div class="hero-img"><img src="/images/{r["image"]}"'
                f' alt="{html.escape(r["product"])} — review"></div>') if r["has_image"] else ""
    content = f"""
<div class="wrap arthead">
  <div class="kicker">{r['cat_emoji']} {r['cat_name']}</div>
  <h1>{html.escape(r['product'])} Review {YEAR}: {html.escape(r['badge'])} 🏆</h1>
  {dek}
  <div class="byline">
    <span>By <b>{SITE}</b></span>
    <span>·</span><span>{r['verified']}</span>
    <span>·</span><span>Updated {YEAR}</span>
  </div>
  {hero_img}
</div>

<div class="narrow" style="padding-top:0">
  <div class="scorebox">
    <div class="bigscore"><div class="n">{r['score']}</div><div class="d">out of 10</div>
      <div class="stars" style="margin-top:8px">{stars(r['score'])}</div></div>
    <div class="bars">{bars}</div>
  </div>

  <div class="toc"><h4>Jump to</h4><ol>{toc}</ol></div>

  <div class="prose">
    <h2 id="what-is-it">What is {html.escape(r['product'])}? 🤔</h2>
    {summary_p}
    <div class="note"><b>Disclosure:</b> some links on this page are affiliate links.
      If you buy through them I may earn a commission — it never changes the price you pay,
      and it never changes the verdict. <a href="/disclosure">Full disclosure</a>.</div>

    <h2 id="pros-cons">Pros and cons ⚖️</h2>
  </div>
</div>

{pc_block}

<div class="narrow">
  <div class="cta">
    <h3>Ready to try {html.escape(r['product'])}? 🚀</h3>
    <p>{cta_line}</p>
    <a class="btn" href="{html.escape(r['affiliate_url'])}" rel="nofollow sponsored">Check price on official site →<small>{btn_sub}</small></a>
  </div>

  <div class="prose">
    <h2 id="scores">How it scored 📊</h2>
    <p>Each category is scored out of ten, based on my own use rather than the vendor's feature list.
       The overall score is weighted towards the things that matter in daily work.</p>
    <table>
      <tr><th>Category</th><th>Score</th><th>Note</th></tr>
      {''.join(f"<tr><td>{html.escape(n)}</td><td><b>{v}/10</b></td><td>{'Exceptional' if v>=9 else 'Solid' if v>=8 else 'Adequate' if v>=7 else 'Weak spot'}</td></tr>" for n,v in r['scores'])}
    </table>

    <h2 id="who-for">Who it's for 🎯</h2>
    <p><b>Buy it if:</b> {html.escape(r['best_for'])}</p>
    <p><b>Skip it if:</b> {html.escape(r['skip_if'])}</p>
  </div>

  {AD("In-article ad · responsive")}

  {verdict_block}

  <div class="prose">{body_html}</div>

  {faq_block}
</div>

<section class="sec" style="border-top:1px solid var(--line)">
  <div class="wrap"><div class="sec-h"><h2>📚 Related reviews</h2></div>
  <div class="grid">{''.join(review_card(x) for x in related)}</div></div>
</section>
"""

    ld_review = {
        "@context": "https://schema.org",
        "@type": "Review",
        "itemReviewed": {"@type": "SoftwareApplication", "name": r["product"],
                         "applicationCategory": "BusinessApplication",
                         "operatingSystem": "Web"},
        "reviewRating": {"@type": "Rating", "ratingValue": r["score"],
                         "bestRating": "10", "worstRating": "1"},
        "author": {"@type": "Person", "name": SITE},
        "publisher": {"@type": "Organization", "name": f"{SITE} Reviews"},
        "reviewBody": r["verdict"],
        "datePublished": f"{YEAR}-01-15",
    }
    ld_faq = {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in r["faq"]],
    }
    ld_crumbs = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": DOMAIN + "/"},
            {"@type": "ListItem", "position": 2, "name": r["cat_name"],
             "item": f"{DOMAIN}/category/{r['cat']}/"},
            {"@type": "ListItem", "position": 3, "name": f"{r['product']} Review"},
        ],
    }
    blocks = [ld_review, ld_crumbs] + ([ld_faq] if r["faq"] else [])
    head = "".join(
        f'<script type="application/ld+json">{json.dumps(x, ensure_ascii=False)}</script>'
        for x in blocks
    )
    return shell(
        f"{r['product']} Review {YEAR}: {r['badge']} (Tested {r['verified']})",
        f"{r['product']} review after real testing. Score {r['score']}/10. "
        f"Pros, cons, pricing, who it's for and who should skip it.",
        content, r["url"], extra_head=head, og_image=r["image"],
    )


def build_category(cat_slug):
    name, emoji, desc = CATS[cat_slug]
    items = [r for r in REVIEWS if r["cat"] == cat_slug]
    body = f"""
<section class="hero" style="padding:44px 0 34px;text-align:left">
  <div class="wrap"><h1 style="margin:0 0 12px;max-width:none">{emoji} {html.escape(name)}</h1>
  <p style="margin:0;max-width:56ch">{html.escape(desc)}</p></div>
</section>
{AD("Leaderboard · 970×90")}
<section class="sec"><div class="wrap">
  <div class="sec-h"><h2>Reviews in {html.escape(name)}</h2><span style="color:var(--muted);font-size:14px">{len(items)} tested</span></div>
  <div class="grid">{''.join(review_card(r) for r in items)}</div>
</div></section>"""
    return shell(f"{name} Reviews {YEAR} — Tested and Rated | ZoranReviews",
                 desc, body, f"/category/{cat_slug}/")


PAGES = {
    "about": ("About", """
<h1>About 🖐️</h1>
<p>I'm Zoran Simović. I've been making a living on the internet since it stopped being
a strange thing to do — affiliate sites, email lists, landing pages, and the occasional
project that taught me what not to do.</p>
<p>This site exists because most software reviews are written by someone who opened the
product for twenty minutes and copied the feature list. I got tired of reading them, so
I'm writing the version I wanted.</p>
<h2>How reviews work here</h2>
<ul>
<li><b>I pay for the tools.</b> No sponsored placements, no free accounts in exchange for coverage.</li>
<li><b>Minimum 30 days.</b> Real tasks, not a demo tour.</li>
<li><b>Cons are mandatory.</b> Every review lists what annoyed me.</li>
<li><b>Affiliate links are disclosed</b> on every page. They pay for the hosting and never change a score.</li>
</ul>
<h2>Something wrong?</h2>
<p>If a tool has changed, broken, or you disagree with a verdict, email me —
<a href="mailto:EMAIL">EMAIL</a>. Corrections get published, not quietly edited.</p>
"""),
    "contact": ("Contact", """
<h1>Contact ✉️</h1>
<p>Email is best: <a href="mailto:EMAIL">EMAIL</a></p>
<h2>For vendors</h2>
<p>I'm happy to look at products relevant to email marketing, page building or social media.
I do not accept payment for a review, I do not publish sponsored posts disguised as reviews,
and I will not remove a criticism because someone asked.</p>
<h2>For readers</h2>
<p>Tell me what to test next. Genuine suggestions get tested more often than cold outreach.</p>
"""),
    "privacy": ("Privacy Policy", """
<h1>Privacy Policy</h1>
<p>Last updated: 2026.</p>
<h2>What this site collects</h2>
<p>No accounts, no sign-up. Server logs may record your IP, browser and pages visited.</p>
<h2>Advertising and cookies</h2>
<p>This site is supported by advertising. Third-party vendors, including Google, use cookies
to serve ads based on your prior visits to this and other websites. Google's use of advertising
cookies enables it and its partners to serve ads based on your visit to this site and other sites
on the internet.</p>
<p>You may opt out of personalised advertising at
<a href="https://www.google.com/settings/ads" rel="nofollow">Google Ads Settings</a>, or opt out
of third-party vendor cookies at <a href="https://www.aboutads.info/choices/" rel="nofollow">aboutads.info</a>.</p>
<p>Visitors in the EEA, UK and Switzerland are asked for consent before personalised advertising
cookies are set.</p>
<h2>Affiliate links</h2>
<p>Some outbound links are affiliate links. If you click one and buy, I may earn a commission at
no extra cost to you. See the <a href="/disclosure">affiliate disclosure</a>.</p>
<h2>Your rights</h2>
<p>Ask what data is held about you, request deletion, or object to processing:
<a href="mailto:EMAIL">EMAIL</a>.</p>
"""),
    "disclosure": ("Affiliate Disclosure", """
<h1>Affiliate Disclosure 💸</h1>
<p>Some links on this site are affiliate links. If you click one and buy something, I may earn a
commission. <b>The price you pay is exactly the same.</b></p>
<h2>What that does not buy</h2>
<ul>
<li>It does not buy a good score.</li>
<li>It does not buy removal of a criticism.</li>
<li>It does not buy a mention. If a product is bad, it gets a bad review or no review.</li>
</ul>
<h2>Why I use them</h2>
<p>Buying software to test it costs money. Affiliate commissions and advertising pay for that,
and for the hosting. It's the only way a site like this survives without charging readers.</p>
<h2>Which links are affiliate</h2>
<p>Links marked <code>rel="sponsored"</code> are affiliate links. Every review page also carries a
disclosure near the top, and the button in every "Check price" block says so directly.</p>
"""),
}

for k in PAGES:
    PAGES[k] = (PAGES[k][0], PAGES[k][1].replace("EMAIL", EMAIL))


def build_pages(key):
    title, inner = PAGES[key]
    content = f'<div class="narrow" style="padding:44px 0 60px"><div class="prose">{inner}</div></div>'
    return shell(f"{title} | {SITE} Reviews", f"{title} — {SITE} Reviews", content, f"/{key}")


def build_404():
    content = """<div class="narrow" style="padding:70px 0 90px;text-align:center">
<h1 style="font-size:3rem;margin:0 0 12px">404 🤷</h1>
<p style="font-size:18px;color:var(--muted);margin:0 0 26px">That page isn't here.
It may have moved during the rebuild.</p>
<a class="btn" href="/">Back to the reviews →</a></div>"""
    return shell(f"Page not found | {SITE} Reviews", "Page not found", content, "/404")


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)
    dest_images = os.path.join(OUT, "images")
    os.makedirs(dest_images, exist_ok=True)
    copied = 0
    if os.path.isdir(IMGS):
        for f in os.listdir(IMGS):
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
                shutil.copy2(os.path.join(IMGS, f), os.path.join(dest_images, f))
                copied += 1
    # images uploaded through the web UI may sit at the repo root instead
    for f in os.listdir(HERE):
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            target = os.path.join(dest_images, f)
            if not os.path.exists(target):
                shutil.copy2(os.path.join(HERE, f), target)
                copied += 1
    print(f"images copied: {copied}")

    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(build_home())

    for r in REVIEWS:
        d = os.path.join(OUT, "reviews", r["slug"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(build_review(r))

    for c in CATS:
        d = os.path.join(OUT, "category", c)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(build_category(c))

    for p in PAGES:
        open(os.path.join(OUT, p, "index.html") if False else os.path.join(OUT, p + ".html"),
             "w", encoding="utf-8").write(build_pages(p))

    open(os.path.join(OUT, "404.html"), "w", encoding="utf-8").write(build_404())

    # sitemap
    urls = ["/"] + [r["url"] for r in REVIEWS] + [f"/category/{c}/" for c in CATS] + \
           [f"/{p}" for p in PAGES]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{DOMAIN}{u}</loc><changefreq>monthly</changefreq></url>" for u in urls]
    sm.append("</urlset>")
    open(os.path.join(OUT, "sitemap.xml"), "w").write("\n".join(sm))

    open(os.path.join(OUT, "robots.txt"), "w").write(
        f"User-agent: *\nAllow: /\n\nSitemap: {DOMAIN}/sitemap.xml\n")

    open(os.path.join(OUT, "ads.txt"), "w").write(
        "# replace pub-0000000000000000 with your AdSense publisher ID\n"
        "google.com, pub-0000000000000000, DIRECT, f08c47fec0942fa0\n")

    # ---------------------------------------------------------------- redirects
    # Workers static assets rejects: duplicate routes, wildcard/? patterns beyond
    # 100 dynamic rules, and encoded characters. Emit a small, strictly valid map.
    MAX_RULES = 40
    rules, seen = [], set()

    def add(src, dest):
        if len(rules) >= MAX_RULES:
            return
        if any(c in src for c in "*?%:") or any(c in dest for c in "*?%:"):
            return                      # skip anything Cloudflare treats as dynamic
        if not src.startswith("/") or not dest.startswith("/"):
            return
        if src in seen or src == dest:
            return
        seen.add(src)
        rules.append(f"{src}  {dest}  301")

    # parking leftovers first (exact path only — no wildcards, they collide)
    add("/lander", "/")

    # then the most useful legacy URLs: those pointing at a real topic page,
    # not the generic homepage fallback
    if os.path.exists(INVENTORY):
        picked = []
        with open(INVENTORY, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                src, dest = parts[0], parts[1]
                if dest == "/":
                    continue                # homepage fallbacks are low value
                picked.append((src, dest))
        for src, dest in picked:
            add(src, dest)

    if os.path.exists(INVENTORY) and rules:
        with open(os.path.join(OUT, "_redirects"), "w") as fh:
            fh.write("# generated redirect map — exact paths only, no wildcards\n")
            fh.write("\n".join(rules) + "\n")
        print(f"redirects: {len(rules)} rules")
    else:
        print("redirects: none")

    print(f"built {len(REVIEWS)} reviews, {len(CATS)} categories, {len(PAGES)} pages -> {OUT}")


if __name__ == "__main__":
    main()
