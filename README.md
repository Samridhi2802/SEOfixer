# SEOPilot 🚀

**A deliberative AI agent for autonomous web optimization — implementing the ReAct paradigm across 6 structured phases to perceive, reason, act, and evaluate SEO improvements on live websites.**

> Built from a real problem: a family-run homestay near Auli, Uttarakhand was invisible on Google despite offering a better product than the aggregators dominating search results. SEOPilot is the autonomous system built to close that information gap — for any small business owner who can't afford an SEO consultant.

---

## What It Does

SEOPilot runs a complete autonomous SEO audit and fix pipeline — from scanning a live website to applying verified fixes directly to production systems — without requiring any SEO knowledge from the user.

```
P0 — Intake       → Site URL + business description
P1 — Scan         → Real browser scan via Crawl4AI + Playwright
P1b — Profile     → Groq/Llama 3.3 70B builds business profile
P2 — Research     → Serper finds true organic competitors
                    (filters out aggregators like MakeMyTrip)
P3 — Diagnose     → Up to 8 ranked issues: Critical / High / Medium
P4 — Approve      → Human approval gate — you control every fix
P5 — Apply        → WP REST API or GitHub API writes to live site
P6 — Verify       → Before/after PageSpeed comparison
```

---

## Research Contribution

SEOPilot is not just an SEO tool. It is a **production testbed for studying LLM reliability in structured real-world diagnosis tasks.**

The core research question:

> *Under what conditions do large language models reliably diagnose structured real-world problems — and where do they systematically fail?*

### Built-in Hallucination Detection (P3b)

Every Groq diagnosis is automatically cross-verified against ground-truth scan data from P1:

```
Groq says: "Meta description is missing"
P3b checks: Is meta_description actually empty in P1 scan data?
Result: ✅ Confirmed / ⚠️ Likely / ❌ Hallucinated
```

This produces measurable hallucination rates across issue types — directly relevant to LLM reliability research.

### ReAct Architecture

SEOPilot implements the ReAct paradigm (Yao et al., ICLR 2023) — interleaving reasoning and acting across structured phases:

```
Thought:     "Site has no schema markup"          ← Groq reasoning
Action:      "Inject JSON-LD via WP REST API"     ← Live API call  
Observation: "PageSpeed unchanged after fix"      ← P6 measurement
Re-thought:  "Schema injection didn't help speed" ← Adaptive response
```

### Human-in-the-Loop Design

P4 is a deliberate architectural choice — not a limitation. It studies the minimum necessary human intervention before an agent modifies live production infrastructure.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      SEOPilot                           │
├─────────────────────────────────────────────────────────┤
│  PERCEPTION LAYER                                       │
│  Crawl4AI ──── extracts page content (markdown)        │
│  Playwright ── real browser screenshots (desktop+mobile)│
│  Google PageSpeed API ── Core Web Vitals               │
├─────────────────────────────────────────────────────────┤
│  REASONING LAYER                                        │
│  Groq / Llama 3.3 70B ── business profiling            │
│  Groq / Llama 3.3 70B ── competitor gap analysis       │
│  Groq / Llama 3.3 70B ── SEO diagnosis (up to 8 issues)│
│  Hallucination Checker ── cross-verify vs scan data    │
├─────────────────────────────────────────────────────────┤
│  ACTION LAYER                                           │
│  WP REST API ── title, meta, schema, alt text fixes    │
│  GitHub REST API ── GitHub Pages site fixes            │
│  Human Gate (P4) ── approve / edit / skip each fix     │
├─────────────────────────────────────────────────────────┤
│  EVALUATION LAYER                                       │
│  Google PageSpeed ── before/after score comparison     │
│  Playwright ── before/after visual screenshot          │
│  Hallucination Rate ── tracked across all runs         │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Technology | Purpose |
|---|---|---|
| UI | Streamlit | Pipeline interface |
| Browser Automation | Playwright | Real screenshots, JS rendering |
| Content Extraction | Crawl4AI | Clean markdown for LLM |
| HTML Parsing | BeautifulSoup4 | Title, meta, H1-H3, schema |
| Competitor Search | Serper.dev API | Google search without CAPTCHA |
| LLM Reasoning | Groq + Llama 3.3 70B | Profiling, diagnosis, gap analysis |
| Performance | Google PageSpeed API | Core Web Vitals measurement |
| CMS Integration | WordPress REST API | Automated fix application |
| Version Control | GitHub REST API | GitHub Pages fix application |
| HTTP | httpx | Async-safe API calls |

---

## Installation

### Prerequisites
- Python 3.11+
- Windows, Mac, or Linux

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/seopilot.git
cd seopilot

# 2. Create virtual environment
python -m venv seopilot_env

# 3. Activate it
# Windows:
seopilot_env\Scripts\activate
# Mac/Linux:
source seopilot_env/bin/activate

# 4. Install dependencies
pip install streamlit httpx crawl4ai playwright beautifulsoup4

# 5. Install browser
python -m playwright install chromium

