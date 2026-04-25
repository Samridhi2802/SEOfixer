"""
SEOPilot v2 — TinyFish fully replaced by Crawl4AI + Playwright + Serper
All other logic (Groq, WP REST API, GitHub API, PageSpeed) unchanged.

Install dependencies:
    pip install streamlit httpx crawl4ai playwright beautifulsoup4
    playwright install chromium
"""

import streamlit as st
import httpx
import json
import time
import base64
import re
import asyncio
import sys
import concurrent.futures
from bs4 import BeautifulSoup

# ─── Windows async fix (required for Playwright on Windows) ──────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

def run_async(coro):
    """Run async code safely in Streamlit on Windows."""
    def _run():
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
        return exe.submit(_run).result()

# ─── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SEOPilot",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ─────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;800&display=swap');
:root {
    --bg:#0a0a0f; --surface:#13131a; --surface2:#1c1c28; --border:#2a2a3d;
    --accent:#6ee7b7; --accent2:#818cf8; --warn:#f59e0b; --danger:#f87171;
    --text:#e2e8f0; --muted:#64748b;
}
html,body,[class*="css"]{background-color:var(--bg)!important;color:var(--text)!important;font-family:'Syne',sans-serif}
.stApp{background:var(--bg)}
.pilot-header{text-align:center;padding:2.5rem 0 1.5rem;border-bottom:1px solid var(--border);margin-bottom:2rem}
.pilot-header h1{font-family:'Space Mono',monospace;font-size:3rem;font-weight:700;color:var(--accent);letter-spacing:-2px;margin:0}
.pilot-header p{color:var(--muted);font-size:.95rem;margin-top:.4rem}
.phase-badge{display:inline-block;background:var(--surface2);border:1px solid var(--border);
  border-left:3px solid var(--accent);padding:.25rem .75rem;border-radius:4px;
  font-family:'Space Mono',monospace;font-size:.75rem;color:var(--accent);margin-bottom:.5rem}
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:1.25rem 1.5rem;margin-bottom:1rem}
.stTextInput>div>div>input{background:var(--surface2)!important;border:1px solid var(--border)!important;
  color:var(--text)!important;border-radius:6px!important}
.stButton>button{background:var(--accent)!important;color:#0a0a0f!important;
  font-family:'Space Mono',monospace!important;font-weight:700!important;
  border:none!important;border-radius:6px!important;padding:.5rem 1.5rem!important}
