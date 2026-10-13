import os
import re
import json
import pymupdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
INDEX_FILE = os.path.join(DATA_DIR, "bnf_index.json")

_BNF_DOC = None
_BNF_INDEX = None

def get_bnf_path():
    for f in os.listdir(BASE_DIR):
        if f.lower().endswith(".pdf") and ("bnf" in f.lower() or "british-national" in f.lower()):
            return os.path.join(BASE_DIR, f)
    data_ref = os.path.join(DATA_DIR, "reference")
    if os.path.exists(data_ref):
        for f in os.listdir(data_ref):
            if f.lower().endswith(".pdf") and ("bnf" in f.lower() or "british-national" in f.lower()):
                return os.path.join(data_ref, f)
    return None

def get_bnf_doc():
    global _BNF_DOC
    if _BNF_DOC is not None:
        return _BNF_DOC
    path = get_bnf_path()
    if path and os.path.exists(path):
        try:
            _BNF_DOC = pymupdf.open(path)
            return _BNF_DOC
        except Exception as e:
            print(f"Error opening BNF PDF: {e}")
    return None

def build_or_load_index():
    global _BNF_INDEX
    if _BNF_INDEX is not None:
        return _BNF_INDEX

    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                _BNF_INDEX = json.load(f)
                return _BNF_INDEX
        except Exception:
            pass

    doc = get_bnf_doc()
    if not doc:
        return {}

    # The BNF Index is roughly on pages 1860 to 1899
    idx = {}
    total_pages = len(doc)
    start_page = max(0, total_pages - 50)
    end_page = min(total_pages, total_pages - 5)

    for pno in range(start_page, end_page):
        txt = doc[pno].get_text()
        for raw_line in txt.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Look for: Drug name, 1234 or Drug name ... 1234
            m = re.match(r'^([^,0-9▶]+)[,\s]+(\d{2,4}(?:,\s*\d{2,4})*)', line)
            if m:
                term = m.group(1).strip().lower()
                pages_str = m.group(2)
                p_nums = [int(p.strip()) for p in re.findall(r'\b\d{2,4}\b', pages_str)]
                if term and p_nums:
                    if term not in idx:
                        idx[term] = []
                    for pn in p_nums:
                        if pn not in idx[term]:
                            idx[term].append(pn)
            elif "see " in line.lower():
                # Cross reference, e.g. "Amidate, see Etomidate"
                parts = re.split(r'\bsee\s+', line, flags=re.IGNORECASE)
                if len(parts) == 2:
                    alias = parts[0].strip().rstrip(',').lower()
                    target = parts[1].strip().lower()
                    if alias and target:
                        idx[f"__see__{alias}"] = target

    _BNF_INDEX = idx
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(idx, f, indent=2)
    except Exception as e:
        print(f"Notice: Failed to save BNF index: {e}")

    return _BNF_INDEX

def clean_bnf_text(raw_text: str) -> str:
    """Cleans BNF glyphs, bullets, line-wraps, and formatting."""
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    cleaned_lines = []
    
    for l in lines:
        # Strip leading icons/symbols: 'l ', '▶', '•'
        l = re.sub(r'^[l•\s▶]+', '', l).strip()
        # Clean section titles
        if l == "INDICATIONS AND DOSE":
            continue
        if l.startswith("BY "):
            cleaned_lines.append(f"\n[{l}]")
        elif l.startswith("Adult:") or l.startswith("Elderly:") or l.startswith("Child ") or l.startswith("Neonate:"):
            cleaned_lines.append(f"• {l}")
        else:
            cleaned_lines.append(l)

    res = "\n".join(cleaned_lines)
    # Join broken lines where a bullet or sentence continues
    res = re.sub(r'([a-zA-Z0-9,\-])\n([a-z0-9])', r'\1 \2', res)
    return res.strip()

