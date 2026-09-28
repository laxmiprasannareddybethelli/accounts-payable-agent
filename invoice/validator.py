SEVERITY = {'Critical': 3, 'High': 2, 'Medium': 1}

def _f(v):
    try: return float(v or 0)
    except (TypeError, ValueError): return 0.0

def detect_exception(inv, historical_ids=None):
    """Detect every exception from invoice fields only (no pre-labelled column).
    All exceptions are reported; the most severe one is the primary exception.
    historical_ids must NOT contain the invoice's own id (callers remove it)."""
    checks = []
    if str(inv.get('invoice_gstin', '')).strip() != str(inv.get('supplier_gstin', '')).strip():
        checks.append(('GSTIN Mismatch', 'High', 'Verify supplier GSTIN before payment.',
                       f"Invoice GSTIN {inv.get('invoice_gstin')} differs from supplier GSTIN {inv.get('supplier_gstin')}."))
    if abs(_f(inv.get('invoice_amount')) - _f(inv.get('po_amount'))) > 0.01:
        checks.append(('PO Variance', 'Medium', 'Route the invoice to procurement for PO variance approval.',
                       f"Invoice amount ₹{_f(inv.get('invoice_amount')):,.2f} differs from PO amount ₹{_f(inv.get('po_amount')):,.2f}."))
    is_dup = str(inv.get('duplicate_flag', 'NO')).upper() == 'YES'
    if is_dup or (historical_ids and str(inv.get('invoice_id')) in historical_ids):
        checks.append(('Duplicate Invoice', 'High', 'Block duplicate payment and verify the original invoice.',
                       'The invoice is flagged as a duplicate or reuses an existing invoice number.'))
    if abs(_f(inv.get('invoice_tds')) - _f(inv.get('expected_tds'))) > 0.01:
        checks.append(('TDS Mismatch', 'Medium', 'Route to tax/finance review for TDS correction.',
                       f"Invoice TDS ₹{_f(inv.get('invoice_tds')):,.2f} differs from expected TDS ₹{_f(inv.get('expected_tds')):,.2f}."))
    if str(inv.get('invoice_bank_account', '')).strip() != str(inv.get('registered_bank_account', '')).strip():
        checks.append(('Bank Account Change', 'Critical', 'Hold payment and verify bank details through an approved channel.',
                       'Invoice bank account differs from the registered supplier bank account.'))
    it, at = str(inv.get('payment_terms', '') or '').strip(), str(inv.get('agreed_payment_terms', '') or '').strip()
    if it and at and it.lower() != at.lower():  # skipped when either side is unknown
        checks.append(('Payment Terms Mismatch', 'Medium', 'Ask procurement to confirm the terms before scheduling payment.',
                       f"Invoice payment terms ({it}) differ from the agreed supplier terms ({at})."))
    if not checks:
        return {'exception_type': 'No Exception', 'risk': 'Low', 'recommendation': 'Continue normal processing.',
                'reasons': ['All configured validation checks passed.'], 'all_exceptions': []}
    checks.sort(key=lambda c: -SEVERITY[c[1]])
    et, risk, rec, _ = checks[0]
    return {'exception_type': et, 'risk': risk, 'recommendation': rec,
            'reasons': [c[3] for c in checks], 'all_exceptions': [c[0] for c in checks]}
