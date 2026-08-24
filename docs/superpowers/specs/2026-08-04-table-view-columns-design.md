# Table view: chosen columns, mobile scrolling, price triple

**Date:** 2026-08-04
**Status:** approved

## Problem

The table view has seven hard-coded columns and drops them by viewport width:
below 900px grape and price vanish, below 700px region too, below 500px also
the vintage - leaving type, name and quantity. The user cannot influence this,
and on a phone the table is nearly empty.

Three requirements:

1. The user picks which columns are shown, instead of the width deciding.
2. Wide tables must stay usable on a phone.
3. Prices: their own price, the AI price, and an effective price that prefers
   their own and falls back to the AI price.

## Current state

`renderTableView()` in `app/templates/index.html` (line ~341) builds the table
from `card.dataset` of the rendered cards. Column hiding lives in
`app/static/style.css` (lines ~697-714) as four media queries.

The dataset carries: `name, winery, year, type, region, country, quantity,
rating, vivino_rating, notes, description, image, purchased_at, price,
drink_from, drink_until, location, grape, category, cask, bottler, abv,
age_years, vivino_id, bottle_format`.

`price` is the user's own price (quantity-weighted average of their purchase
lots). **`ai_price` is absent from the dataset** - it exists only in the detail
view, which reads the wine JSON.

The advanced filter (`app/static/filter-advanced.js`) reads values via
`cardValue(ds, fieldKey) { return ds[fieldKey]; }` - a plain dataset lookup, no
computation. Sorting uses `data-sort` keys on the `<th>` elements.

## Decisions

| Question | Decision |
|---|---|
| Column choice per area? | **Separate** for cellar and bar |
| Mobile | **Horizontal scroll**, type + name stay pinned left |
| Effective price scope | Column **plus sorting and filtering**; statistics untouched |

## Column catalogue

`Typ` and `Name` are fixed: they identify the row and form the pinned pair on
mobile. Everything else is selectable.

| Group | Columns (dataset key) |
|---|---|
| Wine | `year`, `region`, `country`, `grape`, `winery`, `drink_until` |
| Spirits | `age_years`, `abv`, `cask`, `bottler` |
| Price | `price` (own), `ai_price`, `price_effective` |
| General | `quantity`, `rating`, `vivino_rating`, `location`, `bottle_format`, `purchased_at` |

Nineteen selectable columns.

### Defaults

- **Cellar:** `year, region, grape, price_effective, quantity`
  (today's set, with the effective price replacing the plain price)
- **Bar:** `age_years, abv, cask, price_effective, quantity`

Defaults apply when nothing is stored yet, and are what "Reset" restores.

## Effective price

Computed as: own price, else AI price, else empty.

It is written into the card dataset as `data-price_effective` rather than
computed at read time. Reason: the advanced filter and the sort both read
dataset keys directly, so a stored value makes them work with no special
casing. Two places produce it and must agree:

- server-side in the Jinja card markup: `w['price'] or w['ai_price'] or ''`
- client-side in `updateCardData()` / `renderCard()`, which rebuild a card
  after an AJAX save

`data-ai_price` is added to the dataset in the same two places.

**Statistics and total value stay untouched.** They keep counting only real
purchase prices - folding an AI estimate into the cellar value would inflate it
and make it move whenever the AI finds a new price.

## Picker UI

The view-mode switch lives in the settings modal, so there is no on-page
control to sit next to. Instead a slim toolbar is rendered directly above the
table, inside the grid (`grid-column: 1 / -1`), present only in table mode. It
holds one button ("Spalten") that opens the picker dialog.

The dialog lists the four groups with a checkbox per column, plus a Reset
action. It applies immediately on change (no OK button) so the effect is
visible while choosing - the dialog does not cover the table on desktop.

Storage: `localStorage`, keys `wineTableCols.cellar` and `wineTableCols.bar`,
each a JSON array of column keys in catalogue order. Per device, no server
state. An unknown key in a stored array is ignored, so removing a column from
the catalogue later cannot break the view.

Column order is the catalogue order, not the pick order. Reordering columns is
out of scope.

## Mobile / layout

- The table is wrapped in a container with `overflow-x: auto`.
- `Typ` and `Name` get `position: sticky; left: 0` with an opaque background,
  so they stay readable while the rest scrolls under them.
- The four responsive-hiding media queries are **deleted**. The user's choice
  applies at every width.
- `table-layout: fixed` with fixed pixel widths is replaced by per-column
  `min-width` values. With few columns the table fills the width; with many it
  scrolls cleanly instead of squeezing every column to illegibility.

## Fix taken along the way

The grape cell calls `grapeLead(d.grapes)`, but `data-grapes` does not exist on
the dataset. The call always returns empty and the code silently falls through
to `d.grape`, so the raw comma list is shown instead of "Nebbiolo +2". The
structured grape list is added to the dataset as `data-grapes` (JSON) and
`grapeLead` gets its intended input.

## Testing

Server-side (pytest):
- the card markup carries `data-ai_price`, `data-price_effective`, `data-grapes`
- `price_effective` equals the own price when set, the AI price when the own
  price is empty, and is empty when both are

Browser (Playwright verification script):
- the picker shows all 19 columns grouped, and toggling one adds/removes exactly
  that column
- the choice survives a reload, and cellar and bar keep separate choices
- at 390px width the table scrolls horizontally and type + name stay pinned
  (compare their bounding box before and after scrolling)
- no column is hidden by width any more: a chosen column is present at 390px
- the three price columns show the expected values, including the fallback row
- sorting by `price_effective` orders rows correctly
- the advanced filter offers `ai_price` and `price_effective`

## Out of scope

- Column reordering and per-column width dragging
- A separate phone column set (rejected: four stored selections is a lot of
  management for little gain)
- Changing statistics or the total value
- Column choice for the list/grid/card views - this is the table only
