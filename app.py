import os, json, io
from datetime import date
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
load_dotenv()
from ui.styles import apply_css, card
from database.database import init_db, get_cases, get_payments, add_payment, set_payment_status, payment_for_invoice, CASE_COLS, PAY_COLS
from analytics import cases_df, filter_cases, memory_stats, supplier_learning, terms_profile, payment_ledger, ledger_summary, RELEASABLE
from memory.memory_manager import HindsightMemory
from invoice.processor import process_invoice
from invoice.extractor import extract_invoice_fields
from agents.exception_agent import build_ai_explanation
from agents.decision import decide, simulate, ROLES, can_approve
from invoice.validator import detect_exception

st.set_page_config(page_title='AP Memory Agent', page_icon='🧾', layout='wide')
apply_css(); init_db()

@st.cache_resource
def get_memory(): return HindsightMemory()
memory=get_memory()
DATA='data/sample_invoices.csv'
TERMS=['Net 15','Net 30','Net 45','Net 60','Net 90']

def load_data(): return pd.read_csv(DATA)

def normalize(d):
    out=dict(d)
    for k in ['invoice_amount','po_amount','invoice_tds','expected_tds']: out[k]=float(out.get(k) or 0)
    return out

def invoice_detail_table(inv):
    labels={'invoice_id':'Invoice Number','supplier_name':'Supplier','invoice_amount':'Invoice Amount','po_amount':'PO Amount','invoice_gstin':'Invoice GSTIN','supplier_gstin':'Supplier GSTIN','invoice_tds':'Invoice TDS','expected_tds':'Expected TDS','invoice_bank_account':'Invoice Bank Account','registered_bank_account':'Registered Bank Account','duplicate_flag':'Duplicate Flag','payment_terms':'Payment Terms (invoice)','agreed_payment_terms':'Payment Terms (agreed)'}
    rows=[]
    for k,l in labels.items():
        v=inv.get(k,'')
        if k in ['invoice_amount','po_amount','invoice_tds','expected_tds']: v=f'₹{float(v):,.2f}'
        rows.append((l,str(v)))
    st.dataframe(pd.DataFrame(rows,columns=['Field','Value']),width='stretch',hide_index=True)

