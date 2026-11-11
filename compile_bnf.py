import os
import json
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_FILE = os.path.join(BASE_DIR, "bnf_drugs.json")
DATA_OUT = os.path.join(BASE_DIR, "data", "bnf_drugs.json")
MOBILE_OUT = os.path.join(BASE_DIR, "m", "static", "data", "bnf_drugs.json")
DATA_GLOSSARY_OUT = os.path.join(BASE_DIR, "data", "bnf_glossary.json")
MOBILE_GLOSSARY_OUT = os.path.join(BASE_DIR, "m", "static", "data", "bnf_glossary.json")

US_TO_BNF = {
    'acetaminophen': 'paracetamol',
    'tylenol': 'paracetamol',
    'epinephrine': 'adrenaline',
    'adrenaline/epinephrine': 'adrenaline',
    'norepinephrine': 'noradrenaline',
    'noradrenaline/norepinephrine': 'noradrenaline',
    'succinylcholine': 'suxamethonium',
    'suxamethonium chloride': 'suxamethonium',
    'albuterol': 'salbutamol',
    'ventolin': 'salbutamol',
    'lasix': 'furosemide',
    'frusemide': 'furosemide',
    'lidocaine': 'lidocaine',
    'lignocaine': 'lidocaine',
    'xylocaine': 'lidocaine',
    'roc': 'rocuronium bromide',
    'rocuronium': 'rocuronium bromide',
    'mag sulfate': 'magnesium sulfate',
    'magnesium sulphate': 'magnesium sulfate',
    'mgso4': 'magnesium sulfate',
    'bactrim': 'co-trimoxazole',
    'septra': 'co-trimoxazole',
    'augmentin': 'co-amoxiclav',
    'amoxicillin-clavulanate': 'co-amoxiclav',
    'amoxicillin/clavulanic acid': 'co-amoxiclav',
    'ativan': 'lorazepam',
    'versed': 'midazolam',
    'valium': 'diazepam',
    'dilaudid': 'hydromorphone',
    'demerol': 'pethidine hydrochloride',
    'meperidine': 'pethidine hydrochloride',
    'lopressor': 'metoprolol tartrate',
    'toprol-xl': 'metoprolol tartrate',
    'betaloc': 'metoprolol tartrate',
    'cordarone': 'amiodarone hydrochloride',
    'lanoxin': 'digoxin',
    'narcan': 'naloxone hydrochloride',
    'heparin': 'heparin (unfractionated)',
    'unfractionated heparin': 'heparin (unfractionated)',
    'ufh': 'heparin (unfractionated)',
    'clexane': 'enoxaparin sodium',
    'enoxaparin': 'enoxaparin sodium',
    'lovenox': 'enoxaparin sodium',
    'fragmin': 'dalteparin sodium',
    'dalteparin': 'dalteparin sodium',
    'innohep': 'tinzaparin sodium',
    'tinzaparin': 'tinzaparin sodium',
    'eliquis': 'apixaban',
    'xarelto': 'rivaroxaban',
    'pradaxa': 'dabigatran etexilate',
    'coumadin': 'warfarin sodium',
    'warfarin': 'warfarin sodium',
}

SALTS_REGEX = r'\b(hydrochloride|sulfate|sulphate|bromide|chloride|sodium|potassium|tartrate|acetate|fumarate|maleate|succinate|phosphate|gluconate|dihydrate|trihydrate|heptahydrate|mesilate|dipropionate|propionate|valerate|decanoate|enanthate|besilate|citrate|lactate)\b'

