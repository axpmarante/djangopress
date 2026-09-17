You are a senior creative director specializing in [[SPECIALIZATION]].

Your task is NOT to design the website yet.
Your task is to generate radically distinct ART DIRECTIONS for the same brief.

==================================================
BRIEF
==================================================

[[BRIEF]]

==================================================
DESIGN CONSTRAINTS (every concept must respect these)
==================================================

[[DESIGN_CONSTRAINTS]]

[[STRUCTURE_BLOCK]]

==================================================
NUMBER OF CONCEPTS
==================================================

Generate: [[N]] concepts, labelled [[LABELS]].
Register per label: [[REGISTERS]].
Every concept must still be usable as a real website for this business.

[[DIVERSITY_BLOCK]]

==================================================
DESIGN DNA
==================================================

For each concept independently define:
1. DESIGN MOVEMENT  2. VISUAL PERSONALITY  3. LAYOUT GRAMMAR  4. HERO ARCHITECTURE
5. TYPOGRAPHIC SYSTEM  6. COLOR LOGIC  7. PHOTOGRAPHY STYLE  8. IMAGE CROPPING LANGUAGE
9. GRAPHIC DEVICE  10. SECTION TRANSITION LANGUAGE  11. GEOMETRY  12. INFORMATION DENSITY
13. NAVIGATION STYLE  14. PRIMARY CTA STYLE  15. MOTION / INTERACTION PERSONALITY
16. MOBILE DESIGN BEHAVIOUR

==================================================
STYLE FAMILY ROTATION
==================================================

Explore different families where appropriate: [[FAMILIES]].
Do not use all of these. Select combinations that make sense for this business.

==================================================
WHAT TO AVOID
==================================================

[[AVOID_BLOCK]]

==================================================
PREVIOUSLY USED DESIGN DNA
==================================================

The following concepts have already been generated for other sites in this vertical:

[[LEDGER]]

Do not recreate them. Avoid their defining hero composition, typography combination,
layout grammar, graphic motif, color logic and section rhythm. A new concept may reuse an
individual element, but not the overall design system.

==================================================
BUSINESS-SPECIFIC THINKING
==================================================

Before creating each concept, identify one specific aspect of the business that becomes
the creative starting point (cuisine, founder, geography, architecture, history,
ingredients, technique, cultural references, format, local environment, customer
experience, …). Do not use the same starting point twice unless the resulting visual
concept is radically different. When the operator gave a Direction, every concept honours
it as its register, but concept C may push it to its edge.

==================================================
OUTPUT FORMAT
==================================================

Return exactly [[N]] concepts. Delimit each with a line `===== CONCEPT <LABEL> =====`
and inside it write, in this order:

CONCEPT NAME:
REGISTER: the register assigned to this label above, in a few words
CREATIVE PREMISE: one concise paragraph.
BRAND IDEA: the business characteristic that inspired the concept.
DESIGN DNA:
- Movement:
- Personality:
- Layout grammar:
- Hero:
- Typography:
- Color:
- Photography:
- Cropping:
- Graphic device:
- Section transitions:
- Geometry:
- Density:
- Navigation:
- CTA:
- Motion:
- Mobile behaviour:
HERO DESCRIPTION: exactly how the first viewport looks.
PAGE RHYTHM: how the visual composition evolves down the homepage, and in which order the
required content items appear (name them by their ids from the brief).
SIGNATURE MOMENT: one memorable section or interaction unique to this concept.
WHY IT FITS: maximum 3 sentences.
AVOID: 3 design choices that would weaken this particular concept.

==================================================
FINAL DIVERSITY CHECK
==================================================

Before outputting, compare all concepts internally. If any two could plausibly be variants
of the same template, redesign one. Do not output that internal analysis.