def process_and_show(inv, source='New Invoice'):
    inv=normalize(inv); df=load_data(); known=set(df.invoice_id.astype(str))
    if source=='Historical Dataset': known.discard(str(inv.get('invoice_id')))  # an invoice is not its own duplicate
    detection=process_invoice(inv,known)
    et=detection['exception_type']; supplier=inv.get('supplier_name')
    precedents=[] if et=='No Exception' else memory.recall(et,supplier)
    decision=decide(detection,precedents)
    ai_text, ai_mode=build_ai_explanation(inv,detection,precedents)
    iid=str(inv.get('invoice_id'))
    st.markdown(f'<div class="hero"><div class="invoice-id">🧾 INVOICE #{inv.get("invoice_id") or "UNKNOWN"}</div><div class="supplier">{supplier or "Supplier not extracted"} · {source}</div></div>',unsafe_allow_html=True)
    st.markdown('<div class="section">FULL INVOICE / BILL DETAILS</div>',unsafe_allow_html=True); invoice_detail_table(inv)
    st.markdown('<div class="section">DETECTION</div>',unsafe_allow_html=True)
    c1,c2,c3=st.columns(3); c1.metric('Primary exception',et); c2.metric('Risk',detection['risk']); c3.metric('Handling',decision['label'])
    for r in detection['reasons']: st.info(r)
    if len(detection.get('all_exceptions',[]))>1: st.warning('Multiple exceptions found: '+', '.join(detection['all_exceptions']))
    st.markdown('<div class="section">RECALLED FROM HINDSIGHT MEMORY</div>',unsafe_allow_html=True)
    st.caption(f'Memory backend: {memory.backend}'+(f' · note: {memory.error}' if memory.error else ''))
    if precedents:
        for p in precedents:
            st.markdown(f'<div class="card"><b>🧠 Precedent ({p["decision"]})</b><br/>{p["text"]}</div>',unsafe_allow_html=True)
    else: st.info('No matching prior decision for this supplier and exception type. Your decision will become the first precedent.')
    st.markdown('<div class="section">AGENT DECISION</div>',unsafe_allow_html=True)
    (st.success if decision['level'] in ('auto','clear') else st.warning)(f"{decision['label']}: {decision['note']}")
    st.markdown('<div class="section">AI AGENT ANALYSIS</div>',unsafe_allow_html=True)
    st.markdown(f'<div class="card"><span class="tag">{ai_mode}</span><br/><br/>{ai_text}</div>',unsafe_allow_html=True)
    st.markdown('<div class="section">RECOMMENDATION, APPROVAL & RETENTION</div>',unsafe_allow_html=True)
    st.success(detection['recommendation'])
    if decision['level'] in ('escalate','suggest'):
        need=decision['role']; me=st.session_state.get('role',ROLES[0])
        st.info(f'Sign-off required from: **{need}** (you are acting as **{me}**).')
        reason=st.text_input('Reason for the decision (required, kept in memory for future cases)',key='why_'+iid,placeholder='e.g. Vendor ships in full pallets, so this variance is expected')
        allowed=can_approve(me,need); ok_reason=len(reason.strip())>=5
        if not allowed: st.warning(f'{me} cannot sign off on this. Switch role in the sidebar or hand it to a {need}.')
        elif not ok_reason: st.caption('Enter a reason (at least 5 characters) to enable the buttons.')
        a,b=st.columns(2)
        def retain(outcome):
            memory.retain(iid,str(supplier),et,detection['risk'],detection['recommendation'],outcome,source,json.dumps(inv,default=str),me,reason.strip())
            st.success(f'{outcome.title()} decision by {me} retained in memory with your reason.')
        if a.button('✅ Approve resolution & retain',key='ok_'+iid,disabled=not(allowed and ok_reason)): retain('APPROVED')
        if b.button('⛔ Reject / hold payment & retain',key='no_'+iid,disabled=not(allowed and ok_reason)): retain('REJECTED')
    elif decision['level']=='auto':
        if st.button('🧾 Log auto-resolution (audit only, not retained)',key='auto_'+iid):
            from database.database import save_case
            save_case(iid,str(supplier),et,detection['risk'],detection['recommendation'],'APPROVED','auto',json.dumps(inv,default=str),'Agent (auto)','Auto-resolved from agreeing precedents')
            st.success('Logged. Auto-resolutions are not fed back into memory, so the agent cannot reinforce itself.')
    st.markdown('<div class="section">PAYMENT</div>',unsafe_allow_html=True)
    if et=='No Exception':
        if payment_for_invoice(iid): st.info('A payment already exists for this invoice. See Payment History.')
        elif st.button('💳 Mark Payment Ready',key='pay_'+iid):
            add_payment(iid,str(supplier),float(inv.get('invoice_amount',0)),'Ready',str(date.today()),f'PAY-{iid}')
            st.success('Payment marked Ready.')
    else: st.warning('Payment is blocked/held until the exception is resolved.')

st.sidebar.markdown('# 🧾 AP MEMORY AGENT')
st.sidebar.caption('AI Accounts Payable Exception & Hindsight Memory')
st.sidebar.caption(f'Memory: {memory.backend}')
st.sidebar.selectbox('Acting as (approver role)',ROLES,key='role',help='Medium risk needs a Junior AP Analyst if memory has agreeing precedents, otherwise a Senior Accountant. High needs a Senior Accountant. Critical needs a Finance Controller.')
menu=st.sidebar.radio('Navigation',['Dashboard','Process Invoice','Create New Invoice','Case History','Payment History','Memory Center'])

_cases=get_cases(1000)
if _cases:
    st.sidebar.download_button('Download case log (CSV)',pd.DataFrame(_cases,columns=CASE_COLS).to_csv(index=False),'ap_case_log.csv','text/csv')

