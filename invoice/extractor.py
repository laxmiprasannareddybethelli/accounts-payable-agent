import re

def money(s):
    if s is None: return 0.0
    return float(re.sub(r'[^0-9.]','',str(s)) or 0)

def extract_pdf_text(uploaded):
    import pdfplumber
    with pdfplumber.open(uploaded) as pdf:
        return '\n'.join((p.extract_text() or '') for p in pdf.pages)

def extract_invoice_fields(uploaded):
    text=extract_pdf_text(uploaded)
    def find(pattern, default=''):
        m=re.search(pattern,text,re.I|re.M); return m.group(1).strip() if m else default
    inv=find(r'(?:invoice\s*(?:no|number|#))\s*[:#-]?\s*([A-Za-z0-9_-]+)')
    supplier=find(r'(?:supplier|vendor|seller)\s*(?:name)?\s*[:#-]?\s*([^\n]+)')
    amount=find(r'(?:invoice\s*amount|total\s*amount|grand\s*total)\s*[:#-]?\s*[₹$]?\s*([0-9,]+(?:\.\d+)?)')
    po=find(r'(?:po\s*amount|purchase\s*order\s*amount)\s*[:#-]?\s*[₹$]?\s*([0-9,]+(?:\.\d+)?)')
    ig=find(r'(?:invoice\s*gstin)\s*[:#-]?\s*([A-Za-z0-9]+)')
    sg=find(r'(?:supplier\s*gstin|registered\s*gstin)\s*[:#-]?\s*([A-Za-z0-9]+)')
    it=find(r'(?:invoice\s*tds|tds\s*deducted)\s*[:#-]?\s*[₹$]?\s*([0-9,]+(?:\.\d+)?)')
    et=find(r'(?:expected\s*tds)\s*[:#-]?\s*[₹$]?\s*([0-9,]+(?:\.\d+)?)')
    ib=find(r'(?:invoice\s*bank\s*account)\s*[:#-]?\s*([0-9]+)')
    rb=find(r'(?:registered\s*bank\s*account)\s*[:#-]?\s*([0-9]+)')
    dup=find(r'(?:duplicate\s*invoice)\s*[:#-]?\s*(YES|NO)','NO')
    pt=find(r'(?:payment\s*terms)\s*[:#-]?\s*(Net\s*\d+)')
    ap=find(r'(?:agreed\s*(?:payment\s*)?terms)\s*[:#-]?\s*(Net\s*\d+)')
    return {'payment_terms':pt,'agreed_payment_terms':ap,'invoice_id':inv,'supplier_name':supplier,'invoice_amount':money(amount),'po_amount':money(po),'invoice_gstin':ig,'supplier_gstin':sg,'invoice_tds':money(it),'expected_tds':money(et),'invoice_bank_account':ib,'registered_bank_account':rb,'duplicate_flag':dup,'raw_text':text}
