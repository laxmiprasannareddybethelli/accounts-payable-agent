from invoice.validator import detect_exception

def process_invoice(inv, historical_ids=None):
    return detect_exception(inv, historical_ids=historical_ids)
