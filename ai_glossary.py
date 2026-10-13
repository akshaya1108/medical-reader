import os
import json
import re
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv

load_dotenv()

VALID_CATEGORIES = [
    "Anatomy",
    "Pathology / Disease",
    "Concept",
    "Instrument / Device",
    "Drug"
]

CATEGORY_SYNONYMS = {
    "anatomy": "Anatomy",
    "anatomical": "Anatomy",
    "organ": "Anatomy",
    "nerve": "Anatomy",
    "vessel": "Anatomy",
    "bone": "Anatomy",
    "muscle": "Anatomy",
    "structure": "Anatomy",

    "pathology": "Pathology / Disease",
    "disease": "Pathology / Disease",
    "pathology / disease": "Pathology / Disease",
    "pathology/disease": "Pathology / Disease",
    "illness": "Pathology / Disease",
    "syndrome": "Pathology / Disease",
    "disorder": "Pathology / Disease",
    "injury": "Pathology / Disease",
    "infection": "Pathology / Disease",

    "concept": "Concept",
    "concept / lore": "Concept",
    "physiology": "Concept",
    "pathophysiology": "Concept",
    "sign": "Concept",
    "symptom": "Concept",
    "score": "Concept",
    "criteria": "Concept",
    "guideline": "Concept",

    "instrument": "Instrument / Device",
    "device": "Instrument / Device",
    "instrument / device": "Instrument / Device",
    "instrument/device": "Instrument / Device",
    "equipment": "Instrument / Device",
    "tool": "Instrument / Device",
    "catheter": "Instrument / Device",
    "implant": "Instrument / Device",

    "drug": "Drug",
    "medication": "Drug",
    "pharmacology": "Drug",
    "pharmaceutical": "Drug",
    "agent": "Drug",
    "vaccine": "Drug"
}

def normalize_category(cat: str) -> str:
    if not cat:
        return "Concept"
    c_lower = cat.lower().strip()
    if c_lower in CATEGORY_SYNONYMS:
        return CATEGORY_SYNONYMS[c_lower]
    for key, val in CATEGORY_SYNONYMS.items():
        if key in c_lower:
            return val
    return "Concept"

def get_gemini_client():
    load_dotenv(override=True)
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key)
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
        return None