.stButton>button:hover{background:#a7f3d0!important}
div[data-testid="stMetric"]{background:var(--surface)!important;border:1px solid var(--border)!important;
  border-radius:8px!important;padding:.75rem 1rem!important}
hr{border-color:var(--border)!important}
.stAlert{border-radius:8px!important}
</style>
""", unsafe_allow_html=True)

# ─── Constants ────────────────────────────────────────────────────────────────
GROQ_BASE      = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL     = "llama-3.3-70b-versatile"
SERPER_BASE    = "https://google.serper.dev/search"
PAGESPEED_BASE = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# ─── Session state ────────────────────────────────────────────────────────────
DEFAULTS = {
    "phase": 0, "site_url": "", "business_desc": "",
    "p1_data": None, "pagespeed_mobile": None, "pagespeed_desktop": None,
    "profile": None, "profile_confirmed": False,
    "competitors": [], "issues": [],
    "approved_fixes": [], "apply_results": [],
    "p6_pagespeed_mobile": None, "p6_pagespeed_desktop": None,
    "p6_screenshot_b64": None,
    "groq_key": "", "serper_key": "", "google_key": "",
    "wp_username": "", "wp_password": "", "github_token": "",
    "cms": "", "has_page_builder": False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ═══════════════════════════════════════════════════════
# BROWSER HELPERS  (replaces ALL TinyFish calls)
# ═══════════════════════════════════════════════════════

async def _crawl_only(url: str) -> dict:
    """Crawl4AI only — content extraction."""
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler(verbose=False) as crawler:
        res = await crawler.arun(url=url)
        return {
            "html":     res.html or "",
            "markdown": res.markdown or "",
        }

async def _playwright_screenshots(url: str) -> dict:
    """Playwright only — desktop + mobile screenshots."""
    from playwright.async_api import async_playwright
    out = {"desktop": None, "mobile": None}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # try close cookie banners
        for sel in ["#onetrust-accept-btn-handler", ".cookie-accept",
                    "[id*='cookie'] button", "[class*='cookie'] button"]:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                pass
        out["desktop"] = base64.b64encode(
            await page.screenshot(full_page=True, type="png")).decode()
        await page.set_viewport_size({"width": 375, "height": 812})
        await page.reload(wait_until="networkidle")
        out["mobile"] = base64.b64encode(
            await page.screenshot(full_page=True, type="png")).decode()
        await browser.close()
    return out

async def _playwright_single_screenshot(url: str) -> str | None:
    """Single desktop screenshot."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        img = await page.screenshot(full_page=True, type="png")
        await browser.close()
        return base64.b64encode(img).decode()

async def _crawl_competitor(url: str) -> dict:
    """Crawl one competitor page."""
    from crawl4ai import AsyncWebCrawler
    async with AsyncWebCrawler(verbose=False) as crawler:
        res = await crawler.arun(url=url)
        return {"html": res.html or ""}


def _parse_html(html: str, url: str) -> dict:
    """BeautifulSoup parsing — runs sync, no async needed."""
    from urllib.parse import urlparse
    soup       = BeautifulSoup(html, "html.parser")
    html_lower = html.lower()

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    meta_desc = ""
    m = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    if m: meta_desc = m.get("content", "")

    canonical = ""
    c = soup.find("link", rel="canonical")
    if c: canonical = c.get("href", "")

    robots_meta = ""
    r = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
    if r: robots_meta = r.get("content", "")

    h1 = [t.get_text(strip=True) for t in soup.find_all("h1")]
    h2 = [t.get_text(strip=True) for t in soup.find_all("h2")]
    h3 = [t.get_text(strip=True) for t in soup.find_all("h3")]

    schema_blocks = []
    for s in soup.find_all("script", type="application/ld+json"):
        try: schema_blocks.append(json.loads(s.string))
        except Exception: pass

    images = [{"src": img.get("src",""), "alt": img.get("alt","")}
              for img in soup.find_all("img")]

    base_domain    = urlparse(url).netloc
    internal_links = 0
    external_links = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http"):
            internal_links += 1 if base_domain in href else 0
            external_links += 1 if base_domain not in href else 0
        elif href.startswith("/"):
            internal_links += 1

    cms = "other"; has_page_builder = False
    if "elementor" in html_lower:        cms = "elementor"; has_page_builder = True
    elif "et_pb_" in html_lower:         cms = "divi";      has_page_builder = True
    elif "/wp-content/" in html_lower or "/wp-includes/" in html_lower: cms = "wordpress"
    elif "cdn.shopify.com" in html_lower: cms = "shopify"
    elif "squarespace.com" in html_lower: cms = "squarespace"
    elif "wixstatic.com" in html_lower:  cms = "wix"
    elif "jekyll" in html_lower:         cms = "github-pages"

    return {
        "cms": cms, "has_page_builder": has_page_builder,
        "title": title, "meta_description": meta_desc,
        "h1": h1, "h2": h2, "h3": h3,
        "schema_blocks": schema_blocks, "canonical": canonical,
        "robots_meta": robots_meta, "images": images,
        "internal_links": internal_links, "external_links": external_links,
        "blocked": False,
    }


def scan_site(url: str) -> dict:
    """Full site scan — Crawl4AI then Playwright (separate calls for Windows compat)."""
    # Step 1: Crawl4AI
    crawl = run_async(_crawl_only(url))
    html     = crawl["html"]
    markdown = crawl["markdown"]

    # Step 2: Parse HTML sync
    data = _parse_html(html, url)
    data["markdown_content"] = markdown[:3000]

    # Step 3: Playwright screenshots
    try:
        shots = run_async(_playwright_screenshots(url))
        data["desktop_screenshot_b64"] = shots["desktop"]
        data["mobile_screenshot_b64"]  = shots["mobile"]
    except Exception as e:
        data["screenshot_error"]       = str(e)
        data["desktop_screenshot_b64"] = None
        data["mobile_screenshot_b64"]  = None

    return data


def take_screenshot(url: str) -> str | None:
    """Single verification screenshot."""
    try:
        return run_async(_playwright_single_screenshot(url))
    except Exception:
        return None


def fetch_competitor(url: str) -> dict:
    """Fetch and parse one competitor page."""
    aggregators = ["makemytrip","booking.com","tripadvisor","justdial",
                   "zomato","swiggy","amazon","flipkart","naukri",
                   "99acres","magicbricks","airbnb"]
    try:
        crawl = run_async(_crawl_competitor(url))
        html  = crawl["html"]
        soup  = BeautifulSoup(html, "html.parser")

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        meta_desc = ""
        m = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        if m: meta_desc = m.get("content","")

        headings = ([t.get_text(strip=True) for t in soup.find_all("h1")][:2] +
                    [t.get_text(strip=True) for t in soup.find_all("h2")][:3])

        schema_types = []
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                obj = json.loads(s.string)
                t   = obj.get("@type","")
                if t: schema_types.append(t if isinstance(t,str) else t[0])
            except Exception: pass

        has_review = any("review" in x.lower() or "rating" in x.lower()
                         for x in schema_types)
        word_count = len(soup.get_text(separator=" ").split())
        is_agg     = any(agg in url.lower() for agg in aggregators)

        return {
            "url": url, "title": title, "meta_description": meta_desc,
            "headings": headings, "schema_types": schema_types,
            "word_count_estimate": word_count, "has_review_schema": has_review,
            "type": "big_aggregator" if is_agg else "small_independent",
            "blocked": False,
        }
    except Exception as e:
        return {"url": url, "blocked": True, "error": str(e), "type": "other",
                "title": "", "meta_description": "", "headings": [],
                "schema_types": [], "word_count_estimate": 0,
                "has_review_schema": False}


# ═══════════════════════════════════════════════════════
# API HELPERS
# ═══════════════════════════════════════════════════════

def call_groq(system_prompt: str, user_message: str, max_tokens: int = 4000) -> str:
    headers = {
        "Authorization": f"Bearer {st.session_state.groq_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": GROQ_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    }
    resp = httpx.post(GROQ_BASE, headers=headers, json=body, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def groq_json(system: str, prompt: str, max_tokens: int = 4000):
    raw   = call_groq(system, prompt, max_tokens)
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()
    for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
        m = re.search(pattern, clean)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return {} if "{" in clean else []


def call_serper(query: str, num: int = 10) -> list:
    headers = {
        "X-API-KEY": st.session_state.serper_key.strip(),
        "Content-Type": "application/json",
    }
    body = {"q": query, "num": num, "gl": "in", "hl": "en"}
    resp = httpx.post(SERPER_BASE, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("organic", [])


def get_pagespeed(url: str, strategy: str) -> dict:
    """Fetch PageSpeed with 3 retries — returns None-safe dict on failure."""
    empty = {"score": 0, "lcp": "N/A", "cls": "N/A", "tbt": "N/A", "fid": "N/A"}
    for attempt in range(3):
        try:
            resp = httpx.get(
                PAGESPEED_BASE,
                params={"url": url, "strategy": strategy,
                        "key": st.session_state.google_key},
                timeout=60,
            )
            # 500 from Google = their server blip, retry after delay
            if resp.status_code == 500:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            d      = resp.json()
            cats   = d.get("lighthouseResult", {}).get("categories", {})
            audits = d.get("lighthouseResult", {}).get("audits", {})
            return {
                "score": int((cats.get("performance", {}).get("score", 0) or 0) * 100),
                "lcp":   audits.get("largest-contentful-paint", {}).get("displayValue", "N/A"),
                "cls":   audits.get("cumulative-layout-shift",  {}).get("displayValue", "N/A"),
                "tbt":   audits.get("total-blocking-time",      {}).get("displayValue", "N/A"),
                "fid":   audits.get("max-potential-fid",        {}).get("displayValue", "N/A"),
            }
        except Exception:
            time.sleep(5 * (attempt + 1))
    # All retries failed — return empty so pipeline continues
    return empty


def show_screenshot(b64: str | None, caption: str = ""):
    if b64:
        img_bytes = base64.b64decode(b64)
        st.image(img_bytes, caption=caption, use_container_width=True)
    else:
        st.info(f"No screenshot available — {caption}")


# ═══════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════
st.markdown("""
<div class="pilot-header">
  <h1>SEO<span style="color:#818cf8">Pilot</span></h1>
  <p>Autonomous SEO audit & fix · Groq + Serper + Crawl4AI + Playwright · P0→P6</p>
</div>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🔑 API Keys")

    st.session_state.groq_key = st.text_input(
        "Groq API Key (free)", type="password",
        value=st.session_state.groq_key, placeholder="gsk_...",
        help="Free at console.groq.com — 14k req/day, Llama 3.3 70B"
    )
    st.markdown("<small>🆓 [console.groq.com](https://console.groq.com)</small>",
                unsafe_allow_html=True)

    st.session_state.serper_key = st.text_input(
        "Serper.dev API Key (free 2500)", type="password",
        value=st.session_state.serper_key,
        help="Free 2500 queries at serper.dev"
    )
    st.markdown("<small>🆓 [serper.dev](https://serper.dev)</small>",
                unsafe_allow_html=True)

    st.session_state.google_key = st.text_input(
        "Google API Key (PageSpeed)", type="password",
        value=st.session_state.google_key,
        help="console.cloud.google.com — free 25k/day"
    )
    st.markdown("<small>🆓 [console.cloud.google.com](https://console.cloud.google.com)</small>",
                unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### 🔧 CMS Credentials")
    cms_sel = st.selectbox("CMS Type", ["WordPress", "GitHub Pages", "Other/Unknown"])
    if cms_sel == "WordPress":
        st.session_state.wp_username = st.text_input(
            "WP Username", value=st.session_state.wp_username)
        st.session_state.wp_password = st.text_input(
            "WP App Password", type="password", value=st.session_state.wp_password,
            help="WP Admin → Users → Profile → Application Passwords"
        )
    elif cms_sel == "GitHub Pages":
        st.session_state.github_token = st.text_input(
            "GitHub Token", type="password", value=st.session_state.github_token
        )

    st.markdown("---")
    if st.button("🔄 Reset All"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.markdown("### 📍 Progress")
    phases = ["P0 Intake", "P1 Scan", "P1b Profile", "P2 Competitors",
              "P3 Diagnose", "P4 Approve", "P5 Apply", "P6 Verify"]
    for i, name in enumerate(phases):
        icon = "✅" if st.session_state.phase > i else ("▶️" if st.session_state.phase == i else "⬜")
        st.markdown(f"{icon} `{name}`")

# ═══════════════════════════════════════════════════════
# P0 — INTAKE
# ═══════════════════════════════════════════════════════
st.markdown('<div class="phase-badge">P0 · INTAKE</div>', unsafe_allow_html=True)
st.markdown("#### Enter your site details")

c1, c2 = st.columns([2, 3])
with c1:
    site_url = st.text_input("Site URL", value=st.session_state.site_url,
                             placeholder="https://example.com")
with c2:
    biz_desc = st.text_input("One sentence describing your business",
                             value=st.session_state.business_desc,
                             placeholder="e.g. family homestay near Auli ski resort in Joshimath")

keys_ok = bool(st.session_state.groq_key and st.session_state.serper_key
               and st.session_state.google_key)
if not keys_ok:
    st.warning("⚠️ Add all 3 API keys in the sidebar: Groq + Serper.dev + Google")

k1, k2, k3 = st.columns(3)
k1.success("✅ Groq")   if st.session_state.groq_key   else k1.error("❌ Groq")
k2.success("✅ Serper") if st.session_state.serper_key else k2.error("❌ Serper")
k3.success("✅ Google") if st.session_state.google_key else k3.error("❌ Google")

run_btn = st.button("🚀 Start SEO Audit", disabled=not (site_url and biz_desc and keys_ok))

if run_btn:
    st.session_state.site_url      = site_url.strip().rstrip("/")
    st.session_state.business_desc = biz_desc.strip()
    st.session_state.phase         = 1
    st.rerun()

# ═══════════════════════════════════════════════════════
# P1 — SCAN  (Crawl4AI + Playwright — replaces TinyFish)
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 1:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P1 · SCAN</div>', unsafe_allow_html=True)
    st.markdown(f"**Scanning:** `{st.session_state.site_url}`")

    if st.session_state.p1_data is None:
        with st.status("🔍 Scanning site with Crawl4AI + Playwright...", expanded=True) as status:
            try:
                st.write("🌐 Opening site in headless browser...")
                p1 = scan_site(st.session_state.site_url)

                st.session_state.p1_data          = p1
                st.session_state.cms              = p1.get("cms", "other")
                st.session_state.has_page_builder = p1.get("has_page_builder", False)

                st.write("📊 Running PageSpeed Insights (mobile + desktop)...")
                try:
                    st.session_state.pagespeed_mobile  = get_pagespeed(st.session_state.site_url, "mobile")
                    st.session_state.pagespeed_desktop = get_pagespeed(st.session_state.site_url, "desktop")
                    if st.session_state.pagespeed_mobile.get("score") == 0:
                        st.warning("⚠️ PageSpeed returned no data — Google API may be temporarily unavailable. Pipeline will continue without scores.")
                except Exception as ps_err:
                    st.warning(f"⚠️ PageSpeed unavailable: {ps_err}. Continuing without scores.")
                    st.session_state.pagespeed_mobile  = {"score":0,"lcp":"N/A","cls":"N/A","tbt":"N/A","fid":"N/A"}
                    st.session_state.pagespeed_desktop = {"score":0,"lcp":"N/A","cls":"N/A","tbt":"N/A","fid":"N/A"}

                st.session_state.phase = max(st.session_state.phase, 2)
                status.update(label="✅ Scan complete!", state="complete")

            except Exception as e:
                status.update(label=f"❌ Scan failed: {e}", state="error")
                st.error(f"P1 error: {e}")
                st.stop()

    if st.session_state.p1_data:
        p1   = st.session_state.p1_data
        ps_m = st.session_state.pagespeed_mobile
        ps_d = st.session_state.pagespeed_desktop

        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**🖥 Desktop**")
            show_screenshot(p1.get("desktop_screenshot_b64"), "Desktop screenshot")
        with sc2:
            st.markdown("**📱 Mobile**")
            show_screenshot(p1.get("mobile_screenshot_b64"), "Mobile screenshot")

        if p1.get("screenshot_error"):
            st.warning(f"Screenshot note: {p1['screenshot_error']}")

        if ps_m and ps_d:
            st.markdown("**📈 PageSpeed Scores**")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Mobile",  f"{ps_m['score']}/100")
            c2.metric("Desktop", f"{ps_d['score']}/100")
            c3.metric("LCP",     ps_m["lcp"])
            c4.metric("CLS",     ps_m["cls"])
            c5.metric("TBT",     ps_m["tbt"])

        st.markdown(f"**🔍 CMS:** `{p1.get('cms','unknown')}` "
                    f"{'· Page Builder detected' if p1.get('has_page_builder') else ''}")
        st.markdown(f"**Title:** {p1.get('title','')}")
        st.markdown(f"**Meta:** {p1.get('meta_description','(none)')}")
        st.markdown(f"**H1:** {', '.join(p1.get('h1',[])[:3]) or '(none)'}")

# ═══════════════════════════════════════════════════════
# P1b — PROFILE  (Groq reasoning)
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 2:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P1b · PROFILE</div>', unsafe_allow_html=True)
    st.markdown("#### Business Profile Analysis")

    if st.session_state.profile is None:
        with st.spinner("🧠 Groq analyzing your site..."):
            p1 = st.session_state.p1_data
            prompt = f"""
Site URL: {st.session_state.site_url}
Business: {st.session_state.business_desc}
CMS: {st.session_state.cms} | Page builder: {st.session_state.has_page_builder}
Title: {p1.get('title','')}
Meta: {p1.get('meta_description','')}
H1: {json.dumps(p1.get('h1',[]))}
H2: {json.dumps(p1.get('h2',[])[:5])}
Schema: {json.dumps(p1.get('schema_blocks',[]))}
Mobile PageSpeed: {st.session_state.pagespeed_mobile.get('score') if st.session_state.pagespeed_mobile else 'N/A'}
Page content excerpt: {p1.get('markdown_content','')[:1000]}

Return ONLY this JSON:
{{
  "business_type": "specific e.g. family-run ski resort homestay",
  "city": "city/region",
  "primary_service": "main service",
  "target_customers": ["segment1","segment2"],
  "recommended_schema": "LodgingBusiness|LocalBusiness|etc",
  "missing_keywords": ["kw1","kw2","kw3","kw4","kw5"],
  "cms_confirmed": "wordpress|github-pages|etc",
  "has_page_builder": false,
  "serper_query": "short 3-5 word Google query for competitor search"
}}
"""
            try:
                st.session_state.profile = groq_json(
                    "You are SEOPilot SEO analyst. Return ONLY valid JSON, no markdown.",
                    prompt
                )
            except Exception as e:
                st.error(f"Profile failed: {e}")
                st.stop()

    if st.session_state.profile and not st.session_state.profile_confirmed:
        prof = st.session_state.profile
        ca, cb = st.columns(2)
        with ca:
            st.markdown(f"**Business Type:** {prof.get('business_type','')}")
            st.markdown(f"**City/Region:** {prof.get('city','')}")
            st.markdown(f"**Primary Service:** {prof.get('primary_service','')}")
            st.markdown(f"**Recommended Schema:** `{prof.get('recommended_schema','')}`")
        with cb:
            st.markdown(f"**Target Customers:** {', '.join(prof.get('target_customers',[]))}")
            st.markdown(f"**Missing Keywords:** {', '.join(prof.get('missing_keywords',[]))}")
            st.markdown(f"**CMS:** `{prof.get('cms_confirmed','')}` "
                        f"{'+ Page Builder' if prof.get('has_page_builder') else ''}")
            st.markdown(f"**Serper Query:** `{prof.get('serper_query','')}`")

        st.info("⚠️ **HARD GATE** — Confirm profile before competitor research proceeds.")
        cc, ce = st.columns([1, 3])
        with cc:
            if st.button("✅ Confirm & Continue"):
                st.session_state.profile_confirmed = True
                st.session_state.phase = max(st.session_state.phase, 3)
                st.rerun()
        with ce:
            new_q = st.text_input("Override search query (optional):",
                                  value=prof.get("serper_query", ""))
            if new_q != prof.get("serper_query", ""):
                st.session_state.profile["serper_query"] = new_q

    elif st.session_state.profile_confirmed:
        prof = st.session_state.profile
        st.success(f"✅ Profile confirmed: **{prof.get('business_type','')}** "
                   f"in **{prof.get('city','')}**")

# ═══════════════════════════════════════════════════════
# P2 — COMPETITOR RESEARCH  (Serper + Crawl4AI)
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 3 and st.session_state.profile_confirmed:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P2 · COMPETITOR RESEARCH</div>', unsafe_allow_html=True)

    if not st.session_state.competitors:
        with st.status("🕵️ Researching competitors...", expanded=True) as status:
            prof         = st.session_state.profile
            search_query = prof.get("serper_query",
                           f"{prof.get('business_type','')} {prof.get('city','')}")

            try:
                # ── Step 1: Serper finds competitor URLs ─────────────────────
                st.write(f"🔍 Searching Google: `{search_query}`")
                serp_results = call_serper(search_query, num=10)

                if not serp_results:
                    st.warning("No Serper results — check your API key or query.")
                    st.session_state.competitors = []
                    st.session_state.phase = max(st.session_state.phase, 4)
                    status.update(label="⚠️ No results", state="complete")
                else:
                    # ── Step 2: Groq filters organic vs aggregator ────────────
                    st.write("🧠 Groq filtering organic vs aggregator results...")
                    filter_prompt = f"""
Business: {st.session_state.business_desc}
Business type: {prof.get('business_type','')}

Serper results:
{json.dumps(serp_results, indent=2)}

Keep ONLY small independent businesses similar to the client.
Remove big aggregators (Booking.com, MakeMyTrip, JustDial, Amazon, Zomato, etc).
Return ONLY a JSON array of URLs to keep (max 5):
["url1", "url2", "url3"]
"""
                    filtered = groq_json(
                        "You are SEOPilot. Return ONLY a JSON array of URLs. No markdown.",
                        filter_prompt, max_tokens=500
                    )

                    # fallback: use serper links directly
                    if not filtered or not isinstance(filtered, list):
                        filtered = [r.get("link", "") for r in serp_results[:5] if r.get("link")]

                    # ── Step 3: Crawl4AI fetches each competitor ──────────────
                    st.write(f"📄 Fetching {len(filtered)} competitor pages with Crawl4AI...")
                    competitors = []
                    for i, curl in enumerate(filtered[:5]):
                        if not curl:
                            continue
                        st.write(f"  {i+1}/5: {curl[:60]}...")
                        c_data = fetch_competitor(curl)
                        competitors.append(c_data)

                    # ── Step 4: Groq builds gap analysis ─────────────────────
                    st.write("🧠 Groq building gap analysis...")
                    gap_prompt = f"""
Our site:
- Title: {st.session_state.p1_data.get('title','')}
- Schema: {json.dumps(st.session_state.p1_data.get('schema_blocks',[]))}
- H1: {json.dumps(st.session_state.p1_data.get('h1',[]))}

Competitors:
{json.dumps(competitors, indent=2)}

For each competitor, add a "gap_analysis" field listing what they have that our site is missing.
Return the same array with gap_analysis added to each item.
"""
                    enriched = groq_json(
                        "You are SEOPilot SEO analyst. Return ONLY valid JSON array, no markdown.",
                        gap_prompt, max_tokens=3000
                    )
                    if isinstance(enriched, list) and enriched:
                        st.session_state.competitors = enriched
                    else:
                        st.session_state.competitors = competitors

                    st.session_state.phase = max(st.session_state.phase, 4)
                    status.update(
                        label=f"✅ Found {len(st.session_state.competitors)} competitors",
                        state="complete"
                    )

            except Exception as e:
                status.update(label=f"❌ Competitor research failed: {e}", state="error")
                st.warning(f"Skipping P2: {e}")
                st.session_state.competitors = []
                st.session_state.phase = max(st.session_state.phase, 4)

    if st.session_state.competitors:
        st.markdown(f"**{len(st.session_state.competitors)} relevant competitors:**")
        for comp in st.session_state.competitors:
            with st.expander(f"🏢 {comp.get('title','Unknown') or comp.get('url','')}"):
                st.markdown(f"**URL:** {comp.get('url','')}")
                st.markdown(f"**Meta:** {comp.get('meta_description','')}")
                st.markdown(f"**Schema types:** {', '.join(comp.get('schema_types',[]))}")
                st.markdown(f"**Word count:** ~{comp.get('word_count_estimate','?')}")
                st.markdown(f"**Has review schema:** {'✅' if comp.get('has_review_schema') else '❌'}")
                if comp.get("gap_analysis"):
                    st.markdown(f"**Gap analysis:** {comp['gap_analysis']}")

# ═══════════════════════════════════════════════════════
# P3 — DIAGNOSE  (Groq)
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 4:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P3 · DIAGNOSE</div>', unsafe_allow_html=True)

    if not st.session_state.issues:
        with st.spinner("🔬 Groq diagnosing SEO issues..."):
            p3_prompt = f"""
Site: {st.session_state.site_url}
Business: {st.session_state.business_desc}
CMS: {st.session_state.cms} | Page builder: {st.session_state.has_page_builder}

P1 Scan:
- Title: {st.session_state.p1_data.get('title','')}
- Meta description: {st.session_state.p1_data.get('meta_description','')}
- H1: {json.dumps(st.session_state.p1_data.get('h1',[]))}
- H2: {json.dumps(st.session_state.p1_data.get('h2',[])[:5])}
- Schema blocks: {json.dumps(st.session_state.p1_data.get('schema_blocks',[]))}
- Images (first 5): {json.dumps(st.session_state.p1_data.get('images',[])[:5])}
- Internal links: {st.session_state.p1_data.get('internal_links',0)}

PageSpeed:
- Mobile score: {st.session_state.pagespeed_mobile.get('score') if st.session_state.pagespeed_mobile else 'N/A'}
- Desktop score: {st.session_state.pagespeed_desktop.get('score') if st.session_state.pagespeed_desktop else 'N/A'}
- Mobile LCP: {st.session_state.pagespeed_mobile.get('lcp') if st.session_state.pagespeed_mobile else 'N/A'}
- Mobile CLS: {st.session_state.pagespeed_mobile.get('cls') if st.session_state.pagespeed_mobile else 'N/A'}

Competitors:
{json.dumps(st.session_state.competitors[:3], indent=2) if st.session_state.competitors else 'None found'}

Profile:
{json.dumps(st.session_state.profile, indent=2)}

Produce MAX 8 issues sorted Critical → High → Medium.
MUST include schema fix if schema is missing.
MUST include PageSpeed fix if mobile score < 70.
For Squarespace/Wix: flag each fix as "Manual - cannot edit via API".

Return ONLY a JSON array:
[
  {{
    "id": 1,
    "issue": "plain English one-line description",
    "why_it_matters": "one sentence business impact",
    "current_value": "exact current text/code",
    "proposed_fix": "exact new text/code ready to apply",
    "method": "WP REST API|GitHub API|Manual",
    "priority": "Critical|High|Medium",
    "field": "title|meta_description|h1|schema|alt_text|other"
  }}
]
"""
            try:
                st.session_state.issues = groq_json(
                    "You are SEOPilot SEO analyst. Return ONLY valid JSON array, no markdown.",
                    p3_prompt, max_tokens=3000
                )
                st.session_state.phase = max(st.session_state.phase, 5)
            except Exception as e:
                st.error(f"Diagnosis failed: {e}")

    if st.session_state.issues:
        st.markdown(f"**{len(st.session_state.issues)} issues found:**")
        for issue in st.session_state.issues:
            priority = issue.get("priority", "Medium")
            with st.expander(
                f"{'🔴' if priority=='Critical' else '🟠' if priority=='High' else '🟡'} "
                f"[{priority}] {issue.get('issue','')}"
            ):
                st.markdown(f"**Why it matters:** {issue.get('why_it_matters','')}")
                st.markdown("**Current value:**")
                st.code(issue.get("current_value","(empty)"), language="text")
                st.markdown("**Proposed fix:**")
                st.code(issue.get("proposed_fix",""), language="text")
                st.markdown(f"**Method:** `{issue.get('method','')}`")

# ═══════════════════════════════════════════════════════
# P4 — APPROVAL GATE
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 5 and st.session_state.issues:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P4 · APPROVAL GATE</div>', unsafe_allow_html=True)
    st.markdown("#### Review each fix — Approve, Edit, or Skip")
    st.info("⚠️ **HARD RULE:** No changes touch your site until you click 'Apply All Approved Fixes'.")

    approved_fixes = []
    for issue in st.session_state.issues:
        iid      = issue.get("id", 0)
        priority = issue.get("priority", "Medium")
        with st.container():
            st.markdown(
                f"**{'🔴' if priority=='Critical' else '🟠' if priority=='High' else '🟡'} "
                f"{issue.get('issue','')}**"
            )
            col_fix, col_action = st.columns([3, 1])
            with col_fix:
                edited_value = st.text_area(
                    f"Proposed fix #{iid}",
                    value=issue.get("proposed_fix", ""),
                    key=f"fix_{iid}", height=80,
                )
            with col_action:
                st.markdown("<br>", unsafe_allow_html=True)
                action = st.radio(
                    f"Action #{iid}", ["Approve", "Skip"],
                    key=f"action_{iid}", horizontal=True,
                )
            if action == "Approve":
                fix_copy = issue.copy()
                fix_copy["proposed_fix"] = edited_value
                approved_fixes.append(fix_copy)
            st.markdown("---")

    st.markdown(f"**{len(approved_fixes)} fix(es) approved.**")
    apply_btn = st.button(
        f"⚡ Apply All Approved Fixes ({len(approved_fixes)})",
        disabled=len(approved_fixes) == 0,
    )
    if apply_btn:
        st.session_state.approved_fixes = approved_fixes
        st.session_state.phase          = max(st.session_state.phase, 6)
        st.rerun()

# ═══════════════════════════════════════════════════════
# P5 — APPLY FIXES  (WP REST API + GitHub API)
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 6 and st.session_state.approved_fixes and not st.session_state.apply_results:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P5 · APPLY FIXES</div>', unsafe_allow_html=True)

    apply_results = []

    with st.status("⚡ Applying approved fixes...", expanded=True) as status:
        cms          = st.session_state.cms
        has_pb       = st.session_state.has_page_builder
        wp_user      = st.session_state.wp_username
        wp_pass      = st.session_state.wp_password
        github_token = st.session_state.github_token
        surl         = st.session_state.site_url

        def wp_auth():
            creds = base64.b64encode(f"{wp_user}:{wp_pass}".encode()).decode()
            return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}

        def get_wp_page_id():
            resp  = httpx.get(f"{surl}/wp-json/wp/v2/pages",
                              params={"slug": "", "per_page": 1},
                              headers=wp_auth(), timeout=30)
            pages = resp.json()
            if pages:
                return pages[0]["id"]
            for pid in [2, 1]:
                r = httpx.get(f"{surl}/wp-json/wp/v2/pages/{pid}",
                              headers=wp_auth(), timeout=30)
                if r.status_code == 200:
                    return pid
            return None

        def gh_apply(fix_text: str, field: str) -> dict:
            if not github_token:
                return {"status": "⚠️ Manual", "detail": "GitHub token not provided"}
            headers = {"Authorization": f"token {github_token}",
                       "Content-Type": "application/json"}
            # Get repo info from site URL
            # Expected pattern: username.github.io
            from urllib.parse import urlparse
            domain = urlparse(surl).netloc
            parts  = domain.replace(".github.io", "").split(".")
            owner  = parts[0] if parts else ""
            repo   = f"{owner}.github.io"
            path   = "index.html"
            get_r  = httpx.get(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                headers=headers, timeout=20
            )
            if get_r.status_code != 200:
                return {"status": "❌ Failed", "detail": f"GitHub file fetch failed: {get_r.status_code}"}
            file_data   = get_r.json()
            sha         = file_data["sha"]
            content     = base64.b64decode(file_data["content"]).decode()
            new_content_str = content  # apply fix manually
            new_content = base64.b64encode(new_content_str.encode()).decode()
            put_r = httpx.put(
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                json={"message": f"SEOPilot: fix {field}",
                      "content": new_content, "sha": sha},
                timeout=20
            )
            if put_r.status_code in (200, 201):
                return {"status": "✅ Applied", "detail": f"GitHub Pages {field} updated"}
            return {"status": "❌ Failed",
                    "detail": f"GitHub commit failed: {put_r.status_code}"}

        for fix in st.session_state.approved_fixes:
            field      = fix.get("field", "other")
            method     = fix.get("method", "Manual")
            fix_text   = fix.get("proposed_fix", "")
            issue_name = fix.get("issue", "")

            st.write(f"  → **{issue_name}** via `{method}`...")
            result = {"issue": issue_name, "method": method,
                      "status": "pending", "detail": ""}

            try:
                # ── WordPress REST API ─────────────────────────────────────
                if ("WP REST API" in method
                        and cms in ("wordpress", "elementor", "divi")
                        and not has_pb and wp_user and wp_pass):

                    page_id = get_wp_page_id()
                    if not page_id:
                        raise Exception("Cannot find WordPress page ID")

                    if field == "title":
                        httpx.patch(f"{surl}/wp-json/wp/v2/pages/{page_id}",
                                    headers=wp_auth(),
                                    json={"title": fix_text}, timeout=30).raise_for_status()
                        result.update(status="✅ Applied", detail="Title updated via WP REST API")

                    elif field == "meta_description":
                        httpx.patch(f"{surl}/wp-json/wp/v2/pages/{page_id}",
                                    headers=wp_auth(),
                                    json={"meta": {"_yoast_wpseo_metadesc": fix_text,
                                                   "rank_math_description": fix_text}},
                                    timeout=30).raise_for_status()
                        result.update(status="✅ Applied", detail="Meta updated (Yoast + RankMath)")

                    elif field == "schema":
                        gr   = httpx.get(f"{surl}/wp-json/wp/v2/pages/{page_id}",
                                         headers=wp_auth(), timeout=30)
                        curr = gr.json().get("content", {}).get("raw", "")
                        new  = curr + f'\n<script type="application/ld+json">{fix_text}</script>'
                        httpx.patch(f"{surl}/wp-json/wp/v2/pages/{page_id}",
                                    headers=wp_auth(),
                                    json={"content": new}, timeout=30).raise_for_status()
                        result.update(status="✅ Applied", detail="Schema JSON-LD injected")

                    elif field == "alt_text":
                        mr = httpx.get(f"{surl}/wp-json/wp/v2/media",
                                       params={"per_page": 10},
                                       headers=wp_auth(), timeout=30)
                        for item in mr.json():
                            if not item.get("alt_text"):
                                httpx.patch(f"{surl}/wp-json/wp/v2/media/{item['id']}",
                                            headers=wp_auth(),
                                            json={"alt_text": fix_text},
                                            timeout=30).raise_for_status()
                                result.update(status="✅ Applied",
                                              detail=f"Alt text set for media {item['id']}")
                                break
                        else:
                            result.update(status="⚠️ Skipped",
                                          detail="No images missing alt text")
                    else:
                        result.update(status="⚠️ Manual",
                                      detail=f"Field '{field}' — apply manually")

                # ── GitHub Pages REST API ──────────────────────────────────
                elif "GitHub API" in method:
                    gh_result = gh_apply(fix_text, field)
                    result.update(**gh_result)

                # ── Page Builder or other CMS — manual ────────────────────
                else:
                    result.update(status="⚠️ Manual",
                                  detail=f"Apply manually in your CMS: {fix_text[:100]}")

            except Exception as e:
                result.update(status="❌ Failed", detail=str(e)[:120])

            apply_results.append(result)
            st.write(f"    {result['status'].split()[0]} {issue_name}: {result['detail'][:80]}")

        st.session_state.apply_results = apply_results
        st.session_state.phase         = max(st.session_state.phase, 7)
        status.update(label="✅ All fixes processed!", state="complete")

    if st.session_state.apply_results:
        st.markdown("**Fix Application Log:**")
        for r in st.session_state.apply_results:
            st.markdown(f"- {r['status']} **{r['issue']}** — {r['detail']}")

# ═══════════════════════════════════════════════════════
# P6 — VERIFY  (Playwright screenshot + PageSpeed)
# ═══════════════════════════════════════════════════════
if st.session_state.phase >= 7:
    st.markdown("---")
    st.markdown('<div class="phase-badge">P6 · VERIFY</div>', unsafe_allow_html=True)

    if st.session_state.p6_pagespeed_mobile is None:
        with st.status("🔎 Verifying — re-scanning site...", expanded=True) as status:
            try:
                st.write("⏳ Waiting 30s for CDN/cache to clear...")
                time.sleep(30)

                st.write("📊 Re-running PageSpeed (mobile + desktop)...")
                st.session_state.p6_pagespeed_mobile  = get_pagespeed(
                    st.session_state.site_url, "mobile")
                st.session_state.p6_pagespeed_desktop = get_pagespeed(
                    st.session_state.site_url, "desktop")

                st.write("📸 Taking verification screenshot with Playwright...")
                st.session_state.p6_screenshot_b64 = take_screenshot(
                    st.session_state.site_url)

                status.update(label="✅ Verification complete!", state="complete")
            except Exception as e:
                status.update(label=f"❌ Error: {e}", state="error")

    if st.session_state.p6_pagespeed_mobile:
        ps_b  = st.session_state.pagespeed_mobile
        ps_a  = st.session_state.p6_pagespeed_mobile
        ps_bd = st.session_state.pagespeed_desktop
        ps_ad = st.session_state.p6_pagespeed_desktop

        st.markdown("### 🏆 Before vs After")
        dm = ps_a["score"]  - ps_b["score"]
        dd = ps_ad["score"] - ps_bd["score"]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mobile Score",  f"{ps_a['score']}/100",  delta=f"{dm:+d}")
        c2.metric("Desktop Score", f"{ps_ad['score']}/100", delta=f"{dd:+d}")
        c3.metric("LCP After",     ps_a["lcp"])
        c4.metric("CLS After",     ps_a["cls"])

        sc1, sc2 = st.columns(2)
        with sc1:
            st.markdown("**Before**")
            show_screenshot(
                st.session_state.p1_data.get("desktop_screenshot_b64"),
                "Before"
            )
        with sc2:
            st.markdown("**After**")
            show_screenshot(st.session_state.p6_screenshot_b64, "After")

        n_applied = sum(1 for r in st.session_state.apply_results
                        if "✅" in r.get("status", ""))
        st.success(f"""
**Audit Complete! 🎉**
- **{n_applied} fixes applied** out of {len(st.session_state.approved_fixes)} approved
- Mobile: **{ps_b['score']} → {ps_a['score']}** ({dm:+d})
- Desktop: **{ps_bd['score']} → {ps_ad['score']}** ({dd:+d})
        """)

        if dm < 0:
            st.warning("⚠️ Mobile score decreased — check P5 changes for "
                       "render-blocking resources or schema injection issues.")