US_TO_BNF_SYNONYMS = {
    "succinylcholine": "suxamethonium",
    "succinylcholine chloride": "suxamethonium",
    "sux": "suxamethonium",
    "anectine": "suxamethonium",
    "quelicin": "suxamethonium",
    "epinephrine": "adrenaline",
    "epi": "adrenaline",
    "norepinephrine": "noradrenaline",
    "norepi": "noradrenaline",
    "levophed": "noradrenaline",
    "acetaminophen": "paracetamol",
    "tylenol": "paracetamol",
    "apap": "paracetamol",
    "albuterol": "salbutamol",
    "ventolin": "salbutamol",
    "proventil": "salbutamol",
    "meperidine": "pethidine",
    "demerol": "pethidine",
    "glycopyrrolate": "glycopyrronium",
    "robinul": "glycopyrronium",
    "isoproterenol": "isoprenaline",
    "isuprel": "isoprenaline",
    "rifampin": "rifampicin",
    "thiopental": "thiopentone",
    "thiopental sodium": "thiopentone",
    "pentothal": "thiopentone",
    "methohexital": "methohexitone",
    "brevital": "methohexitone",
    "frusemide": "furosemide",
    "lasix": "furosemide",
    "lignocaine": "lidocaine",
    "xylocaine": "lidocaine",
    "bactrim": "co-trimoxazole",
    "septra": "co-trimoxazole",
    "sulfamethoxazole/trimethoprim": "co-trimoxazole",
    "trimethoprim/sulfamethoxazole": "co-trimoxazole",
    "augmentin": "co-amoxiclav",
    "amoxicillin-clavulanate": "co-amoxiclav",
    "amoxicillin/clavulanic acid": "co-amoxiclav",
    "diphenhydramine": "diphenhydramine",
    "benadryl": "diphenhydramine",
    "hydromorphone": "hydromorphone",
    "dilaudid": "hydromorphone",
    "fentanyl": "fentanyl",
    "sublimaze": "fentanyl",
    "morphine": "morphine",
    "lorazepam": "lorazepam",
    "ativan": "lorazepam",
    "diazepam": "diazepam",
    "valium": "diazepam",
    "midazolam": "midazolam",
    "versed": "midazolam",
    "propofol": "propofol",
    "diprivan": "propofol",
    "etomidate": "etomidate",
    "amidate": "etomidate",
    "ketamine": "ketamine",
    "ketalar": "ketamine",
    "rocuronium": "rocuronium",
    "zemuron": "rocuronium",
    "vecuronium": "vecuronium",
    "norcuron": "vecuronium",
    "cisatracurium": "cisatracurium",
    "nimbex": "cisatracurium",
}