if menu=='Dashboard':
    st.title('Accounts Payable Exception Agent')
    st.caption('Historical invoices provide experience. New invoices can be processed even when they are not in the dataset.')
    df=load_data(); cases=get_cases(); pays=get_payments()
    a,b,c,d=st.columns(4); a.metric('Demo Invoices',len(df)); b.metric('Retained Memories',len(cases)); c.metric('Payments',len(pays)); d.metric('Exception Types','6')
    st.markdown('<div class="section">50-INVOICE DEMO DATA</div>',unsafe_allow_html=True)
    st.dataframe(df,width='stretch',hide_index=True)
    st.markdown('<div class="section">MEMORY OFF vs ON (SIMULATION)</div>',unsafe_allow_html=True)
    st.caption('Replays the dataset in order. Assumes the approver approves every case. Synthetic data: shows the mechanism, not real savings.')
    if st.button('▶ Run simulation'):
        sim=pd.DataFrame(simulate(df,detect_exception))
        n=len(sim); one=(sim.level=='suggest'); auto=(sim.level=='auto')
        senior=(sim.needs.isin(['Senior Accountant','Finance Controller']))
        m1,m2,m3,m4=st.columns(4); m1.metric('Exceptions',n); m2.metric('Need senior or above, memory OFF',n); m3.metric('Need senior or above, memory ON',int(senior.sum())); m4.metric('Junior one-click / auto',f'{int((one&(sim.needs=="Junior AP Analyst")).sum())} / {int(auto.sum())}')
        st.line_chart(pd.DataFrame({'Memory OFF':range(1,n+1),'Memory ON':senior.cumsum().values},index=sim.seq))
        st.caption('Cumulative cases needing a Senior Accountant or Finance Controller. Policy keeps High risk with seniors and Critical with the Controller, so memory only relieves Medium-risk cases.')
        st.dataframe(sim,width='stretch',hide_index=True)

elif menu=='Process Invoice':
    st.title('Process Invoice')
    df=load_data(); choice=st.selectbox('Select historical invoice',df.invoice_id.tolist())
    row=df[df.invoice_id==choice].iloc[0].to_dict()
    if st.button('🔎 Analyze Selected Invoice'): st.session_state['selected_inv']=row
    if 'selected_inv' in st.session_state: process_and_show(st.session_state['selected_inv'],'Historical Dataset')

elif menu=='Create New Invoice':
    st.title('Create / Process New Invoice')
    st.caption('Enter a new bill manually or upload a PDF. Do not pre-select an exception — the agent detects it from the data.')
    tab1,tab2=st.tabs(['✍️ Manual Invoice','📄 Upload Invoice PDF'])
    with tab1:
        with st.form('new_invoice'):
            c1,c2=st.columns(2)
            invoice_id=c1.text_input('Invoice Number *',placeholder='INV-2051')
            supplier=c2.text_input('Supplier Name *',placeholder='NewTech Pvt Ltd')
            c3,c4=st.columns(2); amount=c3.number_input('Invoice Amount',min_value=0.0,step=1000.0); po=c4.number_input('PO Amount',min_value=0.0,step=1000.0)
            c5,c6=st.columns(2); ig=c5.text_input('Invoice GSTIN'); sg=c6.text_input('Supplier GSTIN')
            c7,c8=st.columns(2); it=c7.number_input('Invoice TDS',min_value=0.0,step=100.0); et=c8.number_input('Expected TDS',min_value=0.0,step=100.0)
            c9,c10=st.columns(2); ib=c9.text_input('Invoice Bank Account'); rb=c10.text_input('Registered Bank Account')
            c11,c12=st.columns(2); pt=c11.selectbox('Payment terms on invoice',TERMS); apt=c12.selectbox('Agreed supplier payment terms',TERMS)
            dup=st.selectbox('Duplicate Flag', ['NO','YES'])
            submit=st.form_submit_button('🤖 Analyze New Invoice')
        if submit:
            inv={'invoice_id':invoice_id,'supplier_name':supplier,'invoice_amount':amount,'po_amount':po,'invoice_gstin':ig,'supplier_gstin':sg,'invoice_tds':it,'expected_tds':et,'invoice_bank_account':ib,'registered_bank_account':rb,'duplicate_flag':dup,'payment_terms':pt,'agreed_payment_terms':apt}
            st.session_state['manual_inv']=inv
        if 'manual_inv' in st.session_state: process_and_show(st.session_state['manual_inv'],'New Manual Invoice')
    with tab2:
        up=st.file_uploader('Upload invoice PDF',type=['pdf'])
        if up:
            st.info('PDF extraction reads text-based invoices. You can review the extracted fields before analysis.')
            if st.button('📥 Extract Invoice Data'):
                try: st.session_state['pdf_inv']=extract_invoice_fields(up); st.session_state['pdf_go']=False; st.success('Invoice data extracted.')
                except Exception as e: st.error(f'PDF extraction failed: {e}')
        if 'pdf_inv' in st.session_state:
            inv=st.session_state['pdf_inv']; st.json({k:v for k,v in inv.items() if k!='raw_text'})
            if st.button('🤖 Analyze Extracted Invoice'): st.session_state['pdf_go']=True
            if st.session_state.get('pdf_go'): process_and_show(inv,'New PDF Invoice')