def clean_and_format_indications(indications):
    sections = []
    for item in indications:
        ind = (item.get('indication') or '').strip()
        dose = (item.get('dose') or '').strip()
        prep = (item.get('preparation') or '').strip()
        
        if not ind and not dose:
            continue
        
        # If indication was split like '[INJECTION]', merge gracefully
        title = ind
        if prep and not title.startswith(f'[{prep}]'):
            title = f'[{prep}] {title}'
            
        dose_lines = []
        for line in dose.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith('▶'):
                content = line[1:].strip()
                # Route line
                if re.match(r'^(BY|INITIALLY BY|MAINTENANCE BY|TO THE|TO|IN|WITH|FOR)\s+[A-Z\s\(\),–\-]+$', content) or re.match(r'^(BY\s+[A-Z]+)', content):
                    dose_lines.append(f'[{content}]')
                # Patient dose bullet
                elif re.match(r'^(Adult|Child|Elderly|Neonate|Patient|Body-weight)', content):
                    dose_lines.append(f'• {content}')
                else:
                    dose_lines.append(content)
            elif line.startswith('[') and line.endswith(']'):
                dose_lines.append(line)
            elif re.match(r'^(Adult|Child|Elderly|Neonate|Patient|Body-weight)', line):
                dose_lines.append(f'• {line}')
            else:
                dose_lines.append(line)
        
        dose_text = '\n'.join(dose_lines)
        if title:
            sections.append(f'{title}\n\n{dose_text}')
        else:
            sections.append(dose_text)
            
    return '\n\n'.join(sections)

