"""
Component skill: DynamicForm Submission.

DjangoPress has a built-in form system (DynamicForm model) that handles
submission, validation, honeypot spam filtering, rate limiting, email
notifications, and optional confirmation emails. Forms submit to
`/forms/SLUG/submit/` and store data as JSON.
"""

NAME = "dynamic-form"

DESCRIPTION = "DynamicForm submission with CSRF, honeypot spam protection, and email notifications."

INDEX_ENTRY = (
    "DynamicForm submission. `action=\"/forms/SLUG/submit/\"` with `{% csrf_token %}`, "
    "hidden honeypot `name=\"website_url\"`, fixed `name` attrs for field keys. "
    "Use `{{ trans.xxx }}` for labels/placeholders. Common slugs: contact, quote-request, booking."
)

FULL_REFERENCE = """\
### Form Submission (Dynamic Forms)

Forms are handled by the DynamicForm system built into DjangoPress. Each form has
a **slug** and a submission endpoint at `/forms/SLUG/submit/`.

#### How It Works

1. A `DynamicForm` record must exist in the database with a matching slug (e.g., slug=`contact`)
2. The HTML form's `action` points to `/forms/SLUG/submit/`
3. On submit, all form fields are saved as JSON in a `FormSubmission` record
4. The site owner gets an email notification (sent to the form's `notification_email` or the site's `contact_email`)
5. Optionally, the submitter receives a confirmation email (if enabled on the DynamicForm)
6. Built-in rate limiting: max 5 submissions per IP per form per hour
7. Honeypot spam protection filters out bot submissions silently

#### Basic Contact Form

```html
<form action="/forms/contact/submit/" method="post" class="space-y-6">
  {{% csrf_token %}}

  <!-- Honeypot - REQUIRED, do NOT remove or rename -->
  <div style="position:absolute;left:-9999px;" aria-hidden="true">
    <input type="text" name="website_url" tabindex="-1" autocomplete="off">
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.form_name_label }}</label>
    <input type="text" name="name" required placeholder="{{ trans.form_name_placeholder }}" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.form_email_label }}</label>
    <input type="email" name="email" required placeholder="{{ trans.form_email_placeholder }}" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.form_phone_label }}</label>
    <input type="tel" name="phone" placeholder="{{ trans.form_phone_placeholder }}" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition">
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.form_message_label }}</label>
    <textarea name="message" rows="5" required placeholder="{{ trans.form_message_placeholder }}" class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"></textarea>
  </div>

  <button type="submit" class="w-full px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition">{{ trans.form_submit_btn }}</button>
</form>
```

#### Common Form Slugs

| Slug | Use Case |
|------|----------|
| `contact` | General contact/inquiry form (seeded by default on migrate) |
| `quote-request` | Quote or estimate request |
| `booking` | Reservation or appointment booking |
| `newsletter` | Newsletter signup (typically just email field) |
| `feedback` | Customer feedback or review |
| `application` | Job application or enrollment |

The slug in the `action` URL MUST correspond to an existing `DynamicForm` record
in the database. If no form exists for that slug, submissions will return a 404.

#### Available Field Types

Use standard HTML input types. The form system stores all values as JSON.

| Type | HTML | Notes |
|------|------|-------|
| Text | `<input type="text" name="name">` | Short text input |
| Email | `<input type="email" name="email">` | Email with browser validation |
| Phone | `<input type="tel" name="phone">` | Phone number |
| Number | `<input type="number" name="quantity">` | Numeric input |
| Date | `<input type="date" name="date">` | Date picker |
| Time | `<input type="time" name="time">` | Time picker |
| Textarea | `<textarea name="message" rows="5">` | Multi-line text |
| Select | `<select name="subject"><option>...</option></select>` | Dropdown |
| Checkbox | `<input type="checkbox" name="consent">` | Single checkbox (stored as `true`/`false`) |
| Radio | `<input type="radio" name="preference" value="a">` | Radio group |
| Hidden | `<input type="hidden" name="source" value="homepage">` | Hidden field (e.g., tracking) |

#### Quote Request Form Example

```html
<form action="/forms/quote-request/submit/" method="post" class="space-y-6">
  {{% csrf_token %}}

  <!-- Honeypot -->
  <div style="position:absolute;left:-9999px;" aria-hidden="true">
    <input type="text" name="website_url" tabindex="-1" autocomplete="off">
  </div>

  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.quote_name_label }}</label>
      <input type="text" name="name" required class="w-full px-4 py-3 border rounded-lg">
    </div>
    <div>
      <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.quote_email_label }}</label>
      <input type="email" name="email" required class="w-full px-4 py-3 border rounded-lg">
    </div>
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.quote_service_label }}</label>
    <select name="service" required class="w-full px-4 py-3 border rounded-lg bg-white">
      <option value="">{{ trans.quote_service_placeholder }}</option>
      <option value="web-design">{{ trans.quote_service_web }}</option>
      <option value="branding">{{ trans.quote_service_branding }}</option>
      <option value="marketing">{{ trans.quote_service_marketing }}</option>
    </select>
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.quote_budget_label }}</label>
    <select name="budget" class="w-full px-4 py-3 border rounded-lg bg-white">
      <option value="">{{ trans.quote_budget_placeholder }}</option>
      <option value="under-1000">< 1,000</option>
      <option value="1000-5000">1,000 - 5,000</option>
      <option value="5000-10000">5,000 - 10,000</option>
      <option value="over-10000">> 10,000</option>
    </select>
  </div>

  <div>
    <label class="block text-sm font-medium text-gray-700 mb-1">{{ trans.quote_details_label }}</label>
    <textarea name="details" rows="4" class="w-full px-4 py-3 border rounded-lg" placeholder="{{ trans.quote_details_placeholder }}"></textarea>
  </div>

  <button type="submit" class="px-8 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition">{{ trans.quote_submit_btn }}</button>
</form>
```

#### Newsletter Signup (Minimal)

```html
<form action="/forms/newsletter/submit/" method="post" class="flex gap-3">
  {{% csrf_token %}}
  <div style="position:absolute;left:-9999px;" aria-hidden="true">
    <input type="text" name="website_url" tabindex="-1" autocomplete="off">
  </div>
  <input type="email" name="email" required placeholder="{{ trans.newsletter_placeholder }}" class="flex-1 px-4 py-3 border rounded-lg">
  <button type="submit" class="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition whitespace-nowrap">{{ trans.newsletter_btn }}</button>
</form>
```

#### Checkbox Consent Example

```html
<div class="flex items-start gap-2">
  <input type="checkbox" name="privacy_consent" id="privacy_consent" required class="mt-1">
  <label for="privacy_consent" class="text-sm text-gray-600">{{ trans.form_privacy_consent }}</label>
</div>
```

Checkbox values are stored as `true` (when checked) in the JSON submission. If
unchecked and not `required`, the field is simply absent from the data.

#### Rules

**CSRF Token:**
- Always include `{{% csrf_token %}}` as the first element inside `<form>` (note: double braces `{{%` in generation context because the HTML is itself a Django template)
- Without it, submissions will be rejected with a 403 Forbidden error

**Honeypot Field (REQUIRED):**
- Always include the hidden `website_url` input exactly as shown
- It must be: `<input type="text" name="website_url" tabindex="-1" autocomplete="off">`
- Wrapped in a `<div>` with `style="position:absolute;left:-9999px;" aria-hidden="true"`
- Do NOT change the field name from `website_url`
- Do NOT remove this field — it's the spam protection mechanism
- Bots auto-fill it, humans don't see it, and the server silently discards submissions where it has a value

**Field Names:**
- Input `name` attributes are fixed identifiers — they are NOT translated
- They become the JSON keys in the `FormSubmission.data` field
- Use snake_case for consistency: `name`, `email`, `phone`, `message`, `company_name`
- Use `{{ trans.xxx }}` only for visible text: labels, placeholders, button text, helper text

**Select/Option Values:**
- `<option value="...">` values are fixed identifiers (not translated)
- The visible `<option>` text should use `{{ trans.xxx }}`
- Exception: numeric or code values (e.g., budget ranges) can be plain text

**Form Action URL:**
- Must be `/forms/SLUG/submit/` where SLUG matches a DynamicForm record
- This URL is outside `i18n_patterns` — it does NOT have a language prefix
- Do NOT use `{% url %}` tag for this — use the literal path

#### AJAX Submission (Optional)

The form endpoint supports AJAX (returns JSON). Add Alpine.js handling:

```html
<form x-data="{ loading: false, success: false, error: '' }"
      @submit.prevent="
        loading = true; error = '';
        fetch('/forms/contact/submit/', {
          method: 'POST',
          body: new FormData($el),
        })
        .then(r => r.json())
        .then(d => { loading = false; if(d.success) success = true; else error = d.message || 'Error'; })
        .catch(() => { loading = false; error = 'Network error'; })
      " class="space-y-6">

  {{% csrf_token %}}
  <!-- honeypot + fields as above -->

  <div x-show="success" class="p-4 bg-green-50 text-green-700 rounded-lg">
    {{ trans.form_success_message }}
  </div>
  <div x-show="error" class="p-4 bg-red-50 text-red-700 rounded-lg" x-text="error"></div>

  <button type="submit" :disabled="loading" class="px-6 py-3 bg-blue-600 text-white rounded-lg">
    <span x-show="!loading">{{ trans.form_submit_btn }}</span>
    <span x-show="loading">{{ trans.form_sending }}</span>
  </button>
</form>
```

The JSON response format:
- Success: `{"success": true, "message": "Thank you!"}`
- Validation error: `{"success": false, "errors": {"email": "This field is required."}}`
- Rate limit: `{"success": false, "message": "Too many submissions."}` (HTTP 429)
- Not found: `{"success": false, "error": "Form not found."}` (HTTP 404)

#### File Uploads Note

The DynamicForm system currently does NOT support file uploads. All field values
are stored as JSON strings. If file uploads are needed, a custom view must be
implemented in a decoupled app.

#### Do's and Don'ts

**Do:**
- Always include `{{% csrf_token %}}`
- Always include the honeypot field with `name="website_url"` exactly as shown
- Use `{{ trans.xxx }}` for all visible text (labels, placeholders, buttons)
- Use fixed, untranslated `name` attributes on inputs
- Use `required` on mandatory fields for client-side validation
- Add `focus:ring-2 focus:ring-blue-500 focus:border-transparent` for focus styles
- Match form styling to the site's design system

**Don't:**
- Do NOT change the honeypot field name from `website_url`
- Do NOT remove the honeypot field
- Do NOT translate input `name` attributes
- Do NOT use `{% url %}` for the form action — use the literal `/forms/SLUG/submit/` path
- Do NOT add a language prefix to the form action URL (it's outside `i18n_patterns`)
- Do NOT use `GET` method — forms must submit via `POST`
- Do NOT add `enctype="multipart/form-data"` — file uploads are not supported

#### Common Mistakes

1. **Missing `{{% csrf_token %}}`** — Every POST form in Django requires CSRF protection. Without it, the submission returns 403 Forbidden.
2. **Missing or renamed honeypot field** — The field must be named exactly `website_url`. Renaming it breaks spam protection.
3. **Translating `name` attributes** — Input names like `name="nome"` (Portuguese) instead of `name="name"` create inconsistent JSON keys. Keep names in English as fixed identifiers.
4. **Adding language prefix to form action** — The URL `/forms/contact/submit/` is correct. `/en/forms/contact/submit/` will 404.
5. **Non-existent form slug** — The slug in the URL must match a DynamicForm record in the database. If no `DynamicForm` with slug `contact` exists, submissions return 404.
6. **Forgetting `method="post"`** — Without it, the browser sends a GET request, which doesn't trigger form processing.
"""