elif menu=='Case History':
    st.title('Case History')
    st.caption('Every human decision and audit-only auto-resolution, with who decided and why.')
    rows=get_cases(1000)
    if not rows: st.info('No retained resolutions yet. Process an exception and approve or reject it.')
    else:
        cdf=cases_df(rows); ms=memory_stats(cdf)
        m1,m2,m3,m4=st.columns(4); m1.metric('Human decisions',ms['total']); m2.metric('Approved',ms['approved']); m3.metric('Rejected',ms['rejected']); m4.metric('Auto-resolved (audit)',ms['auto'])
        f1,f2,f3,f4=st.columns(4); opt=lambda c:['All']+sorted(cdf[c].unique().tolist())
        fs=f1.selectbox('Supplier',opt('Supplier')); fe=f2.selectbox('Exception',opt('Exception')); fr=f3.selectbox('Risk',opt('Risk')); fo=f4.selectbox('Outcome',opt('Outcome'))
        g1,g2=st.columns([1,2]); fl=g1.selectbox('Approver role',opt('Approver role')); ft=g2.text_input('Search invoice, supplier or reason')
        view=filter_cases(cdf,fs,fe,fr,fo,fl,ft)
        st.caption(f'Showing {len(view)} of {len(cdf)} cases')
        st.dataframe(view[['ID','Invoice','Supplier','Exception','Risk','Outcome','Approver role','Reason','Learned by agent','Created']],width='stretch',hide_index=True)
        st.download_button('Download filtered cases (CSV)',view.drop(columns=['Details']).to_csv(index=False),'ap_cases_filtered.csv','text/csv')
        if not view.empty:
            st.markdown('<div class="section">CASE DETAIL</div>',unsafe_allow_html=True)
            pick=st.selectbox('Open a case',view.ID.tolist(),format_func=lambda i:f"#{i} · {view[view.ID==i].iloc[0].Invoice} · {view[view.ID==i].iloc[0].Exception} · {view[view.ID==i].iloc[0].Outcome}")
            c=view[view.ID==pick].iloc[0]
            tag='Retained in memory' if c['Learned by agent'] else 'Audit only, not fed back into memory'
            st.markdown(f'<div class="card"><span class="tag">{tag}</span><span class="tag">{c.Risk} risk</span><br/><br/><b>{c.Invoice} · {c.Supplier}</b><br/>Exception: {c.Exception}<br/>Recommended action: {c.Recommendation}<br/>Decision: <b>{c.Outcome}</b> by {c["Approver role"]} on {c.Created}<br/>Reason: {c.Reason or "—"}</div>',unsafe_allow_html=True)
            try:
                d=json.loads(c.Details or '{}'); st.dataframe(pd.DataFrame(list(d.items()),columns=['Field','Value']).astype(str),width='stretch',hide_index=True)
            except Exception: pass
            same=cdf[(cdf.Supplier==c.Supplier)&(cdf.Exception==c.Exception)&(cdf.ID!=c.ID)&cdf['Learned by agent']]
            if not same.empty:
                st.markdown('<div class="section">OTHER DECISIONS FOR THIS SUPPLIER AND EXCEPTION</div>',unsafe_allow_html=True)
                st.dataframe(same[['ID','Invoice','Outcome','Approver role','Reason','Created']],width='stretch',hide_index=True)

