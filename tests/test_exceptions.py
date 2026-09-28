from invoice.validator import detect_exception
from agents.decision import decide, simulate, can_approve, required_role
import pandas as pd

def base():
    return {'invoice_id':'INV-X','supplier_name':'Test','invoice_amount':100,'po_amount':100,'invoice_gstin':'A','supplier_gstin':'A','invoice_tds':10,'expected_tds':10,'invoice_bank_account':'1','registered_bank_account':'1','duplicate_flag':'NO'}

def test_po():
    x=base(); x['invoice_amount']=120; assert detect_exception(x)['exception_type']=='PO Variance'
def test_gstin():
    x=base(); x['supplier_gstin']='B'; assert detect_exception(x)['exception_type']=='GSTIN Mismatch'
def test_duplicate():
    x=base(); x['duplicate_flag']='YES'; assert detect_exception(x)['exception_type']=='Duplicate Invoice'
def test_duplicate_by_id():
    assert detect_exception(base(),{'INV-X'})['exception_type']=='Duplicate Invoice'
def test_own_id_not_duplicate():
    assert detect_exception(base(),set())['exception_type']=='No Exception'
def test_tds():
    x=base(); x['invoice_tds']=5; assert detect_exception(x)['exception_type']=='TDS Mismatch'
def test_bank():
    x=base(); x['invoice_bank_account']='2'; assert detect_exception(x)['exception_type']=='Bank Account Change'
def test_clean():
    assert detect_exception(base())['exception_type']=='No Exception'
def test_most_severe_wins_and_all_reported():
    x=base(); x['invoice_amount']=120; x['invoice_bank_account']='2'
    d=detect_exception(x); assert d['exception_type']=='Bank Account Change' and len(d['all_exceptions'])==2

def P(*d): return [{'decision':v} for v in d]
med={'exception_type':'PO Variance','risk':'Medium'}
high={'exception_type':'GSTIN Mismatch','risk':'High'}
crit={'exception_type':'Bank Account Change','risk':'Critical'}
def test_ladder():
    assert decide(med,[])['level']=='escalate'
    assert decide(med,P('APPROVED'))['level']=='suggest'
    assert decide(med,P('APPROVED','APPROVED'))['level']=='auto'
    assert decide(med,P('APPROVED','REJECTED'))['level']=='escalate'
    assert decide(med,P('REJECTED','REJECTED'))['level']=='suggest'
def test_high_and_critical_never_auto():
    assert decide(high,P('APPROVED','APPROVED','APPROVED'))['level']=='suggest'
    assert decide(crit,P('APPROVED','APPROVED','APPROVED'))['level']=='escalate'
def test_simulation_memory_reduces_reviews():
    df=pd.read_csv('data/sample_invoices.csv'); rows=simulate(df,detect_exception)
    esc=sum(r['level']=='escalate' for r in rows)
    assert 0<esc<len(rows) and not any(r['level']=='auto' and r['risk']!='Medium' for r in rows)

def test_terms_mismatch():
    x=base(); x['payment_terms']='Net 60'; x['agreed_payment_terms']='Net 30'
    d=detect_exception(x); assert d['exception_type']=='Payment Terms Mismatch' and d['risk']=='Medium'
def test_terms_match_or_unknown_is_clean():
    x=base(); x['payment_terms']='net 30'; x['agreed_payment_terms']='Net 30'; assert detect_exception(x)['exception_type']=='No Exception'
    x['agreed_payment_terms']=''; x['payment_terms']='Net 60'; assert detect_exception(x)['exception_type']=='No Exception'
terms={'exception_type':'Payment Terms Mismatch','risk':'Medium'}
def test_role_routing_and_memory_lowers_it():
    assert decide(med,[])['role']=='Senior Accountant'
    assert decide(med,P('APPROVED'))['role']=='Junior AP Analyst'
    assert decide(med,P('APPROVED','APPROVED'))['role'] is None
    assert decide(high,P('APPROVED','APPROVED'))['role']=='Senior Accountant'
    assert decide(crit,P('APPROVED','APPROVED'))['role']=='Finance Controller'
    assert decide(terms,P('APPROVED'))['role']=='Junior AP Analyst'
