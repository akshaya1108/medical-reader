import os
import json
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_FILE = os.path.join(BASE_DIR, "bnf_drugs.json")
DATA_OUT = os.path.join(BASE_DIR, "data", "bnf_drugs.json")
MOBILE_OUT = os.path.join(BASE_DIR, "m", "static", "data", "bnf_drugs.json")

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
    'narcan': 'naloxone hydrochloride'
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
                    
        # Base name without salts (e.g. "Metoprolol" for "Metoprolol tartrate")
        base = re.sub(SALTS_REGEX, '', d_lower, flags=re.I).strip()
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

if __name__ == "__main__":
    compile_database()
