# Style Calibration — Design Document

## Problem

The AI generation/refinement prompts include hardcoded "Design Quality Standards" (`_get_design_quality_guidelines()` in `ai/utils/prompts.py:35-79`) that push every output toward aggressive, highly-styled layouts — asymmetric grids, dramatic size contrast, py-32 heroes, dark visual anchors, hover transitions. Users cannot control the style feel. A request like "add a button to the card" always produces a bold, complex result even when the user wants something clean and simple.

## Solution

Remove the hardcoded style guidelines. Let the existing `design_guide` field handle persistent style context. Add three prompt-assistance features to instruction inputs so users can easily express what style they want.

## Design

### 1. Remove Hardcoded Guidelines

Delete `_get_design_quality_guidelines()` and all calls to it across every prompt function:
- `get_page_generation_html_prompt()`
- `get_page_refinement_html_prompt()` (and by extension `get_chat_refinement_html_prompt()`)
- `get_section_refinement_prompt()`
- `get_element_refinement_prompt()`
- `get_global_section_refinement_prompt()`

**Fallback when no style context exists:** None. The LLM uses the design system (colors, fonts, spacing from SiteSettings) and the `design_guide` field. If both are empty, the LLM generates with its own baseline judgment — neutral, professional HTML. This matches the pre-`be7f10a` behavior.

### 2. Design Guide Stays As-Is

The `design_guide` TextField on SiteSettings remains the persistent style/design context. It's already injected into every prompt as `## Design Guide`. No changes needed to the field, the model, or the injection logic.

### 3. Instruction Input Features

Three features added to instruction textareas in the backoffice AI pages and the editor v2 AI panel:

#### A. Tag Chips

Clickable style keywords displayed below the textarea. Clicking a tag appends it to the textarea text (or removes it if already present). Tags are plain text — no hidden logic.

Tags:
`minimal` `bold` `corporate` `playful` `dark theme` `spacious` `compact` `flat` `rounded` `sharp` `gradients` `card-heavy` `asymmetric` `centered` `image-rich` `monochrome` `vibrant`

#### B. Enhance Button

Sends the current textarea content to gemini-flash with a meta-prompt:
> "Expand this into a clear, detailed design instruction for a web designer. Be specific about layout, spacing, typography, and visual feel. Reference Tailwind CSS patterns where relevant. Keep it under 150 words."

The enhanced result replaces the textarea content. The user reviews and edits before sending.

#### C. Suggest Button (Editor v2 Only)

Only available when a section or element is selected. Sends the current section/element HTML to gemini-flash:
> "Analyze this HTML section and suggest 3-5 specific visual/layout improvements. Write as a single instruction paragraph the user can send to an AI to refine the section."

The suggestion is inserted into the textarea as a starting point. The user edits before sending.

### 4. New API Endpoint

`POST /ai/api/enhance-prompt/`

Request:
```json
{
  "text": "make it clean and add a button",
  "section_html": "<section ...>...</section>",
  "mode": "enhance" | "suggest"
}
```

- `mode=enhance`: Polishes the user's text into a detailed instruction
- `mode=suggest`: Analyzes `section_html` and generates improvement suggestions
- `section_html` is optional (only sent for suggest mode)

Response:
```json
{
  "success": true,
  "text": "Create a clean, minimal layout with generous whitespace..."
}
```

Uses gemini-flash (fast, cheap). No DB writes. Staff-only.

### 5. Where Each Feature Appears

| Feature | SiteSettings | Backoffice AI Pages | Editor v2 AI Panel |
|---------|-------------|--------------------|--------------------|
| Tags    | No          | Yes                | Yes                |
| Enhance | No          | Yes                | Yes                |
| Suggest | No          | No                 | Yes                |

SiteSettings design guide page already has its own "AI Generate Design Guide" button.

### 6. No New Model Fields

Tags, enhance, and suggest all modify the instruction text before it's sent. The backend receives the same `instructions` string it always did. No migration needed. The only backend change is removing `_get_design_quality_guidelines()` and adding the `/enhance-prompt/` endpoint.
