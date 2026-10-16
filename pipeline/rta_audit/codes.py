"""Parse and normalise registration numbers shown on Airbnb listings.

Separates four kinds of number found in free text:
  a) Junta de Andalucía tourism register codes (VUT/MA/12345, VFT-MA-1234, A/MA/..., H/MA/..., CR/..., VTAR/...)
  b) Spanish national rental registration numbers (Registro Único, ES + 4 letters + ~45 chars)
  c) Other registration types (other regions' codes, CTC procedure references)
  d) Malformed / truncated Junta-style numbers (kept as their own flag)

Normalised key: "<TYPE>/<PROV>/<int number>" with VFT folded into VUT and leading
zeros dropped, so "VFT/MA/08150", "vut-ma-8150" and "VUT/MA/08150" share a key.
The register's own code is normalised the same way (see register.py).
"""
import html as _html
import re

ANDALUSIAN_PROVINCES = {"AL", "CA", "CO", "GR", "HU", "JA", "MA", "SE"}

# Junta accommodation/tourism prefixes seen in OpenRTA registration_code, plus VFT (old name of VUT)
# and VTF (a common typo). Canonical form on the right.
PREFIXES = {
    "VUT": "VUT", "VFT": "VUT", "VTF": "VUT",
    "VTAR": "VTAR", "A": "A", "H": "H", "CR": "CR", "CTR": "CTR", "CM": "CM",
}
# Order matters: longest first so "VTAR" wins over "A"
_PREFIX_RE = "|".join(sorted(PREFIXES, key=len, reverse=True))
_SEP = r"[\s/\-_.\\]*"

JUNTA_RE = re.compile(
    rf"(?<![A-Z0-9])(?P<prefix>{_PREFIX_RE}){_SEP}(?:(?P<prov>[A-Z]{{2}}){_SEP})?(?P<num>\d{{1,8}})(?P<suffix>[A-Z])?(?![0-9])",
    re.IGNORECASE,
)
# Registro Único de Arrendamientos: ES + 4 letters + long tail (digits, sometimes with the
# regional code embedded at the end, e.g. ...0000VUT/MA/117055).
NATIONAL_RE = re.compile(r"(?<![A-Z0-9])ES[A-Z]{4}\d{10,}[0-9A-Z/\-]*", re.IGNORECASE)
CTC_RE = re.compile(r"(?<![A-Z0-9])CTC[\s\-_/]*(\d{6,12})(?![0-9])", re.IGNORECASE)
EXEMPT_RE = re.compile(r"\b(exempt|exento|exenta)\b[^|\n]*", re.IGNORECASE)
LABEL_RE = re.compile(
    r"(Andaluc[ií]a|Spain|Espa[ñn]a)\s*[–-]\s*(Regional|National|Nacional|Auton[oó]mic\w*)\s+registration\s+number",
    re.IGNORECASE,
)


def clean_text(raw):
    """HTML fragment -> plain text with ' | ' line separators."""
    if not raw:
        return ""
    s = re.sub(r"<br\s*/?>", " | ", raw, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s).replace(" ", " ")
    return re.sub(r"[ \t]+", " ", s).strip()


def normalise_key(prefix, prov, num):
    return f"{PREFIXES.get(prefix.upper(), prefix.upper())}/{(prov or '??').upper()}/{int(num)}"


def parse_national(token):
    """Return dict for a Registro Único number. 'ESFCTU' = tourist use, 'ESFCNT' = non-tourist."""
    t = token.upper()
    embedded = None
    m = re.search(r"(VUT|VFT|VTAR|CR|A|H)/[A-Z]{2}/\d+$", t)
    if m:
        embedded = m.group(0)
    return {"raw": token, "type": t[2:6], "embedded_regional": embedded}


