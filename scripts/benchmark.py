"""Bounded synthetic workload, not a production throughput guarantee."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from repere.adapters import prepare
from repere.demo import payload
from repere.valuation import rank

items,_=prepare(payload(),'demo')
rows=[]
for i in range(2000):
    row=items[(i%6)*16].to_dict()
    row.update(id=f'benchmark-{i}',group_id=f'benchmark-{i}',price_cents=1_000_000+(i%30)*10000)
    rows.append(row)
started=time.perf_counter()
result=rank(rows)
print(json.dumps({'synthetic_records':len(rows),'ranked':len(result),'seconds':round(time.perf_counter()-started,3),
    'scope':'One synthetic process run, repeated signatures, no concurrency or throughput guarantee'}))
