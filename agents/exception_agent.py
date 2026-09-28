import os

def build_ai_explanation(inv, detection, memories):
    key=os.getenv('GEMINI_API_KEY','').strip()
    if key:
        try:
            from google import genai
            client=genai.Client(api_key=key)
            prompt=f"You are an accounts-payable exception agent. Invoice {inv.get('invoice_id')} from {inv.get('supplier_name')}. Detection: {detection}. Past decisions for this supplier and exception type: {[m['text'] for m in memories]}. Give concise audit-safe reasoning, recommendation, and human approval requirement. Do not invent facts."
            r=client.models.generate_content(model=os.getenv('GEMINI_MODEL','gemini-2.5-flash'), contents=prompt)
            return r.text, 'Gemini'
        except Exception as e:
            return fallback(inv,detection,memories), 'Local fallback (Gemini unavailable)'
    return fallback(inv,detection,memories), 'Local AI-style reasoning (no LLM required)'

def fallback(inv,detection,memories):
    et=detection['exception_type']
    if et=='No Exception':
        action='Continue normal processing; no exception was detected.'
    else:
        action=detection['recommendation']
    memory_note = f" I found {len(memories)} prior {et} case(s) in Hindsight memory." if memories else ' No prior matching resolution was found in memory.'
    return f"For invoice {inv.get('invoice_id')} ({inv.get('supplier_name')}), the detected state is {et} with {detection['risk']} risk. {detection['reasons'][0] if detection['reasons'] else ''} {action}{memory_note} A human should approve any payment hold, block, bank change, tax correction, or procurement escalation."