def parse(raw_text, max_issued=None):
    """Parse a licence/registration text.

    max_issued: optional dict {(canonical_prefix, prov): highest number in register}
                used to mark impossible (not-yet-issued) numbers as malformed.
    Returns dict with junta (list), national (list), other (list), exempt_text, clean.
    Each junta item: raw, prefix, prov, num, key, malformed (bool), problems (list), andalusian (bool).
    """
    text = clean_text(raw_text)
    out = {"clean": text, "junta": [], "national": [], "other": [], "exempt_text": None}

    work = text
    for m in NATIONAL_RE.finditer(text):
        out["national"].append(parse_national(m.group(0)))
        work = work.replace(m.group(0), " ")
    for m in CTC_RE.finditer(work):
        out["other"].append({"raw": m.group(0), "kind": "CTC_procedure_ref", "value": m.group(1)})
        work = work.replace(m.group(0), " ")
    work = LABEL_RE.sub(" ", work)

    for m in JUNTA_RE.finditer(work):
        prefix, prov, num, suffix = m.group("prefix"), m.group("prov"), m.group("num"), m.group("suffix")
        canon = PREFIXES[prefix.upper()]
        # Single-letter prefixes (A, H) only count when a province follows, else too ambiguous
        if len(prefix) == 1 and not prov:
            continue
        problems = []
        if prov and prov.upper() not in ANDALUSIAN_PROVINCES:
            if canon != "VUT":
                out["other"].append({"raw": m.group(0), "kind": "non_andalusian_province", "value": prov.upper()})
                continue
            # VUT/VFT is Andalusian terminology; a bad province is a malformed Junta-style number
            problems.append(f"invalid_province_{prov.upper()}")
        if prefix.upper() == "VTF":
            problems.append("prefix_typo_VTF")
        if not prov:
            problems.append("missing_province")
        if suffix:
            problems.append("letter_suffix")
        if len(num) > 6:
            problems.append("too_many_digits")
        if len(num) < 5 and len(num.lstrip("0")) == len(num):
            problems.append("short_unpadded")
        if max_issued and prov:
            hi = max_issued.get((canon, prov.upper()))
            if hi and int(num) > hi:
                problems.append("exceeds_highest_issued")
        # Formatting-only issues (typo prefix, short unpadded) are variants, not malformation.
        hard = {"missing_province", f"invalid_province_{(prov or '').upper()}", "letter_suffix", "too_many_digits", "exceeds_highest_issued"}
        out["junta"].append({
            "raw": m.group(0).strip(),
            "prefix": prefix.upper(), "canonical_prefix": canon,
            "prov": (prov or "").upper() or None, "num": num, "suffix": suffix,
            "key": normalise_key(prefix, prov if prov and prov.upper() in ANDALUSIAN_PROVINCES else "MA", num)
            if prov or canon == "VUT" else None,
            "problems": problems,
            "malformed": bool(hard & set(problems)),
        })

    # Digits-only numbers in a registration section (e.g. "Regional registration number | 29123")
    leftover = JUNTA_RE.sub(" ", work)
    for m in re.finditer(r"(?<![A-Z0-9/])(\d{4,7})(?![0-9])", leftover, re.IGNORECASE):
        out["junta"].append({
            "raw": m.group(1), "prefix": None, "canonical_prefix": None, "prov": None, "num": m.group(1),
            "suffix": None, "key": None, "problems": ["digits_only"], "malformed": True,
        })

    e = EXEMPT_RE.search(text)
    if e:
        out["exempt_text"] = e.group(0).strip(" |")
    # de-duplicate by raw/key
    seen, uniq = set(), []
    for j in out["junta"]:
        k = j["key"] or j["raw"]
        if k not in seen:
            seen.add(k)
            uniq.append(j)
    out["junta"] = uniq
    return out


def variants(item):
    """Candidate register keys for a parsed junta item, in priority order: (key, variant_name)."""
    c = []
    num, prov, canon = item["num"], item["prov"], item["canonical_prefix"]
    if canon is None:
        # digits only: try as VUT/MA
        if num and 1 <= len(num) <= 6:
            c.append((normalise_key("VUT", "MA", num), "digits_only_assumed_VUT_MA"))
        return c
    valid_prov = prov in ANDALUSIAN_PROVINCES
    p = prov if valid_prov else "MA"
    base = "exact" if valid_prov else ("province_replaced_MA" if prov else "province_inferred_MA")
    if item["prefix"] == "VFT":
        base = "prefix_swap_VFT_to_VUT" if base == "exact" else base + "+prefix_swap_VFT_to_VUT"
    if item["prefix"] == "VTF":
        base = "prefix_typo_VTF_to_VUT" if base == "exact" else base + "+prefix_typo_VTF_to_VUT"
    if len(num) < 5:
        base += "+zero_pad"
    c.append((normalise_key(canon, p, num), base))
    # 6/7-digit number may carry the national-number check digit (Registro Único appends one)
    if len(num) >= 6:
        c.append((normalise_key(canon, p, num[:-1]), base + "+check_digit_stripped"))
    # Holders sometimes show VUT for a register entry filed as VTAR / A, or vice versa
    if canon == "VUT":
        c.append((normalise_key("VTAR", p, num), base + "+prefix_swap_VUT_to_VTAR"))
    return c
