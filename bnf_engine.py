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
    "roc": "rocuronium bromide",
    "rocuronium": "rocuronium bromide",
    "rocuronium bromide": "rocuronium bromide",
    "zemuron": "rocuronium bromide",
    "vec": "vecuronium bromide",
    "vecuronium": "vecuronium bromide",
    "vecuronium bromide": "vecuronium bromide",
    "norcuron": "vecuronium bromide",
    "cis": "cisatracurium",
    "cisatracurium": "cisatracurium",
    "nimbex": "cisatracurium",
    "sux": "suxamethonium chloride",
    "succs": "suxamethonium chloride",
    "succinylcholine": "suxamethonium chloride",
    "succinylcholine chloride": "suxamethonium chloride",
    "suxamethonium": "suxamethonium chloride",
    "suxamethonium chloride": "suxamethonium chloride",
    "anectine": "suxamethonium chloride",
    "quelicin": "suxamethonium chloride",
    "atropine": "atropine sulfate",
    "atropine sulfate": "atropine sulfate",
    "epinephrine": "adrenaline/epinephrine",
    "epi": "adrenaline/epinephrine",
    "adrenaline": "adrenaline/epinephrine",
    "adrenaline/epinephrine": "adrenaline/epinephrine",
    "norepinephrine": "noradrenaline/norepinephrine",
    "norepi": "noradrenaline/norepinephrine",
    "noradrenaline": "noradrenaline/norepinephrine",
    "noradrenaline/norepinephrine": "noradrenaline/norepinephrine",
    "levophed": "noradrenaline/norepinephrine",
    "acetaminophen": "paracetamol",
    "tylenol": "paracetamol",
    "apap": "paracetamol",
    "paracetamol": "paracetamol",
    "albuterol": "salbutamol",
    "ventolin": "salbutamol",
    "proventil": "salbutamol",
    "salbutamol": "salbutamol",
    "meperidine": "pethidine",
    "demerol": "pethidine",
    "pethidine": "pethidine",
    "glycopyrrolate": "glycopyrronium bromide",
    "robinul": "glycopyrronium bromide",
    "glycopyrronium": "glycopyrronium bromide",
    "glycopyrronium bromide": "glycopyrronium bromide",
    "isoproterenol": "isoprenaline",
    "isuprel": "isoprenaline",
    "rifampin": "rifampicin",
    "thiopental": "thiopentone sodium",
    "thiopental sodium": "thiopentone sodium",
    "thiopentone": "thiopentone sodium",
    "thiopentone sodium": "thiopentone sodium",
    "pentothal": "thiopentone sodium",
    "methohexital": "methohexitone",
    "brevital": "methohexitone",
    "frusemide": "furosemide",
    "lasix": "furosemide",
    "furosemide": "furosemide",
    "lignocaine": "lidocaine",
    "xylocaine": "lidocaine",
    "lidocaine": "lidocaine",
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
    "amiodarone": "amiodarone hydrochloride",
    "amiodarone hydrochloride": "amiodarone hydrochloride",
}

SPECIAL_DRUG_PAGES = {
    "atropine": [1472],
    "atropine sulfate": [1472],
    "rocuronium": [1477],
    "rocuronium bromide": [1477],
    "suxamethonium": [1475],
    "suxamethonium chloride": [1475],
    "succinylcholine": [1475],
    "noradrenaline": [206],
    "norepinephrine": [206],
    "noradrenaline/norepinephrine": [206],
    "adrenaline": [243],
    "epinephrine": [243],
    "adrenaline/epinephrine": [243],
    "amiodarone": [108],
    "amiodarone hydrochloride": [108],
}

def get_page_content_blocks(page):
    blocks = page.get_text("blocks")
    content_blocks = [
        b for b in blocks 
        if b[0] >= 35 and b[2] <= 415 and b[1] >= 35 and b[3] <= 610
    ]
    col1 = sorted([b for b in content_blocks if b[0] < 225], key=lambda b: b[1])
    col2 = sorted([b for b in content_blocks if b[0] >= 225], key=lambda b: b[1])
    return col1 + col2

