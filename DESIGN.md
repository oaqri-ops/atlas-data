---
version: 1
name: Atlas Data
description: >
  Data journalism for the Moroccan property market. A calm, numbers-first interface: navy ink on
  white and cool-grey surfaces, one confident royal blue for data and primary actions, terracotta
  and green only to say "above / below the city". Archivo (wide, heavy) for headlines and figures,
  Roboto for reading, Roboto Mono for data labels. Every number is honest about its source, its date and its sample size.

colors:
  ink: "#0f1a33"          # text, headings, dark buttons
  muted: "#4f5a6e"        # secondary text
  faint: "#5f687a"        # captions, axis labels, metadata
  blue: "#2340c2"         # primary action, data marks, key figure
  blue-dark: "#1a2f94"    # primary hover
  blue-soft: "#b7c3f1"    # secondary data marks (other neighbourhoods)
  tint: "#eef1fa"         # selected row, result panel
  navy: "#0f1a33"         # footer, Pro offer band
  canvas: "#ffffff"
  soft: "#f5f6f8"         # page heroes, alternating sections, table heads
  line: "#e3e6ec"         # borders, dividers, grid lines
  line-strong: "#c9ceda"  # input and ghost-button borders
  clay: "#b8502a"         # "above city median", live-data badge dot
  clay-ink: "#8a3a1c"
  clay-tint: "#fbede6"
  green-ink: "#0b5a4b"    # "below city median", positive result
  green-tint: "#e3f3ef"

typography:
  display:
    fontFamily: "'Archivo', 'Arial Narrow', Arial, sans-serif"
    usage: headings, all prominent numbers, logo word
  body:
    fontFamily: "'Roboto', system-ui, -apple-system, 'Segoe UI', sans-serif"
    usage: everything else
  mono:
    fontFamily: "'Roboto Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    usage: >
      data labels only: eyebrows, column heads and figures of the hero ticket, offer table labels.
      12px, weight 500, uppercase, letter-spacing .06-.08em for labels; 14px for figures. Never for
      sentences or headings. Loaded on the home page and the dashboard (variable --mono).
  scale:
    hero-h1:     { size: "clamp(40px, 5.2vw, 64px)", weight: 800, lineHeight: 1.03, letterSpacing: -0.035em }
    page-h1:     { size: "clamp(36px, 4.6vw, 58px)", weight: 800, lineHeight: 1.04, letterSpacing: -0.035em }
    section-h2:  { size: "clamp(30px, 3.6vw, 44px)", weight: 800, lineHeight: 1.08, letterSpacing: -0.03em }
    block-h2:    { size: "clamp(26px, 3vw, 36px)",   weight: 800, lineHeight: 1.10, letterSpacing: -0.03em }
    card-title:  { size: 22-24px, weight: 800, letterSpacing: -0.02em }
    lede:        { size: 17-19px, weight: 400, lineHeight: 1.55, color: muted }
    body:        { size: 16px, weight: 400, lineHeight: 1.6 }
    small:       { size: 13-14px, color: muted or faint }
    figure-xl:   { size: "clamp(72px, 8vw, 104px)", weight: 800, family: display, color: blue }
    figure:      { size: 28-40px, weight: 800, family: display, letterSpacing: -0.03em }
  numbers: "font-variant-numeric: tabular-nums everywhere a number can line up; thousands separated by a non-breaking space (18 509)"

radius:
  button: 6px
  input: 8px
  card: 12px
  panel: 14px      # calculator, Pro card, dialog
  pill: 999px      # chips, badges, deltas

spacing:
  shell: 1180px max, 24px gutter (18px under 600px)
  section: 96px vertical (72px under 820px)
  block: 72px vertical (56px under 600px)
  card-padding: 20-24px

elevation:
  card: "1px solid line, no shadow"
  card-hover: "border blue + 0 16px 32px -24px rgba(15,26,51,.5)"
  floating: "0 30px 60px -40px rgba(15,26,51,.45)"   # calculator, menus, dialog

breakpoints: [1040px, 820px, 600px]
---

# Atlas Data design system

Source of truth for the look of atlas-data.fr. Tokens live in `assets/site.css` (city and neighbourhood
pages), in the inline `<style>` of `scripts/templates/home.html` and of `dashboard.html`, and shared
components in `assets/components.css`. When a token changes here, change it in all three.

