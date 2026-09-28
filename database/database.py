import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "ap_memory.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = connect(); cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT, supplier TEXT,
        exception_type TEXT, risk TEXT, recommendation TEXT, outcome TEXT,
        source TEXT, details TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    for col in ('approver_role', 'reason'):  # added in v8; safe on an existing v7 database
        try: cur.execute(f"ALTER TABLE cases ADD COLUMN {col} TEXT DEFAULT ''")
        except sqlite3.OperationalError: pass
    cur.execute("""CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT, supplier TEXT,
        amount REAL, status TEXT, payment_date TEXT, reference TEXT)""")
    con.commit(); con.close()

CASE_COLS = ['ID','Invoice','Supplier','Exception','Risk','Recommendation','Outcome','Source','Details','Created','Approver role','Reason']

def save_case(invoice_id, supplier, exception_type, risk, recommendation, outcome, source, details, role='', reason=''):
    con=connect(); con.execute("INSERT INTO cases(invoice_id,supplier,exception_type,risk,recommendation,outcome,source,details,approver_role,reason) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (invoice_id,supplier,exception_type,risk,recommendation,outcome,source,details,role,reason)); con.commit(); con.close()

def get_cases(limit=100):
    con=connect(); rows=con.execute("SELECT * FROM cases ORDER BY id DESC LIMIT ?",(limit,)).fetchall(); con.close(); return rows

def add_payment(invoice_id,supplier,amount,status,payment_date,reference):
    con=connect(); con.execute("INSERT INTO payments(invoice_id,supplier,amount,status,payment_date,reference) VALUES(?,?,?,?,?,?)",(invoice_id,supplier,amount,status,payment_date,reference)); con.commit(); con.close()

def get_payments(limit=100):
    con=connect(); rows=con.execute("SELECT * FROM payments ORDER BY id DESC LIMIT ?",(limit,)).fetchall(); con.close(); return rows

def payment_for_invoice(invoice_id):
    con=connect(); row=con.execute("SELECT * FROM payments WHERE invoice_id=? ORDER BY id DESC LIMIT 1",(str(invoice_id),)).fetchone(); con.close(); return row

def set_payment_status(payment_id,status,payment_date=None):
    con=connect()
    if payment_date: con.execute("UPDATE payments SET status=?, payment_date=? WHERE id=?",(status,payment_date,payment_id))
    else: con.execute("UPDATE payments SET status=? WHERE id=?",(status,payment_id))
    con.commit(); con.close()

PAY_COLS = ['ID','Invoice','Supplier','Amount','Status','Date','Reference']
