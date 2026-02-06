# Logo Usage Guide

## Available Logo Variables

In all templates, you have access to two logo variables from the context processor:

- **`LOGO`** or **`SITE_LOGO`**: Main logo for light/white backgrounds
- **`LOGO_DARK_BG`** or **`SITE_LOGO_DARK_BG`**: Alternative logo for dark backgrounds (typically white/light version)

## Usage Examples

### Light Background (Default)
Use the main logo for sections with light/white backgrounds:

```django
{% if LOGO %}
<img src="{{ LOGO.url }}" alt="{{ SITE_NAME }}" class="h-12 w-auto">
{% endif %}
```

### Dark Background
Use the dark logo for sections with dark backgrounds:

```django
<section class="bg-gray-900 py-16">
    <div class="container mx-auto">
        {% if LOGO_DARK_BG %}
        <img src="{{ LOGO_DARK_BG.url }}" alt="{{ SITE_NAME }}" class="h-12 w-auto">
        {% else %}
        <!-- Fallback to main logo if dark logo is not set -->
        <img src="{{ LOGO.url }}" alt="{{ SITE_NAME }}" class="h-12 w-auto">
        {% endif %}
    </div>
</section>
```

### Conditional Logo Based on Background
If you need to dynamically switch between logos based on a condition:

```django
{% if dark_background %}
    {% if LOGO_DARK_BG %}
    <img src="{{ LOGO_DARK_BG.url }}" alt="{{ SITE_NAME }}" class="h-12 w-auto">
    {% else %}
    <img src="{{ LOGO.url }}" alt="{{ SITE_NAME }}" class="h-12 w-auto filter invert">
    {% endif %}
{% else %}
    <img src="{{ LOGO.url }}" alt="{{ SITE_NAME }}" class="h-12 w-auto">
{% endif %}
```

## Best Practices

1. **Always provide both logos**: Upload both light and dark versions in Site Settings
2. **Use appropriate logo for background**: Match the logo to the background color
3. **Provide fallback**: Always check if logo exists before using it
4. **Alt text**: Always include `alt="{{ SITE_NAME }}"` for accessibility
5. **Consistent sizing**: Use Tailwind classes like `h-12` or `h-16` for consistent logo sizing

## Where to Upload Logos

### Django Admin
1. Go to `/admin/core/sitesettings/`
2. Upload:
   - **Logo (Light Backgrounds)**: Your main logo (typically dark colored)
   - **Logo (Dark Backgrounds)**: Your alternative logo (typically white/light colored)

### Backoffice
1. Go to `/backoffice/settings/`
2. Scroll to "General Information" section
3. Upload both logos in their respective fields

## Common Use Cases

### Header with White Background
```django
<header class="bg-white">
    <img src="{{ LOGO.url }}" alt="{{ SITE_NAME }}">
</header>
```

### Header with Dark Background
```django
<header class="bg-gray-900">
    <img src="{{ LOGO_DARK_BG.url }}" alt="{{ SITE_NAME }}">
</header>
```

### Footer (Usually Light Background)
```django
<footer class="bg-gray-50">
    <img src="{{ LOGO.url }}" alt="{{ SITE_NAME }}">
</footer>
```

### Footer (Dark Background)
```django
<footer class="bg-gray-900 text-white">
    <img src="{{ LOGO_DARK_BG.url }}" alt="{{ SITE_NAME }}">
</footer>
```
