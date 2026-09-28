"""Decision ladder: what the agent does depends on what memory returns.
Memory is the only thing that changes the outcome; nothing is retrained."""
from collections import defaultdict

# Only these risk levels may ever be auto-resolved. High/Critical always get a human.
AUTO_RISKS = {'Medium', 'Low'}

# Approval workflow. A higher rank can do anything a lower rank can.
ROLES = ['Junior AP Analyst', 'Senior Accountant', 'Finance Controller']
RANK = {r: i for i, r in enumerate(ROLES)}

def can_approve(user_role, required_role):
    return required_role is None or RANK[user_role] >= RANK[required_role]

def required_role(risk, level):
    """Who must sign off. Memory only lowers this for Medium risk with agreeing precedents."""
    if level in ('clear', 'auto'): return None
    if risk == 'Critical': return 'Finance Controller'
    if risk == 'High': return 'Senior Accountant'
    return 'Junior AP Analyst' if level == 'suggest' else 'Senior Accountant'

def _decide(detection, precedents):
    et, risk = detection['exception_type'], detection['risk']
    if et == 'No Exception':
        return {'level': 'clear', 'label': 'No exception', 'note': 'All checks passed.'}
    decisions = {p['decision'] for p in precedents}
    n = len(precedents)
    if risk == 'Critical':
        return {'level': 'escalate', 'label': 'Senior review (critical risk)',
                'note': 'Critical exceptions are never auto-resolved, whatever memory says.'}
    if n == 0:
        return {'level': 'escalate', 'label': 'Senior review',
                'note': 'No past decision found for this supplier and exception type.'}
    if len(decisions) > 1:
        return {'level': 'escalate', 'label': 'Senior review (precedents disagree)',
                'note': f'{n} past decisions for this supplier disagree. Disagreement is treated as a warning sign.'}
    agreed = next(iter(decisions))
    if n >= 2 and agreed == 'APPROVED' and risk in AUTO_RISKS:
        return {'level': 'auto', 'label': 'Auto-resolved from memory',
                'note': f'{n} past decisions for this supplier agree ({agreed}).'}
    if n >= 2 and risk not in AUTO_RISKS:
        return {'level': 'suggest', 'label': 'One-click approval',
                'note': f'{n} agreeing precedents ({agreed}), but {risk} risk is always human-approved.'}
    return {'level': 'suggest', 'label': 'One-click approval',
            'note': f'{n} past decision(s) for this supplier suggest: {agreed}.'}

def decide(detection, precedents):
    d = _decide(detection, precedents)
    d['role'] = required_role(detection['risk'], d['level'])
    return d

def simulate(df, detect):
    """Replay the dataset in order with an approver who approves every case.
    Compares 'memory off' (every exception needs a Senior Accountant or above) with 'memory on'
    (see the 'needs' column: memory moves Medium-risk cases down to a Junior AP Analyst or to nobody).
    Synthetic data: shows the mechanism, not real savings."""
    hist = defaultdict(list)
    rows = []
    for i, (_, r) in enumerate(df.iterrows(), 1):
        d = detect(r.to_dict())
        if d['exception_type'] == 'No Exception':
            continue
        key = (r['supplier_name'], d['exception_type'])
        dec = decide(d, [{'decision': x} for x in hist[key]])
        rows.append({'seq': i, 'invoice': r['invoice_id'], 'supplier': r['supplier_name'],
                     'exception': d['exception_type'], 'risk': d['risk'], 'level': dec['level'],
                     'needs': dec['role'] or 'nobody'})
        if dec['level'] != 'auto':
            hist[key].append('APPROVED')
    return rows
