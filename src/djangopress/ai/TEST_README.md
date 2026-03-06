# AI Prompt Testing Guide

This guide explains how to test each AI method individually to see the actual prompts being sent to the LLM.

## 🚀 Quick Start

### Using Management Command (Recommended)

The easiest way to test prompts:

```bash
# Test a specific method
python manage.py test_ai_prompts --test generate_page
python manage.py test_ai_prompts --test generate_section
python manage.py test_ai_prompts --test refine_section
python manage.py test_ai_prompts --test refine_global_section
python manage.py test_ai_prompts --test refine_page
python manage.py test_ai_prompts --test bulk_analysis

# Run all tests
python manage.py test_ai_prompts --test all

# Use a different model
python manage.py test_ai_prompts --test generate_page --model gemini-pro

# Dry run (don't save results to database)
python manage.py test_ai_prompts --test refine_section --no-save
```

### Using Python Script

For more control and interactive testing:

```bash
# Interactive menu
python manage.py shell < ai/test_prompts.py

# Or import and run specific tests
python manage.py shell
>>> from ai.test_prompts import *
>>> test_generate_page()
>>> test_refine_section()
```

## 📋 Available Tests

### 1. Generate Page
Tests complete page generation with multiple sections.

```bash
python manage.py test_ai_prompts --test generate_page
```

**What it does:**
- Creates 4-8 sections for a complete page
- Shows system and user prompts
- Displays token estimates
- Returns section data (not saved unless you specify)

### 2. Generate Section
Tests single section generation.

```bash
python manage.py test_ai_prompts --test generate_section
```

**What it does:**
- Creates a single section based on brief
- Shows prompts and token counts
- Returns section data

### 3. Refine Section
Tests section refinement on an existing section.

```bash
python manage.py test_ai_prompts --test refine_section
```

**What it does:**
- Takes first section from database
- Refines it based on instructions
- Shows before/after
- Can save changes (without --no-save)

**Requirements:**
- At least one section must exist in the database

### 4. Refine Global Section
Tests header/footer refinement.

```bash
python manage.py test_ai_prompts --test refine_global_section
```

**What it does:**
- Refines the main header
- Shows all page URLs available for navigation
- Can save changes (without --no-save)

**Requirements:**
- A GlobalSection with key='main-header' must exist

### 5. Refine Page
Tests complete page refinement using HTML approach.

```bash
python manage.py test_ai_prompts --test refine_page
```

**What it does:**
- Takes entire page HTML
- Shows all sections with metadata
- Refines multiple sections at once
- Supports create/update/delete actions

**Requirements:**
- At least one page with sections must exist

### 6. Bulk Page Analysis
Tests natural language page extraction.

```bash
python manage.py test_ai_prompts --test bulk_analysis
```

**What it does:**
- Analyzes a website description
- Extracts structured page list
- Returns page titles, slugs, and descriptions in all languages

## 🎯 What You'll See

When running any test, you'll see:

```
================================================================================
SYSTEM PROMPT (≈250 tokens):
================================================================================
[Full system prompt with all instructions...]

================================================================================
USER PROMPT (≈1500 tokens):
================================================================================
[Full user prompt with context and request...]
================================================================================
TOTAL ESTIMATED TOKENS: ≈1750
================================================================================
```

## 🔧 Options

### Model Selection

Change the LLM model:

```bash
--model gemini-flash    # Fast, cheaper (default)
--model gemini-pro      # More capable
--model gpt-5          # OpenAI (if configured)
--model claude         # Anthropic (if configured)
```

### Dry Run Mode

Test without saving to database:

```bash
--no-save
```

This is useful for:
- Seeing prompts without side effects
- Testing on production data safely
- Experimenting with different instructions

## 📊 Token Estimates

The test commands show approximate token counts:
- System prompt tokens
- User prompt tokens
- Total tokens

**Note:** These are estimates using `word_count × 1.3`. Actual tokens may vary slightly depending on the tokenizer used by the LLM.

## 💡 Example Workflows

### Test Before Deploying New Prompts

```bash
# Test all methods to ensure prompts work correctly
python manage.py test_ai_prompts --test all --no-save

# If all pass, remove --no-save to actually use
python manage.py test_ai_prompts --test refine_section
```

### Debug Prompt Issues

```bash
# Run specific test to see exact prompt
python manage.py test_ai_prompts --test generate_page

# Check the terminal output for:
# - System prompt content
# - User prompt content
# - Token estimates
# - Any errors
```

### Compare Different Models

```bash
# Test with fast model
python manage.py test_ai_prompts --test generate_section --model gemini-flash

# Test with powerful model
python manage.py test_ai_prompts --test generate_section --model gemini-pro

# Compare token usage and quality
```

## 🐛 Troubleshooting

### "No sections found in database"

Create some sections first:
```bash
python manage.py shell
>>> from ai.test_prompts import test_generate_page
>>> test_generate_page()
```

### "No main-header found"

Create a GlobalSection:
```python
from core.models import GlobalSection

GlobalSection.objects.create(
    key='main-header',
    section_type='header',
    name='Main Header',
    html_template='<header>...</header>',
    is_active=True
)
```

### "Module not found" errors

Make sure you're in the project directory:
```bash
cd /Users/antoniomarante/Documents/DjangoSites/get_algarve
python manage.py test_ai_prompts --test all
```

## 📈 Next Steps

After testing prompts:

1. **Review token usage** - Optimize if prompts are too large
2. **Check prompt quality** - Ensure instructions are clear
3. **Test with different models** - Find best balance of cost/quality
4. **Iterate on instructions** - Refine based on LLM responses

## 🔗 Related Files

- `ai/services.py` - Service methods that use prompts
- `ai/utils/prompts.py` - All prompt templates
- `ai/views.py` - API endpoints that call services
- `ai/test_prompts.py` - Python test script
- `ai/management/commands/test_ai_prompts.py` - Management command
