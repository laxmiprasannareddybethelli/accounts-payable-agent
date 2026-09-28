import os, re
from database.database import get_cases, save_case

BANK_ID = os.getenv('HINDSIGHT_BANK_ID', 'ap-exception-agent')
_DECISION = re.compile(r'Approver decision:\s*(APPROVED|REJECTED)', re.I)

def _norm(outcome):
    return 'REJECTED' if str(outcome).upper().startswith('REJ') else 'APPROVED'

class HindsightMemory:
    """Retain / recall / reflect on Hindsight Cloud. If HINDSIGHT_* env vars are missing or the
    call fails, it falls back to local SQLite and says so in `backend` (never silently)."""
    def __init__(self):
        self.client, self.error = None, ''
        self.backend = 'Local SQLite (Hindsight not configured)'
        url = os.getenv('HINDSIGHT_BASE_URL', '').strip()
        key = os.getenv('HINDSIGHT_API_KEY', '').strip()
        if url and key:
            try:
                from hindsight_client import Hindsight
                self.client = Hindsight(base_url=url, api_key=key)
                self.backend = 'Hindsight Cloud'
                try: self.client.create_bank(bank_id=BANK_ID, name='AP Exception Agent')
                except Exception: pass  # bank probably exists already
            except Exception as e:
                self.client, self.error = None, str(e)
                self.backend = 'Local SQLite (Hindsight client failed)'

    def _text(self, supplier, invoice_id, et, risk, rec, decision, role='', reason=''):
        who = f" Decided by: {role}." if role else ''
        why = f" Reason: {reason.strip()}" if reason and reason.strip() else ''
        return (f"AP exception precedent. Supplier: {supplier}. Invoice: {invoice_id}. "
                f"Exception: {et} (risk {risk}). Recommended action: {rec} "
                f"Approver decision: {decision}.{who}{why}")

    def retain(self, invoice_id, supplier, exception_type, risk, recommendation, outcome, source, details, role='', reason=''):
        decision = _norm(outcome)
        save_case(invoice_id, supplier, exception_type, risk, recommendation, decision, source, details, role, reason)
        if self.client:
            try:
                self.client.retain(bank_id=BANK_ID, content=self._text(
                    supplier, invoice_id, exception_type, risk, recommendation, decision, role, reason))
            except Exception as e:
                self.error = f'retain failed: {e}'

    def recall(self, exception_type, supplier=None, limit=5):
        """Precedents for this supplier AND exception type only: [{'text','decision'}]."""
        sup = (supplier or '').lower()
        if self.client:
            try:
                res = self.client.recall(bank_id=BANK_ID, query=(
                    f"How was {exception_type} resolved for supplier {supplier}?"))
                out = []
                for r in getattr(res, 'results', res) or []:
                    t = getattr(r, 'text', None) or str(r)
                    m = _DECISION.search(t)
                    if m and exception_type.lower() in t.lower() and sup and sup in t.lower():
                        out.append({'text': t, 'decision': m.group(1).upper()})
                return out[:limit]
            except Exception as e:
                self.error = f'recall failed, used local memory: {e}'
        out = []
        for r in get_cases(300):  # id, invoice, supplier, type, risk, rec, outcome, source, details, created
            if r[3] == exception_type and sup and r[2].lower() == sup and r[7] != 'auto':
                d = _norm(r[6])
                out.append({'text': self._text(r[2], r[1], r[3], r[4], r[5], d, r[10] or '', r[11] or ''), 'decision': d})
        return out[:limit]

    def reflect(self, supplier):
        q = f"Summarise what has been learned about how exceptions for supplier {supplier} are resolved."
        if self.client:
            try:
                r = self.client.reflect(bank_id=BANK_ID, query=q)
                return getattr(r, 'text', None) or str(r)
            except Exception as e:
                self.error = f'reflect failed: {e}'
        rows = [r for r in get_cases(500) if r[2].lower() == supplier.lower() and r[7] != 'auto']
        if not rows: return f'No retained decisions for {supplier} yet.'
        lines = [f"- {r[3]}: {_norm(r[6])}" + (f" by {r[10]}" if r[10] else '') + (f" ({r[11]})" if r[11] else '') for r in rows]
        return f'Local summary for {supplier} ({len(rows)} decisions):\n' + '\n'.join(lines)