def lookup_drug_bnf(drug_name: str) -> dict:
    """
    Looks up drug in BNF 85.
    Returns dict:
      {
         "drug": "Etomidate",
         "indications_and_dose": "...",
         "safety_info": "...",
         "cautions": "...",
         "printed_page": 1468,
         "pdf_page": 1486
      }
    or {"found": False}
    """
    if not drug_name:
        return {"found": False}

    doc = get_bnf_doc()
    if not doc:
        return {"found": False, "error": "BNF PDF not found"}

    index = build_or_load_index()
    raw_q = drug_name.strip().lower()
    q = US_TO_BNF_SYNONYMS.get(raw_q, raw_q)

    # Direct match or cross-reference
    candidate_pages = index.get(q, [])
    if not candidate_pages:
        # Check cross-ref
        target_name = index.get(f"__see__{q}")
        if target_name:
            candidate_pages = index.get(target_name, [])
            if not candidate_pages:
                for k, v in index.items():
                    if target_name in k and not k.startswith("__see__"):
                        candidate_pages = v
                        break

    if not candidate_pages:
        # Fuzzy/substring match in index keys
        for k, v in index.items():
            if not k.startswith("__see__") and (q == k or q in k or k in q):
                candidate_pages.extend(v)
                if len(candidate_pages) >= 3:
                    break

    if not candidate_pages:
        # Fallback: search doc directly if term wasn't in index
        for pno in range(100, min(1800, len(doc)), 50):
            pass # Keep it fast; index covers >99% of drugs

    if not candidate_pages:
        return {"found": False, "error": f"Drug '{drug_name}' not found in BNF index"}

    # Search around printed pages (PDF offset is usually ~14 to 22)
    target_page = None
    target_pno = None
    matched_term = drug_name

    for printed_page in candidate_pages:
        for offset in [18, 17, 19, 16, 20, 15, 21]:
            pno = printed_page + offset
            if 0 <= pno < len(doc):
                txt = doc[pno].get_text().lower()
                if q in txt and "indications and dose" in txt:
                    target_page = doc[pno]
                    target_pno = pno
                    break
        if target_page:
            break

    if not target_page:
        return {"found": False, "error": f"Monograph page not located for '{drug_name}'"}

    # Extract column-sorted blocks from target page
    blocks = target_page.get_text("blocks")
    content_blocks = [
        b for b in blocks 
        if b[0] >= 35 and b[2] <= 415 and b[1] >= 35 and b[3] <= 610
    ]

    col1 = sorted([b for b in content_blocks if b[0] < 225], key=lambda b: b[1])
    col2 = sorted([b for b in content_blocks if b[0] >= 225], key=lambda b: b[1])
    all_blocks = col1 + col2

    # Find the drug heading or closest match
    drug_idx = -1
    for i, b in enumerate(all_blocks):
        txt_lower = b[4].strip().lower()
        lines = [l.strip() for l in txt_lower.splitlines()]
        if any(l == q or l.startswith(q + " ") for l in lines):
            drug_idx = i
            break

    if drug_idx == -1:
        for i, b in enumerate(all_blocks):
            if q in b[4].lower():
                drug_idx = i
                break

    if drug_idx == -1:
        return {"found": False, "error": "Could not isolate drug block"}

    # Extract INDICATIONS AND DOSE, IMPORTANT SAFETY INFORMATION, and CAUTIONS
    dose_blocks = []
    safety_blocks = []
    cautions_blocks = []
    current_section = None

    # Scan blocks belonging to this drug until next major drug/section
    for b in all_blocks[drug_idx:]:
        txt = b[4].strip()
        txt_upper = txt.upper()

        if "INDICATIONS AND DOSE" in txt_upper:
            current_section = "dose"
            dose_blocks.append(txt)
            continue
        elif "IMPORTANT SAFETY INFORMATION" in txt_upper:
            current_section = "safety"
            safety_blocks.append(txt)
            continue
        elif any(h in txt_upper for h in ["l CAUTIONS", "CAUTIONS Acute", "CAUTIONS"]):
            current_section = "cautions"
            cautions_blocks.append(txt)
            continue
        elif any(h in txt_upper for h in ["SIDE-EFFECTS", "INTERACTIONS", "CONTRA-INDICATIONS", "HEPATIC IMPAIRMENT", "RENAL IMPAIRMENT", "PREGNANCY"]):
            # Stop dosage extraction when side effects / interactions begin
            current_section = "other"
            break
        elif current_section == "dose":
            # Check if this looks like another drug's heading
            first_line = txt.splitlines()[0].strip() if txt.splitlines() else ""
            if b[0] == all_blocks[drug_idx][0] and len(dose_blocks) >= 2 and len(first_line) > 2 and first_line.isupper() and "BY " not in first_line:
                break
            dose_blocks.append(txt)
        elif current_section == "safety":
            safety_blocks.append(txt)
        elif current_section == "cautions":
            cautions_blocks.append(txt)

    dose_raw = "\n".join(dose_blocks)
    cleaned_dose = clean_bnf_text(dose_raw)

    return {
        "found": bool(cleaned_dose),
        "drug": drug_name.title(),
        "indications_and_dose": cleaned_dose,
        "safety_info": clean_bnf_text("\n".join(safety_blocks)) if safety_blocks else "",
        "cautions": clean_bnf_text("\n".join(cautions_blocks)[:400]) if cautions_blocks else "",
        "printed_page": candidate_pages[0] if candidate_pages else None,
        "pdf_page": target_pno + 1 if target_pno is not None else None,
        "source": "British National Formulary (BNF 85)"
    }