def compile_database():
    with open(SRC_FILE, 'r', encoding='utf-8') as f:
        raw_list = json.load(f)
        
    print(f"Loaded {len(raw_list)} raw drugs from {SRC_FILE}")
    
    # Sort raw_list so single-agent drugs come before combinations ('with', 'and')
    raw_sorted = sorted(
        raw_list, 
        key=lambda d: (' with ' in d['drug_name'].lower() or ' and ' in d['drug_name'].lower(), len(d['drug_name']))
    )
    
    compiled = {}
    
    for item in raw_sorted:
        d_name = item.get('drug_name', '').strip()
        if not d_name:
            continue
            
        formatted_dose = clean_and_format_indications(item.get('indications', []))
        entry = {
            'drug': d_name,
            'indications_and_dose': formatted_dose,
            'chapters': item.get('chapters', []),
            'pages': item.get('pages', []),
            'source': 'British National Formulary (BNF 85)'
        }
        
        d_lower = d_name.lower()
        
        # Exact name
        if d_lower not in compiled:
            compiled[d_lower] = entry
            
        # Slash split (e.g. "Adrenaline/epinephrine", "Noradrenaline/norepinephrine")
        if '/' in d_lower:
            for part in d_lower.split('/'):
                p_clean = part.strip()
                if p_clean and p_clean not in compiled:
                    compiled[p_clean] = entry
                    
        # Strip parenthetical qualifiers (e.g. "Heparin (unfractionated)" -> "heparin", "Calcitonin (salmon)" -> "calcitonin")
        no_parens = re.sub(r'\(.*?\)', '', d_lower).strip()
        no_parens = re.sub(r'\s+', ' ', no_parens).strip()
        if no_parens and len(no_parens) >= 3 and no_parens not in compiled:
            compiled[no_parens] = entry

        # Base name without salts (e.g. "Metoprolol" for "Metoprolol tartrate")
        for candidate_text in [d_lower, no_parens]:
            base = re.sub(SALTS_REGEX, '', candidate_text, flags=re.I).strip()
            base = re.sub(r'\s+', ' ', base).strip()
            if base and len(base) >= 3 and base not in compiled:
                compiled[base] = entry
            
        # British / American spelling variants (sulphate <-> sulfate)
        if 'sulfate' in d_lower:
            alt = d_lower.replace('sulfate', 'sulphate')
            if alt not in compiled:
                compiled[alt] = entry
        if 'sulphate' in d_lower:
            alt = d_lower.replace('sulphate', 'sulfate')
            if alt not in compiled:
                compiled[alt] = entry

    # Add US_TO_BNF synonyms
    for syn_key, target_key in US_TO_BNF.items():
        syn_k = syn_key.lower().strip()
        target_k = target_key.lower().strip()
        if syn_k not in compiled:
            if target_k in compiled:
                compiled[syn_k] = compiled[target_k]
            else:
                # check if target_k matches any key
                match = next((v for k, v in compiled.items() if k.startswith(target_k) or target_k.startswith(k)), None)
                if match:
                    compiled[syn_k] = match

    print(f"Total compiled dictionary keys (with aliases & salts): {len(compiled)}")
    
    # Save to data/bnf_drugs.json and m/static/data/bnf_drugs.json
    for out_path in [DATA_OUT, MOBILE_OUT]:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(compiled, f, ensure_ascii=False, indent=2)
        print(f"Saved {out_path} ({os.path.getsize(out_path) / (1024*1024):.2f} MB)")

    # Build structured list of all 1,699 drugs for the BNF Formulary Browser & Glossary population
    def slugify(text):
        t = text.lower().strip()
        t = re.sub(r'[^\w\s-]', '', t)
        t = re.sub(r'[\s_-]+', '-', t)
        return t.strip('-')

    bnf_to_synonyms = {}
    for syn, target in US_TO_BNF.items():
        bnf_to_synonyms.setdefault(target.lower().strip(), set()).add(syn)

    glossary_list = []
    seen_slugs = set()

    for item in raw_list:
        d_name = item.get('drug_name', '').strip()
        if not d_name:
            continue
        slug = slugify(d_name)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        d_lower = d_name.lower()
        aliases = set()

        # 1. Reverse US_TO_BNF synonyms
        for target, syns in bnf_to_synonyms.items():
            if target == d_lower or d_lower.startswith(target) or target.startswith(d_lower):
                for s in syns:
                    if s.lower() != d_lower:
                        aliases.add(s.title())

        # 2. Slash split
        if '/' in d_name:
            for p in d_name.split('/'):
                p_clean = p.strip()
                if p_clean and p_clean.lower() != d_lower and len(p_clean) >= 3:
                    aliases.add(p_clean)

        # 3. Strip parentheses
        no_parens = re.sub(r'\(.*?\)', '', d_name).strip()
        no_parens = re.sub(r'\s+', ' ', no_parens).strip()
        if no_parens and len(no_parens) >= 3 and no_parens.lower() != d_lower:
            aliases.add(no_parens)

        # 4. Salt-stripped base name
        for cand in [d_name, no_parens]:
            base = re.sub(SALTS_REGEX, '', cand, flags=re.I).strip()
            base = re.sub(r'\s+', ' ', base).strip()
            if base and len(base) >= 3 and base.lower() != d_lower:
                aliases.add(base)

        # 5. Sulfate <-> Sulphate
        if 'sulfate' in d_lower:
            aliases.add(re.sub(r'sulfate', 'sulphate', d_name, flags=re.I))
        if 'sulphate' in d_lower:
            aliases.add(re.sub(r'sulphate', 'sulfate', d_name, flags=re.I))

        inds = item.get('indications', [])
        first_summary = ''
        if inds:
            ind_text = (inds[0].get('indication') or '').strip()
            if ind_text:
                first_summary = ind_text.split('\n')[0].strip()

        raw_chapter = item.get('chapters', ['BNF 85 Formulary'])[0]
        chapter_clean = raw_chapter.split(':', 1)[1].strip() if ':' in raw_chapter else raw_chapter
        if not first_summary:
            first_summary = f'BNF 85 Monograph ({chapter_clean})'

        formatted_dose = clean_and_format_indications(inds)

        entry = {
            'id': slug,
            'name': d_name,
            'category': 'Drug',
            'affiliation': chapter_clean,
            'sect_or_affiliation': chapter_clean,
            'aliases': sorted(list(aliases)),
            'summary': first_summary[:250],
            'bnf_dosage': formatted_dose,
            'pinyin_or_chinese': '',
            'chapters': item.get('chapters', []),
            'pages': item.get('pages', []),
            'source': 'British National Formulary (BNF 85)'
        }
        glossary_list.append(entry)

    glossary_list.sort(key=lambda x: x['name'].lower())

    for out_g_path in [DATA_GLOSSARY_OUT, MOBILE_GLOSSARY_OUT]:
        os.makedirs(os.path.dirname(out_g_path), exist_ok=True)
        with open(out_g_path, 'w', encoding='utf-8') as f:
            json.dump(glossary_list, f, ensure_ascii=False, indent=2)
        print(f"Saved {out_g_path} ({len(glossary_list)} entries, {os.path.getsize(out_g_path) / (1024*1024):.2f} MB)")

if __name__ == "__main__":
    compile_database()
