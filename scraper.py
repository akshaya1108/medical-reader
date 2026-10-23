import requests
import json
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
from ai_glossary import get_gemini_client, slugify, normalize_category, clean_entry_for_novel

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9"
}

GENERIC_COMMON_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by",
    "can", "could", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "had", "has", "have", "he", "her", "here", "him", "his", "how", "if", "in", "into", "is", "it",
    "its", "me", "more", "most", "my", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "our", "out", "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "them", "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who",
    "whom", "why", "with", "you", "your"
}

def extract_title_from_url(url: str) -> str:
    if not url:
        return ""
    # Extract Wikipedia page title
    wiki_match = re.search(r'https?://[a-zA-Z-]+\.wikipedia\.org/wiki/([^?#]+)', url)
    if wiki_match:
        return wiki_match.group(1).replace('_', ' ').strip()
    match = re.search(r'https?://([a-zA-Z0-9_-]+)\.fandom\.com/wiki/([^?#]+)', url)
    if match:
        return match.group(2).replace('_', ' ').strip()
    return ""

def fetch_wikipedia_content(query: str) -> Tuple[str, str, str]:
    """
    Fetches lead extract and thumbnail from Wikipedia API for medical entities.
    Returns: (extract_text, image_url, page_title)
    """
    clean_q = query.strip()
    try:
        api_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts|pageimages",
            "exintro": True,
            "explaintext": True,
            "titles": clean_q,
            "redirects": 1,
            "pithumbsize": 500
        }
        res = requests.get(api_url, params=params, headers=HEADERS, timeout=6)
        if res.status_code == 200:
            data = res.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if pid != "-1":
                    text = pdata.get("extract", "").strip()
                    title = pdata.get("title", clean_q)
                    thumb = pdata.get("thumbnail", {}).get("source", "")
                    if text:
                        return text[:8000], thumb, title
    except Exception as e:
        print(f"Notice: Wikipedia lookup failed for {query}: {e}")
    return "", "", ""

def scrape_fandom_data(url_or_title: str, novel_title: str = "") -> Tuple[str, str, str]:
    """Compatibility wrapper; queries Wikipedia or web for medical term."""
    text, img, title = fetch_wikipedia_content(url_or_title)
    if text:
        return text, "Concept", title
    return "", "Concept", url_or_title

def scrape_fandom_character_list(wiki_url_or_title: str, novel_title: str = "") -> Tuple[List[str], str]:
    text, img, title = fetch_wikipedia_content(wiki_url_or_title)
    if title:
        return [title], novel_title or title
    return [wiki_url_or_title], novel_title or wiki_url_or_title

def sanitize_wiki_data_with_gemini(raw_text: str, novel_title: str = "", target_category: str = "", query: str = "", genre: str = "", **kwargs) -> Tuple[List[Dict[str, Any]], str]:
    target_query = (query or novel_title or "").strip()
    res, msg = lookup_single_entity(target_query, novel_title=novel_title, raw_text=raw_text, target_category=target_category, **kwargs)
    return res, msg

