# tienelicencia.com

**¿Tiene licencia?** A free, public-information site about tourist flats in Andalucía: which ones are registered with the
Junta de Andalucía, where they concentrate, and how many Airbnb listings don't display a valid registration number.
Spanish by default, with English.

- **Every registered tourist flat** in Andalucía, from the Junta's open register: a map for each province and city,
  search by address or licence number, and the share of homes that are tourist flats.
- **Airbnb listings checked against the register:** every listing in Málaga and Sevilla (from Inside Airbnb, re-checked
  live), and a random sample of 1,000 in Marbella, Granada, Córdoba and Cádiz.
- **Check any advert** yourself, and the **law by area** with official sources.

"Doesn't display a valid number" is a mismatch with the register, not proof that a flat lacks a permit. We publish
problems only aggregated by area, never individual listings.

Built and maintained free of charge by [Shifted Labs](https://shiftedlabs.ai). No advertising, no commercial purpose.
Questions, corrections and suggestions: [tienelicencia.com/contacto](https://tienelicencia.com/contacto).

## How it works

| Path | What |
|---|---|
| `site/` | The static site (Netlify). `site/data/` is generated: one folder per area. |
| `netlify/functions/` | `/api/search`, `/api/building`, `/api/suggest`, `/api/check` (reads the register into memory; no database). |
| `pipeline/site_build.py` | `refresh` (download sources), `recheck` (live-check Airbnb listings), `sample` (a town's random sample), `build` (write `site/data`). Areas are defined in `AREAS`. |
| `pipeline/rta_audit/` | Number parsing and matching (`codes.py`, `classify.py`), register, Catastro, INE, Inside Airbnb, Airbnb search. |
| `docs/law-sources.md` | The legal research behind the "law by area" sections, with official sources. |
| `.github/workflows/` | The daily refresh (one job per city) and the quarterly town samples. |

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