# 6. Run
streamlit run seopilot_final.py
```

---

## API Keys Required

| Key | Where to Get | Cost |
|---|---|---|
| Groq API Key | [console.groq.com](https://console.groq.com) | Free (14k req/day) |
| Serper.dev Key | [serper.dev](https://serper.dev) | Free (2500 queries) |
| Google API Key | [console.cloud.google.com](https://console.cloud.google.com) | Free (25k/day) |

All three are free. No credit card required for the free tiers used here.

### Optional (for auto-applying fixes)
- **WordPress**: Username + Application Password (WP Admin → Users → Application Passwords)
- **GitHub Pages**: Personal Access Token with `repo` scope

---

## Supported CMS Types

| CMS | Auto-Fix Support | What Gets Fixed |
|---|---|---|
| WordPress (no page builder) | ✅ Full | Title, meta, schema, alt text |
| GitHub Pages | ✅ Full | HTML file edits via GitHub API |
| WordPress + Elementor/Divi | ⚠️ Manual | Diagnosis only — apply manually |
| Shopify | ⚠️ Manual | Diagnosis only |
| Squarespace / Wix | ⚠️ Manual | Diagnosis only |

---

## Key Design Decisions

### Why filter aggregators in P2?
The original problem: searching "homestay near Auli" returns MakeMyTrip and Booking.com — not actual competitor homestays. These aggregators are not organic competitors. SEOPilot uses Groq to classify results and exclude aggregators, returning only true independent competitors in the same category.

### Why a human approval gate in P4?
An agent that writes to production systems without human review is dangerous. P4 is deliberately designed to study the minimum necessary human checkpoint — not as a limitation but as a research question about trust in agentic systems.

### Why Crawl4AI + Playwright separately?
On Windows, running Crawl4AI and Playwright in the same async context causes `NotImplementedError` due to event loop conflicts. SEOPilot runs them in separate threads with `WindowsProactorEventLoopPolicy` — a real engineering problem solved during development.

### Why PageSpeed is non-fatal?
Google's PageSpeed API returns 500 errors intermittently. SEOPilot retries 3 times with exponential backoff and continues the pipeline with empty scores rather than crashing — because the SEO diagnosis is valuable even without performance scores.

---

## Real-World Results

SEOPilot was developed and tested on [aulihimalaya.com](https://www.aulihimalaya.com) — a real family-run homestay near the Auli ski resort in Uttarakhand, India.

**The original problem:** The site was not appearing on Google search for the first 4 days after launch. After running SEOPilot's diagnosis and fixing the identified issues, the site began appearing in search results.

**What was found:** Missing schema markup, suboptimal meta description, weak H1 keyword targeting, images without alt text, mobile PageSpeed score below 60.

---

## Limitations & Honest Assessment

- **Auto-fix only works for WordPress and GitHub Pages** — other CMS types require manual application
- **Hallucination detection is field-based** — complex issues like content quality cannot be auto-verified
- **PageSpeed is a proxy metric** — improvements don't guarantee ranking changes
- **Competitor analysis is one-time** — no continuous monitoring yet (P7/P8 planned)
- **LLM reasoning quality depends on Groq availability** — API downtime affects diagnosis

---

## Planned Extensions

```
P7 — Google Indexing API submission
     Automatically notify Google of changes for faster re-crawl

P8 — Weekly rank monitoring via Prefect
     Track keyword positions and Core Web Vitals over time

Pre-build advisor
     Research competitive landscape BEFORE building a website
     Output SEO blueprint as AGENTS.md for Antigravity/Codex

IDE Integration
     VS Code extension / MCP server
     Inline fix suggestions like Copilot for SEO
```

---

## Research Context

This project implements and extends the ReAct agent paradigm (Yao et al., 2023) in a production environment. Key research questions being studied:

1. What is the hallucination rate of Llama 3.3 70B on structured SEO diagnosis tasks?
2. Which issue types (title, meta, schema, alt text) have the highest false-positive rate?
3. How often do users override AI-generated fix suggestions in P4?
4. Does PageSpeed improvement correlate with actual ranking changes?

Results from running SEOPilot on real websites will be documented in the research findings section as data is collected.

---

## Citation

If you use SEOPilot in research, please cite the ReAct paper this builds on:

```bibtex
@inproceedings{yao2023react,
  title={ReAct: Synergizing Reasoning and Acting in Language Models},
  author={Yao, Shunyu and Zhao, Jeffrey and Yu, Dian and Du, Nan and 
          Shafran, Izhak and Narasimhan, Karthik and Cao, Yuan},
  booktitle={ICLR},
  year={2023}
}
```

---

## Author

**Samridhi Naithani**
B.Tech Computer Science, Graphic Era University (2021-2025)
[LinkedIn](https://www.linkedin.com/in/samridhi-naithani-1ab449232) · [GitHub](https://github.com/Samridhi2802)

*Built from a real problem. Tested on a real website. Honest about its limitations.*

---

## License

MIT License — use freely, attribution appreciated.