def find_drug_heading_block(all_blocks, q):
    date_regex = re.compile(r'\b\d{1,2}-[A-Za-z]{3}-\d{4}\b')
    q_parts = [q] + [p.strip() for p in q.split('/') if p.strip()]

    # Pass 1: Drug heading accompanied by revision date or directly followed by INDICATIONS AND DOSE
    for i, b in enumerate(all_blocks):
        txt = b[4].strip()
        lines = [l.strip().lower() for l in txt.splitlines()]
        if lines:
            for q_term in q_parts:
                if any(l == q_term or l.startswith(q_term + ' ') or l.startswith(q_term + '/') or q_term in l for l in lines):
                    if date_regex.search(txt) or (i + 1 < len(all_blocks) and 'indications and dose' in all_blocks[i+1][4].lower()):
                        return i

    # Pass 2: Block immediately preceding 'INDICATIONS AND DOSE'
    for i, b in enumerate(all_blocks):
        if 'indications and dose' in b[4].lower():
            for q_term in q_parts:
                if i > 0 and q_term in all_blocks[i-1][4].lower():
                    return i - 1
                if q_term in b[4].lower():
                    return i

    # Pass 3: Exact line matches
    for i, b in enumerate(all_blocks):
        lines = [l.strip().lower() for l in b[4].splitlines()]
        for q_term in q_parts:
            if any(l == q_term or l.startswith(q_term + '/') or l.startswith(q_term + ' ') for l in lines):
                return i

    return -1

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

    # Check SPECIAL_DRUG_PAGES first
    candidate_pages = SPECIAL_DRUG_PAGES.get(raw_q) or SPECIAL_DRUG_PAGES.get(q) or index.get(q, [])

    if not candidate_pages:
        # Check cross-ref
        target_name = index.get(f"__see__{q}")
        if target_name:
            candidate_pages = SPECIAL_DRUG_PAGES.get(target_name) or index.get(target_name, [])
            if not candidate_pages:
                for k, v in index.items():
                    if target_name in k and not k.startswith("__see__"):
                        candidate_pages = v
                        break

    if not candidate_pages:
        # Substring / exact match in index keys (avoid small substrings < 4 to prevent collisions like 'roc' -> 'abrocitinib')
        for k, v in index.items():
            if not k.startswith("__see__"):
                if q == k or (len(q) >= 4 and (q in k or k in q)):
                    candidate_pages.extend(v)
                    if len(candidate_pages) >= 3:
                        break

    if not candidate_pages:
        return {"found": False, "error": f"Drug '{drug_name}' not found in BNF index"}

    # Search around printed pages (PDF offset is usually ~14 to 22)
    target_page = None
    target_pno = None
    q_parts = [q] + [p.strip() for p in q.split('/') if p.strip()]

    for printed_page in candidate_pages:
        for offset in [18, 17, 19, 16, 20, 15, 21]:
            pno = printed_page + offset
            if 0 <= pno < len(doc):
                txt = doc[pno].get_text().lower()
                if any(qp in txt for qp in q_parts) and "indications and dose" in txt:
                    target_page = doc[pno]
                    target_pno = pno
                    break
        if target_page:
            break

    if not target_page:
        return {"found": False, "error": f"Monograph page not located for '{drug_name}'"}

    # Extract column-sorted blocks from target page
    all_blocks = get_page_content_blocks(target_page)
    drug_idx = find_drug_heading_block(all_blocks, q)

    if drug_idx == -1:
        return {"found": False, "error": "Could not isolate drug block"}

    # Extract INDICATIONS AND DOSE, IMPORTANT SAFETY INFORMATION, and CAUTIONS
    dose_blocks = []
    safety_blocks = []
    cautions_blocks = []
    current_section = None
    stop_headings = [
        "SIDE-EFFECTS", "INTERACTIONS", "CONTRA-INDICATIONS", 
        "HEPATIC IMPAIRMENT", "RENAL IMPAIRMENT", "PREGNANCY", 
        "MEDICINAL FORMS", "DIRECTIONS FOR ADMINISTRATION"
    ]

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
        elif any(h in txt_upper for h in stop_headings):
            current_section = "stop"
            break
        elif current_section == "dose":
            # Check if this looks like another drug's heading
            first_line = txt.splitlines()[0].strip() if txt.splitlines() else ""
            if b[0] == all_blocks[drug_idx][0] and len(dose_blocks) >= 2 and len(first_line) > 3 and first_line.isupper() and "BY " not in first_line:
                break
            dose_blocks.append(txt)
        elif current_section == "safety":
            safety_blocks.append(txt)
        elif current_section == "cautions":
            cautions_blocks.append(txt)

    # Multi-page continuation: if section was still 'dose' at page boundary, check next page
    if current_section == "dose" and target_pno + 1 < len(doc):
        next_blocks = get_page_content_blocks(doc[target_pno + 1])
        for b in next_blocks:
            txt = b[4].strip()
            txt_upper = txt.upper()
            if any(h in txt_upper for h in stop_headings) or "IMPORTANT SAFETY INFORMATION" in txt_upper or "UNLICENSED USE" in txt_upper or "CAUTIONS" in txt_upper:
                break
            first_line = txt.splitlines()[0].strip() if txt.splitlines() else ""
            if len(first_line) > 3 and first_line.isupper() and "BY " not in first_line:
                break
            dose_blocks.append(txt)

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