def lookup_single_entity(query: str, novel_title: str = "", raw_text: str = "", target_category: str = "", wiki_url: str = "", **kwargs) -> Tuple[List[Dict[str, Any]], str]:
    """
    Looks up a medical term (disease, anatomy, drug, score, device) using Wikipedia + Gemini.
    Returns: (list_of_entries, message)
    """
    client = get_gemini_client()
    if not client:
        return [], "Gemini client not initialized. Please ensure GEMINI_API_KEY is set in .env"

    q_clean = (query or "").strip()
    if not q_clean or q_clean.lower() in GENERIC_COMMON_WORDS:
        return [], "Please provide a valid medical term."

    book_title = novel_title or "Medical Textbook"

    # 1. Instant check in local BNF 85 for drugs (< 5ms)
    # 1. Check local BNF 85 for drugs (< 5ms)
    bnf_dose_info = ""
    try:
        import bnf_engine
        bnf_res = bnf_engine.lookup_drug_bnf(q_clean)
        if bnf_res.get("found"):
            bnf_dose_info = bnf_res.get("indications_and_dose", "")
    except Exception as e:
        print(f"Notice: BNF pre-check skipped: {e}")

    # 2. Fetch Wikipedia extract & diagram thumbnail (< 0.4s)
    wiki_extract, wiki_thumb, verified_title = fetch_wikipedia_content(q_clean)
    context_text = raw_text or wiki_extract

    # Prepare instant Wikipedia fallback entry
    wiki_first_sentence = ""
    if wiki_extract:
        wiki_first_sentence = wiki_extract.split('.')[0].strip() + '.'

    prompt = f"""You are an expert clinical medicine reference scholar and medical educator for "{book_title}".
The user is reading medical literature and wants a verified, high-yield clinical reference entry for "{q_clean}".

Analyze "{q_clean}" in clinical medicine:

1. CANONICAL VERIFICATION:
   Is "{q_clean}" a recognized medical entity, disease, anatomical structure, clinical sign/score, instrument/device, or drug?
   If it is completely non-medical, nonsensical, or generic common slang, return an empty array: []

2. CATEGORIZE ACCURATELY INTO EXACTLY ONE OF THESE 5 CATEGORIES:
   - "Anatomy": Anatomical structures, vascular beds, nerves, organs, histological layers, musculoskeletal landmarks.
   - "Pathology / Disease": Diseases, conditions, syndromes, disorders, trauma/injuries, infections.
   - "Concept": Pathophysiology, physical exam signs, diagnostic criteria, clinical scores, classification systems, staging.
   - "Instrument / Device": Surgical instruments, catheters, monitoring devices, airway tools, diagnostic hardware.
   - "Drug": Medications, pharmacology classes, biologicals, antidotes, vaccines.

3. EXTRACT:
   - "name": Standard canonical medical name (e.g. "Glasgow Coma Scale", "Tension Pneumothorax", "Ceftriaxone", "Femoral Artery").
   - "category": One of: "Anatomy", "Pathology / Disease", "Concept", "Instrument / Device", "Drug".
   - "aliases": Array of AKAs (Also Known As): Brand names, generic names, common medical abbreviations/acronyms, eponyms (always include "{q_clean}" if different from primary name).
   - "sect_or_affiliation": Relevant organ system, anatomical region, drug class, or medical specialty (e.g. "Emergency Medicine / Neurology", "Cardiovascular", "Third-generation Cephalosporin").
   - "summary": Exactly ONE concise sentence (1 line). A clear, punchy, high-yield clinical definition and primary indication or role. STRICT: Must be a single sentence.
   - "image_url": {f'"{wiki_thumb}"' if wiki_thumb else '""'}

{f"Reference Extract:\n{context_text[:5000]}" if context_text else ""}

Return a JSON array with 1 object (or [] if non-medical):
[
  {{
    "name": "Standard Medical Name",
    "category": "Pathology / Disease",
    "aliases": ["{q_clean}", "AKA 1"],
    "sect_or_affiliation": "Organ System / Specialty",
    "summary": "One sentence high-yield clinical definition and indication.",
    "image_url": {f'"{wiki_thumb}"' if wiki_thumb else '""'}
  }}
]
Only return a valid JSON array.
"""

    models_to_try = ["gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-3-flash-preview"]
    if client:
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
                if isinstance(parsed, list) and len(parsed) > 0:
                    entries = []
                    for item in parsed:
                        if item.get("category") == "Drug":
                            # Attach pre-checked BNF dosage or look up with canonical name / aliases
                            if bnf_dose_info:
                                item["bnf_dosage"] = bnf_dose_info
                            else:
                                try:
                                    import bnf_engine
                                    c_name = item.get("name", "")
                                    b_res = bnf_engine.lookup_drug_bnf(c_name)
                                    if b_res.get("found"):
                                        item["bnf_dosage"] = b_res.get("indications_and_dose", "")
                                    else:
                                        for al in item.get("aliases", []):
                                            b_res = bnf_engine.lookup_drug_bnf(al)
                                            if b_res.get("found"):
                                                item["bnf_dosage"] = b_res.get("indications_and_dose", "")
                                                break
                                except Exception as e:
                                    print(f"Notice: BNF lookup error for {c_name}: {e}")
                            if not item.get("bnf_dosage"):
                                item["bnf_dosage"] = "Unavailable"
                        clean_entry_for_novel(item)
                        if not item.get("image_url") and wiki_thumb:
                            item["image_url"] = wiki_thumb
                        entries.append(item)
                    return entries, "Success"
            except Exception as e:
                print(f"Notice: Model {model_name} failed lookup ({e}).")
                break # Don't loop through multiple models if quota/network is down; fall back immediately!

    # Fallback to Wikipedia extract directly if AI was unavailable
    if wiki_extract:
        clean_summary = wiki_first_sentence if len(wiki_first_sentence) > 15 else wiki_extract[:250].strip()
        entry_name = verified_title or q_clean
        is_drug = bool(bnf_dose_info) or any(w in (wiki_extract or "").lower() for w in ["medication", "pharmaceutical", "drug", "dosage"])
        found_aliases = [q_clean] if q_clean.lower() != entry_name.lower() else []
        brand_match = re.search(r'sold under the (?:brand|trade) names?\s+([A-Za-z0-9\-\s]+?)(?:\s+among others|\s*,|\.|$)', wiki_extract, re.IGNORECASE)
        if brand_match:
            b_name = brand_match.group(1).strip()
            if b_name and b_name.lower() not in [entry_name.lower(), q_clean.lower()]:
                found_aliases.append(b_name)

        entry = {
            "id": slugify(entry_name),
            "name": entry_name,
            "category": "Drug" if is_drug else normalize_category(target_category or "Concept"),
            "aliases": found_aliases,
            "affiliation": "Pharmacology / BNF 85" if is_drug else "Clinical Reference",
            "sect_or_affiliation": "Pharmacology / BNF 85" if is_drug else "Clinical Reference",
            "summary": clean_summary,
            "image_url": wiki_thumb or "",
            "bnf_dosage": bnf_dose_info if (is_drug and bnf_dose_info) else ("Unavailable" if is_drug else "")
        }
        clean_entry_for_novel(entry)
        return [entry], "Extracted from clinical reference"

    return [], "Could not verify medical entity."