## Principles

1. **The number is the hero.** Each page leads with one figure in Archivo 800, blue, tabular. Supporting
   figures are ink. Never more than one blue headline number per view.
2. **Say where it comes from.** Every figure sits near its source line: date of the weekly snapshot,
   number of listings, "prix demandés, pas prix de vente". Never show a median without its sample size.
3. **Small samples are flagged, not hidden.** Under 15 listings: neutral dashed pill "Échantillon réduit"
   (grey, never orange or red; it is information, not an error). Under 8 listings: no median published.
4. **Colour means direction, not decoration.** Blue = the data. Terracotta (`clay`) = above the city
   median. Green = below it, or "there are listings at this price". No other accent colours.
5. **Explain the gap.** When a calculation is theoretical (no listing at that price), say so in the
   result itself, with the cheapest real price. Never let two statements on screen contradict each other.

## Components

- **Buttons**: 48px high, 6px radius, Roboto 700 15px. Primary = blue fill. Ghost = white with
  `line-strong` border, ink border on hover. Header CTA = navy fill. Full width under 600px.
- **Chips** (neighbourhood picker): pill, 1px `line` border, ink fill when selected. Above 10 neighbourhoods, a select replaces the chips under 600px, and the « same budget » list shows 8 rows then folds the rest.
- **Segmented control** (city picker, chart mode): `soft` track with 3px padding, selected segment white
  with a 1px shadow.
- **Key-figure tiles**: white, 1px `line`, 12px radius; label 13px muted above or below a 28-40px figure.
- **Ranking bars**: 10px bars on a `soft` track. Blue when every bar is equal; `blue-soft` for the others
  and blue for the current one on a neighbourhood page. A dashed ink line marks the city median, with a
  legend in the card foot.
- **Dot plot**: 10px blue dots at 55% opacity, outliers hollow, median as a 2px ink line with label.
- **Result box** (calculator): `clay-tint` when no listing matches, `green-tint` when some do; bold
  first sentence, then one plain-language explanation, then a link to the matching listings.
- **Cards**: white, 1px `line`, 12px radius, `soft` foot strip for captions and legends.
- **Relevé ticket** (home hero): white card, 14px radius, floating shadow. Mono label row on top
  ("Relevé hebdomadaire" in blue, source in faint), then title and intro; table with mono uppercase
  heads, mono tabular figures and dashed `line-strong` row dividers; total row on `tint`; source line
  in the foot.
- **Offer comparison table** (home, navy Pro band): white panel, 14px radius, scrolls horizontally
  under its min width. Columns: criterion (muted) / Gratuit / Atlas Data Pro. The Pro header is blue
  with white text, Pro cells on `tint`. "Oui" carries a blue check, "Non" is `faint` text, never red.
  Price row in Archivo 800. Actions in the foot row: primary button for Pro, plain link for free.
  Other offers (Sur mesure, Développeurs) stay as text blocks under the table.
- **Header**: sticky, white at 96% with blur, 68px. Nav: Calculer mon budget, Villes (dropdown listing
  every city with its median), Offres, Méthode. On mobile, a "Prix par ville" group in the menu.
- **Footer and Pro band**: navy background, `#c9cfdc` text, white headings.
- **Dialog** (Pro request): 14px radius, navy 55% backdrop, labelled fields 44px high, 16px text so iOS
  does not zoom.

- **Touch targets**: every control is at least 44px high (buttons, presets, inputs, segmented controls); links in table headers, breadcrumbs and the footer get vertical padding so their tap area reaches 44px.
- **Scrolling charts and tables** on mobile say so in visible text ("faites glisser"), never only by being cut off.

## Voice

French, plain, precise. "Prix demandé" not "prix". Dates in full ("19 octobre 2026"). Figures with a
non-breaking space as thousands separator and a non-breaking space before `%`, `?`, `:` and `MAD/m²`.

## Do / don't

- Do keep one idea per section: heading, one paragraph, one visual.
- Do link every neighbourhood name to its page, and every count to the filtered dashboard.
- Don't add stock photos, gradients behind data, or a second accent colour.
- Don't round medians in figures; round only in sentences ("environ 23 000 MAD").
- Don't hide a limitation in a tooltip only; tooltips may repeat, never replace, visible text.