elif menu=='Payment History':
    st.title('Payment History')
    st.caption('Where every invoice stands for payment, and what each supplier\'s payment terms look like. Payments stay downstream of exception resolution.')
    inv_df=load_data(); led=payment_ledger(inv_df,get_payments(1000),get_cases(1000)); sm=ledger_summary(led)
    a,b,c,d=st.columns(4); a.metric('Paid',f"₹{sm['paid']:,.0f}"); b.metric('Ready to pay',f"₹{sm['ready']:,.0f}"); c.metric('Awaiting release',f"₹{sm['awaiting']:,.0f}"); d.metric('Held by exceptions',f"₹{sm['held']:,.0f}")
    t1,t2,t3=st.tabs(['📒 Invoice payment status','🗓 Supplier payment terms','🧾 Payment log'])
    with t1:
        f1,f2=st.columns(2)
        fs=f1.selectbox('Supplier',['All']+sorted(led.Supplier.unique().tolist()),key='pl_s'); fst=f2.selectbox('Status',['All']+sorted(led['Payment status'].unique().tolist()),key='pl_st')
        v=led if fs=='All' else led[led.Supplier==fs]; v=v if fst=='All' else v[v['Payment status']==fst]
        st.dataframe(v,width='stretch',hide_index=True)
        st.markdown('<div class="section">RELEASE PAYMENT</div>',unsafe_allow_html=True)
        rel=led[led['Payment status'].isin(RELEASABLE)]
        if rel.empty: st.info('Nothing is ready to release. Resolve exceptions first, or every clear invoice already has a payment.')
        else:
            pick=st.selectbox('Invoice',rel.Invoice.tolist(),format_func=lambda i:f"{i} · {rel[rel.Invoice==i].iloc[0].Supplier} · ₹{rel[rel.Invoice==i].iloc[0].Amount:,.0f} · {rel[rel.Invoice==i].iloc[0]['Payment status']}")
            if st.button('💳 Mark Payment Ready',key='rel_btn'):
                r=rel[rel.Invoice==pick].iloc[0]
                if payment_for_invoice(pick): st.warning('A payment already exists for this invoice.')
                else: add_payment(pick,r.Supplier,float(r.Amount),'Ready',str(date.today()),f'PAY-{pick}'); st.success(f'{pick} marked Ready.'); st.rerun()
    with t2:
        tp=terms_profile(inv_df); st.dataframe(tp,width='stretch',hide_index=True)
        st.caption('Mismatch % is the share of a supplier\'s invoices billed on terms different from the agreed terms. Repeat offenders are where memory helps most.')
        sup=st.selectbox('Supplier detail',tp.Supplier.tolist(),key='terms_sup')
        sd=led[led.Supplier==sup]; st.dataframe(sd[['Invoice','Amount','Billed terms','Agreed terms','Exception','Payment status']],width='stretch',hide_index=True)
        tm=cases_df(get_cases(1000)) if get_cases(1) else None
        if tm is not None:
            tm=tm[(tm.Supplier==sup)&(tm.Exception=='Payment Terms Mismatch')&tm['Learned by agent']]
            if not tm.empty:
                st.markdown('<div class="section">HOW PAST TERMS MISMATCHES WERE DECIDED</div>',unsafe_allow_html=True)
                st.dataframe(tm[['Invoice','Outcome','Approver role','Reason','Created']],width='stretch',hide_index=True)
    with t3:
        pr=get_payments(1000)
        if not pr: st.info('No payments marked Ready yet.')
        else:
            pdf=pd.DataFrame(pr,columns=PAY_COLS); st.dataframe(pdf,width='stretch',hide_index=True)
            ready=pdf[pdf.Status=='Ready']
            if not ready.empty:
                pid=st.selectbox('Mark as Paid',ready.ID.tolist(),format_func=lambda i:f"{ready[ready.ID==i].iloc[0].Reference} · ₹{ready[ready.ID==i].iloc[0].Amount:,.0f}")
                if st.button('✅ Mark Paid',key='paid_btn'): set_payment_status(int(pid),'Paid',str(date.today())); st.rerun()
            st.download_button('Download payment log (CSV)',pdf.to_csv(index=False),'ap_payments.csv','text/csv')