def slugify(text: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
    return slug or "medical-term"

def is_chinese_novel(novel_title: str = "", genre: str = "") -> bool:
    """Retained for signature compatibility; always False in medical reader."""
    return False

def clean_entry_for_novel(entry: dict, is_chinese: bool = False) -> dict:
    """Normalizes medical glossary entry fields."""
    entry["pinyin_or_chinese"] = ""
    entry["category"] = normalize_category(entry.get("category", "Concept"))
    
    raw_aliases = entry.get("aliases", [])
    if not isinstance(raw_aliases, list):
        raw_aliases = [raw_aliases] if raw_aliases else []
    
    filtered = []
    name_lower = (entry.get("name") or "").strip().lower()
    for a in raw_aliases:
        if not isinstance(a, str):
            continue
        a_strip = a.strip()
        if not a_strip or a_strip.lower() in ["n/a", "none", "null"]:
            continue
        if a_strip.lower() == name_lower:
            continue
        if a_strip not in filtered:
            filtered.append(a_strip)
    entry["aliases"] = filtered
    if "image_url" not in entry:
        entry["image_url"] = ""
    if entry.get("category") == "Drug" and not entry.get("bnf_dosage"):
        try:
            import bnf_engine
            bnf_res = bnf_engine.lookup_drug_bnf(entry.get("name", ""))
            if bnf_res.get("found"):
                entry["bnf_dosage"] = bnf_res.get("indications_and_dose", "")
        except Exception:
            pass
    return entry

CHINESE_CHAR_RE = re.compile(r'[\u4e00-\u9fff]')

def extract_characters_from_text(text: str, existing_glossary: List[Dict[str, Any]], novel_title: str = "", genre: str = "") -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Scans textbook chapter text with Gemini to extract high-yield medical terms across
    the 5 core categories:
      1. Anatomy
      2. Pathology / Disease
      3. Concept
      4. Instrument / Device
      5. Drug
    Extracts AKAs (aliases, brand names, acronyms, abbreviations), organ systems,
    and comprehensive, multi-line clinical summaries.
    Returns: (updated_glossary, newly_added_names)
    """
    client = get_gemini_client()
    if not client:
        print("Gemini API key not configured or google-genai not installed.")
        return existing_glossary, []

    book_title = novel_title or "Medical Textbook"

    existing_names_summary = []
    for item in existing_glossary:
        existing_names_summary.append({
            "name": item.get("name", ""),
            "category": item.get("category", "Concept"),
            "aliases": item.get("aliases", []),
            "affiliation": item.get("affiliation") or item.get("sect_or_affiliation", "")
        })

    prompt = f"""You are an expert clinical professor and medical textbook reference editor analyzing chapters from "{book_title}".

Extract high-yield medical entities, diseases, anatomical structures, diagnostic criteria, clinical concepts, drugs, and instruments mentioned in the chapter text below.

CLASSIFY EACH TERM INTO EXACTLY ONE OF THESE 5 CATEGORIES:
1. "Anatomy" (Anatomical structures, vessels, nerves, organs, fascial planes, histology)
2. "Pathology / Disease" (Diseases, clinical conditions, syndromes, disorders, injuries, infections)
3. "Concept" (Pathophysiology, clinical signs/reflexes, diagnostic scores, staging systems, guidelines, physical exam maneuvers)
4. "Instrument / Device" (Medical devices, surgical tools, catheters, monitoring instruments, implants, diagnostic hardware)
5. "Drug" (Medications, pharmacology classes, biological agents, antidotes, vaccines)

FOR EACH EXTRACTED TERM, PROVIDE:
- "name": Standard canonical medical name (e.g. "Tension Pneumothorax", "Glasgow Coma Scale", "Femoral Artery", "Ceftriaxone", "Bougie Dilator").
- "category": Exactly one of: "Anatomy", "Pathology / Disease", "Concept", "Instrument / Device", "Drug".
- "aliases": Array of AKAs (Also Known As): Brand names, generic names, common medical abbreviations/acronyms, eponyms, or alternate spellings (e.g. ["EtCO2", "end-tidal carbon dioxide"], ["GCS"], ["Rocephin"], ["needle thoracostomy"]).
- "sect_or_affiliation": Relevant organ system, anatomical region, drug class, or medical specialty (e.g. "Emergency Medicine / Pulmonology", "Third-generation Cephalosporin", "Cardiovascular").
- "summary": Exactly ONE concise sentence (1 line). A clear, punchy, high-yield clinical definition and primary clinical role or indication. STRICT: Must be a single sentence.
- "image_url": Optional URL to a public medical diagram/illustration if specifically known, else "".

EXISTING TERMS ALREADY TRACKED (Do not duplicate; only extract new entities or identify new AKAs):
{json.dumps(existing_names_summary[:60], ensure_ascii=False, indent=2)}

CHAPTER TEXT TO SCAN:
\"\"\"
{text[:18000]}
\"\"\"

Return a JSON array of objects with the exact schema:
[
  {{
    "name": "Standard Medical Term",
    "category": "Pathology / Disease",
    "aliases": ["AKA 1", "Abbreviation / Brand"],
    "sect_or_affiliation": "Organ System / Specialty",
    "summary": "One sentence high-yield clinical definition and indication.",
    "image_url": ""
  }}
]
Only return a valid JSON array. No extra commentary or markdown backticks.
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
    extracted = None

    for model_name in models_to_try:
        try:
            from google.genai import types
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            content = (response.text or "").strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            parsed = json.loads(content)
            if isinstance(parsed, list):
                extracted = parsed
                break
        except Exception as e:
            print(f"Notice: Model {model_name} extraction error ({e}). Trying fallback...")
            continue

    if not extracted:
        return existing_glossary, []

    updated_glossary = [dict(c) for c in existing_glossary]
    newly_added = []

    for item in extracted:
        name = item.get("name", "").strip()
        if not name or len(name) < 2:
            continue

        clean_entry_for_novel(item)

        # Check if term matches an existing entry
        matched_entry = None
        for entry in updated_glossary:
            existing_name = (entry.get("name") or "").lower()
            existing_aliases = [(a or "").lower() for a in entry.get("aliases", [])]
            
            if name.lower() == existing_name or name.lower() in existing_aliases:
                matched_entry = entry
                break
            for incoming_alias in item.get("aliases", []):
                if incoming_alias.lower() == existing_name or incoming_alias.lower() in existing_aliases:
                    matched_entry = entry
                    break
            if matched_entry:
                break

        if matched_entry:
            # Merge AKAs
            current_aliases = matched_entry.get("aliases", [])
            current_aliases_lower = [a.lower() for a in current_aliases]
            for a in item.get("aliases", []):
                if a.strip() and a.lower() not in current_aliases_lower and a.lower() != (matched_entry.get("name") or "").lower():
                    current_aliases.append(a.strip())
                    current_aliases_lower.append(a.lower())
            matched_entry["aliases"] = current_aliases
            
            if not matched_entry.get("category") or matched_entry.get("category") in ["Character", "Race / Creature", "Clan / Sect"]:
                matched_entry["category"] = item.get("category", "Concept")

            affiliation_val = item.get("sect_or_affiliation") or item.get("affiliation")
            if not matched_entry.get("affiliation") and affiliation_val:
                matched_entry["affiliation"] = affiliation_val
                matched_entry["sect_or_affiliation"] = affiliation_val

            if item.get("image_url") and not matched_entry.get("image_url"):
                matched_entry["image_url"] = item["image_url"]

            # If existing summary is tiny and incoming is comprehensive, enrich it
            if len(item.get("summary", "")) > len(matched_entry.get("summary", "") or ""):
                matched_entry["summary"] = item["summary"]

            clean_entry_for_novel(matched_entry)
        else:
            term_id = slugify(name)
            existing_ids = {c.get("id") for c in updated_glossary}
            counter = 1
            base_id = term_id
            while term_id in existing_ids:
                term_id = f"{base_id}-{counter}"
                counter += 1

            new_entry = {
                "id": term_id,
                "name": name,
                "category": normalize_category(item.get("category", "Concept")),
                "pinyin_or_chinese": "",
                "aliases": [a.strip() for a in item.get("aliases", []) if a.strip() and a.lower() != name.lower()],
                "affiliation": item.get("sect_or_affiliation") or item.get("affiliation", ""),
                "sect_or_affiliation": item.get("sect_or_affiliation") or item.get("affiliation", ""),
                "summary": item.get("summary", ""),
                "image_url": item.get("image_url", ""),
                "updated_at": item.get("updated_at") or ""
            }
            clean_entry_for_novel(new_entry)
            updated_glossary.append(new_entry)
            newly_added.append(name)

    return updated_glossary, newly_added


def ai_enhance_book_metadata(raw_title: str, raw_author: str, raw_description: str = "", sample_text: str = "") -> Dict[str, Any]:
    """
    Analyzes raw EPUB metadata and opening text excerpt using Gemini AI to extract
    clean, iconic medical textbook title, verified authors/editors, specialty genre, and clinical overview.
    """
    fallback_title = raw_title.strip()
    fallback_title = re.sub(r'\s*[-_:]\s*(retail|scan|ocr|hocr|pdf|epub|worldfreebooks.*)\b.*$', '', fallback_title, flags=re.IGNORECASE).strip()
    fallback_title = re.sub(r'\s*\(retail\)\s*$', '', fallback_title, flags=re.IGNORECASE).strip()
    if not fallback_title:
        fallback_title = "Medical Textbook"

    fallback_author = raw_author.strip() if raw_author else "Unknown Medical Author"

    baseline = {
        "title": fallback_title,
        "author": fallback_author,
        "genre": "MEDICAL TEXTBOOK",
        "description": raw_description.strip() if raw_description else "",
        "enable_glossary": True
    }

    client = get_gemini_client()
    if not client:
        return baseline

    prompt = f"""You are an expert medical librarian and clinical cataloger.
A user has uploaded a medical textbook EPUB file to their digital clinical reference library.
Analyze the raw metadata and opening excerpt below to generate clean, professional book metadata.

Raw Title: {raw_title}
Raw Author: {raw_author}
Raw Description: {raw_description}
Opening Excerpt:
{sample_text[:1400]}

Return ONLY a valid JSON object with the following fields:
{{
  "title": "Clean, iconic medical textbook title (strip scan junk, file extensions, retail tags)",
  "author": "Clean, proper author or editor names with credentials if present (e.g. 'Judith E. Tintinalli, MD, MS')",
  "genre": "Concise medical specialty genre (e.g. EMERGENCY MEDICINE, INTERNAL MEDICINE, SURGERY, PHARMACOLOGY, PATHOLOGY, ANATOMY)",
  "description": "Professional 2-3 sentence overview of this clinical manual or textbook",
  "enable_glossary": true
}}
"""

    models_to_try = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]
    for model_name in models_to_try:
        try:
            from google.genai import types
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            content = (response.text or "").strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            parsed = json.loads(content.strip())
            if isinstance(parsed, dict) and parsed.get("title"):
                return {
                    "title": str(parsed.get("title", fallback_title)).strip() or fallback_title,
                    "author": str(parsed.get("author", fallback_author)).strip() or fallback_author,
                    "genre": str(parsed.get("genre", "MEDICAL TEXTBOOK")).strip() or "MEDICAL TEXTBOOK",
                    "description": str(parsed.get("description", "")).strip(),
                    "enable_glossary": bool(parsed.get("enable_glossary", True))
                }
        except Exception:
            continue

    return baseline