def test_permissions():
    assert not can_approve('Junior AP Analyst','Senior Accountant')
    assert can_approve('Finance Controller','Senior Accountant') and can_approve('Senior Accountant','Senior Accountant')
    assert can_approve('Junior AP Analyst',None)
def test_simulation_moves_work_down():
    df=pd.read_csv('data/sample_invoices.csv'); rows=simulate(df,detect_exception)
    assert any(r['needs']=='Junior AP Analyst' for r in rows)
    assert all(r['needs']!='Junior AP Analyst' for r in rows if r['risk'] in ('High','Critical'))
    assert any(r['exception']=='Payment Terms Mismatch' for r in rows)

# ---- v9: analytics behind Payment History, Case History, Memory Center ----
from analytics import cases_df, filter_cases, memory_stats, supplier_learning, terms_profile, payment_ledger, ledger_summary

def _case(i, inv, sup, et, out, src='New', role='Senior Accountant', reason='ok reason'):
    return (i, inv, sup, et, 'Medium', 'rec', out, src, '{}', '2026-09-28', role, reason)

CASES = [_case(1,'INV-1','A','PO Variance','APPROVED'), _case(2,'INV-2','A','PO Variance','APPROVED'),
         _case(3,'INV-3','B','TDS Mismatch','APPROVED'), _case(4,'INV-4','B','TDS Mismatch','REJECTED'),
         _case(5,'INV-5','A','PO Variance','APPROVED','auto','Agent (auto)','Auto')]

def test_memory_stats_excludes_auto():
    s = memory_stats(cases_df(CASES))
    assert (s['total'], s['approved'], s['rejected'], s['auto'], s['suppliers']) == (4, 3, 1, 1, 2)
def test_empty_stats():
    assert memory_stats(cases_df([]))['total'] == 0
def test_filters_and_search():
    df = cases_df(CASES)
    assert len(filter_cases(df, supplier='B')) == 2
    assert len(filter_cases(df, outcome='REJECTED')) == 1
    assert len(filter_cases(df, text='INV-3')) == 1
    assert len(filter_cases(df, supplier='A', exception='PO Variance', role='Senior Accountant')) == 2
def test_supplier_learning_readiness():
    sl = supplier_learning(cases_df(CASES)).set_index('Supplier')
    assert sl.loc['A','Decisions'] == 2 and sl.loc['A','Agent readiness'] == 'Has agreeing precedents'
    assert sl.loc['B','Agent readiness'] == 'Precedents disagree' and sl.loc['B','Approval %'] == 50
def test_terms_profile():
    tp = terms_profile(pd.read_csv('data/sample_invoices.csv')).set_index('Supplier')
    assert tp.loc['Tech Solutions','Terms mismatches'] == 2 and tp.loc['Global Traders','Terms mismatches'] == 0
def test_payment_ledger_states():
    inv = pd.read_csv('data/sample_invoices.csv'); led = payment_ledger(inv, [], [])
    assert len(led) == len(inv) and set(led['Payment status']) == {'Held – exception unresolved', 'Clear – awaiting payment'}
    clear = led[led['Payment status'] == 'Clear – awaiting payment'].Invoice.iloc[0]
    held = led[led['Payment status'] == 'Held – exception unresolved'].Invoice.iloc[0]
    pays = [(1, clear, 'X', 100.0, 'Paid', '2026-09-28', 'PAY-1')]
    cases = [(1, held, 'X', 'PO Variance', 'Medium', 'r', 'APPROVED', 'New', '{}', 't', 'Senior Accountant', 'why now')]
    l2 = payment_ledger(inv, pays, cases).set_index('Invoice')
    assert l2.loc[clear,'Payment status'] == 'Paid' and l2.loc[held,'Payment status'] == 'Exception approved – ready to release'
    cases[0] = cases[0][:6] + ('REJECTED',) + cases[0][7:]
    assert payment_ledger(inv, pays, cases).set_index('Invoice').loc[held,'Payment status'] == 'Rejected – payment on hold'
def test_ledger_summary_adds_up():
    inv = pd.read_csv('data/sample_invoices.csv'); led = payment_ledger(inv, [], []); s = ledger_summary(led)
    assert abs(sum(s.values()) - led.Amount.sum()) < 0.01
