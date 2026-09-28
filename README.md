# Accounts Payable Exception Agent

An AP agent that remembers how each invoice exception was resolved for each supplier, using [Hindsight](https://github.com/vectorize-io/hindsight) agent memory. Nothing is retrained: the agent improves only because its memory fills up.

## How memory drives decisions
- **Retain:** when an approver approves or rejects an exception, the decision is stored in Hindsight as a plain-English sentence.
- **Recall:** for each new exception, the agent recalls past decisions for the *same supplier and exception type*.
- **Reflect:** "Brief me" in the Memory Center asks Hindsight to summarise what it has learned about a supplier.

| Past decisions found | Agent action | Sign-off needed |
|---|---|---|
| None | Full manual review | Senior Accountant |
| One | One-click approval suggested | Junior AP Analyst |
| Two or more that agree (Medium risk, approved) | Auto-resolved, precedents shown | Nobody |
| Precedents that disagree | Full manual review | Senior Accountant |
| Any number, High risk | Human approves (never auto) | Senior Accountant |
| Any number, Critical risk (bank change) | Never auto | Finance Controller |

## Approval workflow (v8)
Pick your role in the sidebar. A role can only sign off cases at or below its level, and every approve or reject needs a written reason. The role and reason are stored in Hindsight with the decision (for example: "Approver decision: APPROVED. Decided by: Senior Accountant. Reason: vendor ships in full pallets."), so later recalls show *why* a past case was decided, not just what was decided. Memory lowers the required role only for Medium risk.

Auto-resolutions are logged for audit but not retained, so the agent cannot reinforce its own decisions.

## Exceptions detected (from fields only, no label column)
GSTIN mismatch, PO variance, duplicate invoice (flag or reused number), TDS mismatch, bank account change, payment terms mismatch (invoice terms differ from the supplier's agreed terms; skipped if either is blank). All are reported; the most severe is primary.

## Run on Windows
```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # add your Hindsight URL and API key
python -m streamlit run app.py
```
The sidebar shows `Memory: Hindsight Cloud` when the real backend is active.

## Demo flow
1. Process Invoice: pick an exception invoice, show "no precedent", approve and retain.
2. Process another invoice from the same supplier and type: one-click suggestion citing the first decision.
3. A third one (Medium risk): auto-resolved with cited precedents.
4. Dashboard: run the memory OFF vs ON simulation.
5. Memory Center: Brief me on a supplier.

## Limits
Data is synthetic, and the simulation assumes the approver approves everything, so it shows the mechanism rather than real savings. Tests: `python -m pytest`.

## v9 upgrades
- **Payment History** (replaces Payments): per-invoice payment status (clear / held / approved / rejected / ready / paid), release and mark-paid actions, supplier payment-terms profile with mismatch rates, and how past terms mismatches were decided.
- **Case History**: filters (supplier, exception, risk, outcome, role), reason search, case detail with invoice fields and other decisions for the same supplier and exception, CSV export.
- **Memory Center**: backend status, stats, per-supplier "what the agent has learned", filterable memories, a Recall test showing what the agent would do now, and Brief me.
- Fixed: invoice detail table crashed on mixed number/text values; Streamlit `use_container_width` replaced with `width='stretch'` (requires streamlit>=1.50).
Logic lives in `analytics.py` and is covered by tests (`python -m pytest`).
