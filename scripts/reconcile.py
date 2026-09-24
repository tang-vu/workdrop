"""Print the complete local supply reconciliation without exposing private media."""
import json
import os
from app.store import Store, UNIT

state=Store(os.getenv("WORKDROP_DATA_DIR","data")).snapshot()
print(json.dumps({"mode":state["mode"],"base_units_per_credit":UNIT,"balances":{k:v["units"] for k,v in state["balances"].items()},"reconciliation":state["reconciliation"],"pool_quote_cash_cents":state["batch"]["pool_cash_cents"]},indent=2))
