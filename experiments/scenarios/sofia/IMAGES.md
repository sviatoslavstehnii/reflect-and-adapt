# Images to Generate for Sofia's Scenarios

---

## S03 — `existing_thumbnails.png`

A single image showing a 2×3 grid of YouTube thumbnails in Sofia's consistent style.
Each thumbnail should look like a real YouTube thumbnail — 1280×720 proportions, cropped to fit.

**Each thumbnail contains:**
- A young woman (late 20s, warm brown hair, Mediterranean/Southern European features,
  friendly expression) occupying roughly the left or centre third
- Bold sans-serif text on the right or overlaid — 2–4 words, high contrast
- Warm, bright background — cream wall, soft window light, or blurred home office
- Occasional small graphic element (emoji, arrow, icon)
- Warm colour grading throughout — golden-hour tones, never cold

**Suggested thumbnail titles to render as text overlays:**
1. "honest review" (Notion AI video)
2. "I tested them all" (AI image generators)
3. "under £300" (home office)
4. "my actual workflow" (batch filming)
5. "does it work?" (CapCut AI)
6. "4 hours saved" (productivity tools)

**Prompt for generation:**
"A 2x3 grid of YouTube thumbnails in a consistent warm creator style. Each thumbnail shows
a young woman with warm brown hair and friendly expression, warm cream/earth tone backgrounds,
bold white or dark text overlay, soft home office or bright window lighting. Consistent cosy
aesthetic throughout. Flat lay / mockup style presentation."

---

## S09 — `sofia_reference.jpg`

A portrait photo of Sofia that she is providing as a reference for generating AI thumbnail images.

**What it should show:**
- Young woman, late 20s, warm brown shoulder-length hair, green/hazel eyes
- Light olive/medium skin tone, natural makeup
- Seated at a warm home office desk — wooden desk, soft lamp light, plants visible behind
- Wearing earth tones — a soft terracotta or cream linen top
- Expression: looking directly at camera with a genuine, warm smile
- Lighting: warm, soft — window light from the left, slight golden tone
- Background: slightly blurred cream wall + bookshelf or plants
- Framing: shoulders-up portrait, not a full-body shot

**Prompt for generation:**
"Portrait photo of a young woman in her late 20s, warm brown shoulder-length hair, light olive
skin, hazel eyes, natural makeup, genuine warm smile, looking directly at camera. Wearing soft
terracotta linen top. Seated at a warm wooden home office desk with plants and a soft lamp
visible in the background. Warm golden window light from the left. Shallow depth of field.
Cosy, natural, candid feel — not a studio portrait."

---

## Notes

- Both images should be saved as the exact filenames referenced in their scenario.yaml files
- `existing_thumbnails.png` → `scenarios/sofia/s03_thumbnail_concepts/existing_thumbnails.png`
- `sofia_reference.jpg` → `scenarios/sofia/s09_thumbnail_prompts/sofia_reference.jpg`
- The reference photo (S09) will be read by openclaw as a real image — the agent should
  be able to describe Sofia's appearance from it when generating DALL-E prompts
