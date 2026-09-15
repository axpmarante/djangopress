---
name: analyze-site
description: Analyze a DjangoPress site's quality and give a score from 0-100. Use when the user asks to analyze, score, or evaluate a site's quality. Requires the site slug as argument.
---

# Analyze Site Quality

Perform a comprehensive quality analysis of a DjangoPress site and score it from 0-100 across 10 categories.

## Usage

```
/analyze-site <slug>
```

## Prerequisites

- DjangoPress Manager running on `localhost:9000`
- The site must exist in the manager database
- Playwright CLI installed (`playwright-cli`)
- Lighthouse installed (`npm install -g lighthouse`) — optional, skip if not available

## Process

### Step 1: Get site info from the manager

```bash
curl -s http://localhost:9000/api/sites/ | python3 -c "
import sys, json
data = json.load(sys.stdin)
for site in data['sites']:
    if site['slug'] == '<SLUG>':
        print(json.dumps(site, indent=2))
        break
"
```

This gives you: page_count, languages, has_header, has_footer, domain, railway_url, github_url, screenshot, review_status.

### Step 2: Start the dev server (if not running)

```bash
curl -s -X POST http://localhost:9000/site/<SLUG>/start/ \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "X-CSRFToken: <TOKEN>" -b "csrftoken=<TOKEN>"
```

Get CSRF token first: `CSRF=$(curl -s -c - http://localhost:9000/ | grep csrftoken | awk '{print $NF}')`

Wait 3 seconds for it to start. Get the port from the response.

### Step 3: Analyze with Playwright

Open the site and analyze:

```bash
playwright-cli open http://localhost:<PORT>/
```

Run a single eval to collect all data at once:

```javascript
JSON.stringify({
  title: document.title,
  metaDesc: document.querySelector('meta[name=description]')?.content || '',
  viewport: !!document.querySelector('meta[name=viewport]'),
  ogTitle: !!document.querySelector('meta[property="og:title"]'),
  ogDesc: !!document.querySelector('meta[property="og:description"]'),
  ogImage: !!document.querySelector('meta[property="og:image"]'),
  h1: document.querySelector('h1')?.textContent?.trim()?.substring(0, 80) || '',
  imgCount: document.querySelectorAll('img').length,
  imgWithAlt: document.querySelectorAll('img[alt]:not([alt=""])').length,
  imgBroken: Array.from(document.querySelectorAll('img')).filter(i => i.src && !i.naturalWidth && !i.closest('[x-cloak]')).length,
  linksCount: document.querySelectorAll('a[href]').length,
  bodyTextLen: document.body.innerText.trim().length,
  cookieBanner: document.body.innerHTML.indexOf('cookieConsent') > -1,
  privacyLink: !!document.querySelector('a[href*=privacy], a[href*=politica]'),
  formCount: document.querySelectorAll('form:not([method=get])').length,
  formFields: Array.from(document.querySelectorAll('form input, form textarea, form select')).map(f => f.type || f.tagName).join(','),
  hasPhone: /(\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4})/.test(document.body.innerText),
  hasEmail: /[\w.-]+@[\w.-]+\.\w{2,}/.test(document.body.innerText),
  phoneNumbers: (document.body.innerText.match(/\+\d[\d\s.-]{8,}/g) || []).join(', '),
  emailAddresses: (document.body.innerText.match(/[\w.-]+@[\w.-]+\.\w{2,}/g) || []).join(', '),
})
```

Then check all internal links for 404s:
```javascript
// Get unique internal links
JSON.stringify(Array.from(new Set(
  Array.from(document.querySelectorAll('a[href]'))
    .map(a => a.href)
    .filter(h => h.startsWith('http://localhost'))
)))
```

Navigate to each link and check status with curl:
```bash
for url in <URLS>; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  echo "$code $url"
done
```

**Mobile Check:**
```bash
playwright-cli resize 375 667
playwright-cli eval "document.documentElement.scrollWidth <= 375 ? 'ok' : 'scroll'"
```

**Form Test (on contact page):**
Navigate to the contact page and verify:
- Form exists with proper fields (name, email, message at minimum)
- Form has CSRF token
- Submit button exists
- Optional: test submission with test data

**Contact Verification:**
- Check phone numbers are in valid international format (+351...)
- Check email addresses are real-looking (not placeholder@example.com)
- Verify `tel:` and `mailto:` links exist for phone/email

### Step 4: Run Lighthouse (if available)

```bash
lighthouse http://localhost:<PORT>/ --output=json --quiet --chrome-flags="--headless" 2>/dev/null
```

