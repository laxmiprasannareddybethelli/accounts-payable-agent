"""Pure functions (no Streamlit) behind Payment History, Case History and the Memory Center.
Kept separate so they can be unit-tested."""
import pandas as pd
from database.database import CASE_COLS, PAY_COLS
from invoice.validator import detect_exception

def cases_df(rows):
    df = pd.DataFrame(rows, columns=CASE_COLS)
    df['Approver role'] = df['Approver role'].fillna('').replace('', '—')
    df['Reason'] = df['Reason'].fillna('')
    df['Learned by agent'] = df['Source'] != 'auto'   # auto-resolutions are audit-only, never fed back
    return df

def filter_cases(df, supplier='All', exception='All', risk='All', outcome='All', role='All', text=''):
    m = pd.Series(True, index=df.index)
    for col, val in [('Supplier', supplier), ('Exception', exception), ('Risk', risk), ('Outcome', outcome), ('Approver role', role)]:
        if val and val != 'All': m &= df[col] == val
    t = (text or '').strip().lower()
    if t:
        hay = (df['Invoice'].astype(str) + ' ' + df['Supplier'] + ' ' + df['Reason'] + ' ' + df['Exception']).str.lower()
        m &= hay.str.contains(t, regex=False)
    return df[m]

def memory_stats(df):
    if df.empty: return {'total': 0, 'approved': 0, 'rejected': 0, 'auto': 0, 'suppliers': 0, 'with_reason': 0, 'approve_rate': 0.0}
    learned = df[df['Learned by agent']]
    n = len(learned); ap = int((learned.Outcome == 'APPROVED').sum())
    return {'total': n, 'approved': ap, 'rejected': int((learned.Outcome == 'REJECTED').sum()),
            'auto': int((~df['Learned by agent']).sum()), 'suppliers': int(learned.Supplier.nunique()),
            'with_reason': int((learned.Reason.str.strip() != '').sum()), 'approve_rate': (ap / n * 100) if n else 0.0}

def supplier_learning(df):
    """One row per supplier: what the agent has learned so far."""
    cols = ['Supplier', 'Decisions', 'Approved', 'Rejected', 'Approval %', 'Most common exception', 'Last decision', 'Agent readiness']
    learned = df[df['Learned by agent']] if not df.empty else df
    if learned.empty: return pd.DataFrame(columns=cols)
    out = []
    for sup, g in learned.groupby('Supplier'):
        g = g.sort_values('ID'); n = len(g); ap = int((g.Outcome == 'APPROVED').sum())
        by_type = g.groupby('Exception').Outcome.agg(lambda s: set(s))
        agreeing = int(sum(1 for s in by_type if len(s) == 1))
        ready = 'Has agreeing precedents' if agreeing else 'Precedents disagree'
        out.append({'Supplier': sup, 'Decisions': n, 'Approved': ap, 'Rejected': n - ap, 'Approval %': round(ap / n * 100),
                    'Most common exception': g.Exception.mode().iloc[0], 'Last decision': f"{g.iloc[-1].Outcome} ({g.iloc[-1].Exception})",
                    'Agent readiness': ready})
    return pd.DataFrame(out, columns=cols).sort_values('Decisions', ascending=False)

def terms_profile(inv_df):
    """Per supplier payment-terms picture from the invoice dataset."""
    cols = ['Supplier', 'Agreed terms', 'Invoices', 'Terms mismatches', 'Mismatch %', 'Usually billed as']
    if inv_df.empty or 'payment_terms' not in inv_df: return pd.DataFrame(columns=cols)
    out = []
    for sup, g in inv_df.groupby('supplier_name'):
        billed = g.payment_terms.fillna('').astype(str).str.strip(); agreed = g.agreed_payment_terms.fillna('').astype(str).str.strip()
        known = (billed != '') & (agreed != '')
        mm = int((known & (billed.str.lower() != agreed.str.lower())).sum())
        out.append({'Supplier': sup, 'Agreed terms': agreed[agreed != ''].mode().iloc[0] if (agreed != '').any() else '—',
                    'Invoices': len(g), 'Terms mismatches': mm, 'Mismatch %': round(mm / max(int(known.sum()), 1) * 100),
                    'Usually billed as': billed[billed != ''].mode().iloc[0] if (billed != '').any() else '—'})
    return pd.DataFrame(out, columns=cols).sort_values('Mismatch %', ascending=False)

def payment_ledger(inv_df, pay_rows, case_rows):
    """Every dataset invoice with its payment position. Status is derived, never assumed."""
    pays = {}
    for r in sorted(pay_rows, key=lambda r: r[0]): pays[str(r[1])] = r          # latest payment per invoice wins
    decided = {}
    for r in sorted(case_rows, key=lambda r: r[0]):
        if r[8] is not None and r[7] != 'auto': decided[str(r[1])] = r[6]         # human decision per invoice
    known = set(inv_df.invoice_id.astype(str)); out = []
    for _, row in inv_df.iterrows():
        inv = row.to_dict(); iid = str(inv['invoice_id'])
        d = detect_exception(inv, known - {iid}); et = d['exception_type']
        if iid in pays: status, ref, pdate = pays[iid][4], pays[iid][6], pays[iid][5]
        elif et == 'No Exception': status, ref, pdate = 'Clear – awaiting payment', '', ''
        elif decided.get(iid) == 'APPROVED': status, ref, pdate = 'Exception approved – ready to release', '', ''
        elif decided.get(iid) == 'REJECTED': status, ref, pdate = 'Rejected – payment on hold', '', ''
        else: status, ref, pdate = 'Held – exception unresolved', '', ''
        out.append({'Invoice': iid, 'Supplier': inv['supplier_name'], 'Amount': float(inv.get('invoice_amount') or 0),
                    'Billed terms': inv.get('payment_terms', ''), 'Agreed terms': inv.get('agreed_payment_terms', ''),
                    'Exception': et, 'Risk': d['risk'], 'Payment status': status, 'Reference': ref, 'Paid/ready on': pdate})
    return pd.DataFrame(out)

RELEASABLE = ('Clear – awaiting payment', 'Exception approved – ready to release')

def ledger_summary(led):
    if led.empty: return {'paid': 0.0, 'ready': 0.0, 'held': 0.0, 'awaiting': 0.0}
    s = led.groupby('Payment status').Amount.sum()
    g = lambda k: float(s.get(k, 0.0))
    return {'paid': g('Paid'), 'ready': g('Ready'),
            'awaiting': g('Clear – awaiting payment') + g('Exception approved – ready to release'),
            'held': g('Held – exception unresolved') + g('Rejected – payment on hold')}