else:
    st.title('Hindsight Memory Center')
    st.caption('What the agent has retained, what it has learned per supplier, and what it would do right now.')
    st.info(f'Memory backend: **{memory.backend}**'+(f' · note: {memory.error}' if memory.error else ''))
    rows=get_cases(1000); cdf=cases_df(rows) if rows else None
    if cdf is not None:
        ms=memory_stats(cdf)
        a,b,c,d,e=st.columns(5); a.metric('Retained memories',ms['total']); b.metric('Approved',ms['approved']); c.metric('Rejected',ms['rejected']); d.metric('Suppliers learned',ms['suppliers']); e.metric('With a reason',ms['with_reason'])
        st.markdown('<div class="section">WHAT THE AGENT HAS LEARNED PER SUPPLIER</div>',unsafe_allow_html=True)
        st.dataframe(supplier_learning(cdf),width='stretch',hide_index=True)
        st.markdown('<div class="section">RETAINED MEMORIES</div>',unsafe_allow_html=True)
        f1,f2,f3=st.columns(3); fs=f1.selectbox('Supplier',['All']+sorted(cdf.Supplier.unique().tolist()),key='mc_s'); fe=f2.selectbox('Exception',['All']+sorted(cdf.Exception.unique().tolist()),key='mc_e'); ft=f3.text_input('Search reasons',key='mc_t')
        mem=filter_cases(cdf[cdf['Learned by agent']],fs,fe,text=ft)
        st.dataframe(mem[['Invoice','Supplier','Exception','Risk','Outcome','Approver role','Reason','Created']],width='stretch',hide_index=True)
        st.download_button('Download memories (CSV)',mem.drop(columns=['Details']).to_csv(index=False),'ap_memories.csv','text/csv')
    else: st.info('Memory is empty. Process and approve an exception to create the first retained case.')
    st.markdown('<div class="section">RECALL TEST: WHAT WOULD THE AGENT DO NOW?</div>',unsafe_allow_html=True)
    r1,r2=st.columns(2); rs=r1.selectbox('Supplier',sorted(load_data().supplier_name.unique()),key='rt_s')
    rt=r2.selectbox('Exception type',['PO Variance','TDS Mismatch','GSTIN Mismatch','Duplicate Invoice','Payment Terms Mismatch','Bank Account Change'],key='rt_e')
    if st.button('🔍 Test recall'):
        risk={'Bank Account Change':'Critical','GSTIN Mismatch':'High','Duplicate Invoice':'High'}.get(rt,'Medium')
        prec=memory.recall(rt,rs); dec=decide({'exception_type':rt,'risk':risk},prec)
        st.success(f"{dec['label']}: {dec['note']}"+(f" Sign-off: {dec['role']}." if dec['role'] else ''))
        for p in prec: st.markdown(f'<div class="card"><b>🧠 Precedent ({p["decision"]})</b><br/>{p["text"]}</div>',unsafe_allow_html=True)
        if not prec: st.caption('No matching precedents yet.')
    st.markdown('<div class="section">BRIEF ME (REFLECT)</div>',unsafe_allow_html=True)
    sup=st.selectbox('Supplier',sorted(load_data().supplier_name.unique()),key='br_s')
    if st.button('🧠 Brief me on this supplier'): st.markdown(f'<div class="card">{memory.reflect(sup)}</div>'.replace(chr(10),'<br/>'),unsafe_allow_html=True)
