# tienelicencia.com

**¿Tiene licencia?** A free, public-information site about tourist flats in Spain: which ones are registered with each
region's tourism register, where they concentrate, and how many Airbnb listings don't display a valid registration number.
Spanish by default, with English.

- **The tourist-housing pressure index** for every Spanish city over 300,000 inhabitants (13 cities): homes advertised,
  concentration in the most affected area and registration discrepancies, against a fixed October 2026 baseline, monthly.
- **Every registered tourist flat** in the areas we cover (Andalucía, Madrid, Barcelona, Mallorca, Valencia, Alicante,
  Bilbao, San Sebastián, Zaragoza, Murcia, Las Palmas, Valladolid): maps, search by address or licence number, and the
  share of homes that are tourist flats.
- **Airbnb listings checked against the registers:** every listing where Inside Airbnb publishes data (re-checked live),
  and a random sample of each city's complete listing list elsewhere.
- **Check any advert** yourself, and the **law by area** with official sources.

"Doesn't display a valid number" is a mismatch with the register, not proof that a flat lacks a permit. We publish
problems only aggregated by area, never individual listings.

Built and maintained free of charge by [Shifted Labs](https://shiftedlabs.ai). No advertising, no commercial purpose.
Questions, corrections and suggestions: [tienelicencia.com/contacto](https://tienelicencia.com/contacto) or hola@shiftedlabs.ai.

## Using the data

Everything in `site/data/` is published under [CC BY 4.0](DATA_LICENSE.md): reuse it, citing "tienelicencia.com" and the
date of the data. The files are rebuilt every day, so this repository's history is also the history of the data.

| File | What |
|---|---|
| `site/data/ranking.json` | The index: every city's score, its three components, the sample behind it and the calculation. |
| `site/data/index_history.json` | One snapshot of the index per month. |
| `site/data/areas.json` | Every area with its key figures. |
| `site/data/<area>/summary.json` | Every figure for one area (registered flats, share of homes, listings, barrios, buildings). |
| `site/data/<area>/zonas.csv` | The area's table by barrio, postcode or municipality (opens in Excel). |
| `site/data/history.json` | Registered flats per area, day by day. |

Ideas: chart the index month by month; compare your barrio with the rest of your city; join `zonas.csv` with census or
rent data. The method, with its limits, is at [tienelicencia.com/metodologia](https://tienelicencia.com/metodologia).
Found a mistake? Open an issue.

## How it works

| Path | What |
|---|---|
| `site/` | The static site (Netlify). `site/data/` is generated: one folder per area. |
| `netlify/functions/` | `/api/search`, `/api/building`, `/api/suggest`, `/api/check` (reads the register into memory; no database). |
| `pipeline/site_build.py` | `refresh` (download sources), `recheck` (live-check Airbnb listings), `sample` (a town's random sample), `build` (write `site/data`). Areas are defined in `AREAS`. |
| `pipeline/rta_audit/` | Number parsing and matching (`codes.py`, `classify.py`), each region's register module, Catastro, INE, Inside Airbnb, Airbnb search, and the index (`index.py`). |
| `pipeline/index_config.json` | The index's versioned settings: cities, weights, severities, baseline. |
| `docs/law-sources.md` | The legal research behind the "law by area" sections, with official sources. |
| `.github/workflows/` | `1 · Sources` (daily open-data downloads into a shared cache), `2a · Airbnb re-checks` (daily, every listing about once a month), `2b · Town samples` (monthly; both write to the private state repo) and `3 · Build site` (rebuilds and commits the site data after either). |

The method in plain language, with its limits: [tienelicencia.com/metodologia](https://tienelicencia.com/metodologia).

Per-listing check results (which include Airbnb host identifiers) are kept in a private repository and are not published.

## Run it locally

```bash
cd pipeline && pip install requests openpyxl
python3 site_build.py refresh     # downloads the register, Inside Airbnb, Catastro, INE (a few minutes)
python3 site_build.py build       # writes site/data and the function data
cd .. && node dev.mjs             # http://localhost:8791
```

Tests: `cd pipeline && python3 -m unittest discover -s tests` and `node netlify/functions/test.mjs`.

## Licence

Code: [MIT](LICENSE). Published data: [CC BY 4.0](DATA_LICENSE.md), citing "tienelicencia.com".