If not installed, skip and estimate from page load timing.

### Step 5: Visual Design Analysis

```bash
playwright-cli screenshot --filename=/tmp/analyze-<SLUG>.png
```

Read the screenshot and evaluate: consistent color scheme, structured layout, professional look, readable fonts.

### Step 6: Calculate scores

Score each category from 0-100:

| Category | Weight | What to check |
|----------|--------|---------------|
| `content` | 15% | Pages exist, real text (not placeholder), header+footer, sufficient content |
| `seo` | 10% | Title, meta description, h1, viewport, OG tags (title, desc, image) |
| `performance` | 10% | Lighthouse performance score (or page load time) |
| `images` | 10% | Images exist, all load, have alt text |
| `links` | 10% | No broken internal links |
| `mobile` | 10% | Responsive layout, no horizontal scroll |
| `design` | 10% | Visual consistency, professional look, color scheme |
| `accessibility` | 5% | Alt text, heading hierarchy, semantic HTML, ARIA labels |
| `forms` | 10% | Contact form exists, has required fields (name, email, message), CSRF token, submit button, privacy consent checkbox |
| `compliance` | 10% | Cookie consent banner present, privacy policy page exists and linked, GDPR-compliant, contact info (phone+email) visible and valid |

**Total = weighted average of all category scores.**

### Step 7: Stop the dev server (if you started it)

```bash
curl -s -X POST http://localhost:9000/site/<SLUG>/stop/ \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "X-CSRFToken: <TOKEN>" -b "csrftoken=<TOKEN>"
```

### Step 8: Save scores to the manager

```bash
curl -s -X POST http://localhost:9000/site/<SLUG>/quality-score/ \
  -H "Content-Type: application/json" \
  -d '{
    "total": <TOTAL_SCORE>,
    "scores": {
      "content": {"score": <0-100>, "details": "<what was found>"},
      "seo": {"score": <0-100>, "details": "<what was found>"},
      "performance": {"score": <0-100>, "details": "<what was found>"},
      "images": {"score": <0-100>, "details": "<what was found>"},
      "links": {"score": <0-100>, "details": "<what was found>"},
      "mobile": {"score": <0-100>, "details": "<what was found>"},
      "design": {"score": <0-100>, "details": "<what was found>"},
      "accessibility": {"score": <0-100>, "details": "<what was found>"},
      "forms": {"score": <0-100>, "details": "<what was found>"},
      "compliance": {"score": <0-100>, "details": "<what was found>"}
    }
  }'
```

### Step 9: Report results

Present a summary table to the user:

```
Site: <Name> (<slug>)
Overall Score: <TOTAL>/100

| Category      | Score | Details                              |
|---------------|-------|--------------------------------------|
| Content       | XX    | 5 pages, header+footer               |
| SEO           | XX    | Missing OG image                     |
| Performance   | XX    | 779ms load                           |
| Images        | XX    | 12 images, 2 missing alt             |
| Links         | XX    | 0 broken / 15 total                  |
| Mobile        | XX    | Responsive OK                        |
| Design        | XX    | Consistent, professional             |
| Accessibility | XX    | Good contrast, semantic              |
| Forms         | XX    | Contact form OK, 3 fields            |
| Compliance    | XX    | Cookie banner ✓, Privacy page ✓      |

Contact: +351 912 345 678 ✓, info@example.com ✓
```

### Step 10: Clean up

```bash
playwright-cli close
rm -f /tmp/analyze-<SLUG>.png
```

## Next Steps

After analyzing, suggest to the user:
- If score is below 80: "Run `/improve-site <slug>` to automatically fix the lowest-scoring issues"
- If score is above 80: "Good score! Run `/improve-site <slug>` to fine-tune the remaining issues"

The `/improve-site` skill reads this report, fixes the worst categories, and re-runs `/analyze-site` to measure the improvement.

## Important Notes

- Always stop the dev server if you started it
- Always close the Playwright browser when done
- If Lighthouse is not available, estimate performance from page load behavior
- Be honest in scoring — a placeholder site should score low
- The CSRF token handling for the save endpoint may need adjustment — if POST fails, try fetching the token from the cookie first
- Each analysis creates a QualityReport record for historical tracking — you can compare scores over time
- **Forms**: check the contact page specifically, not just the homepage
- **Compliance**: cookie banner + privacy page are MANDATORY for GDPR. Score 0 if both missing.
- **Contact info**: phone numbers should be in international format (+351...), emails should be real (not @example.com)
