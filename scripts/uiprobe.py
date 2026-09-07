"""Exercise the running UI's event endpoints through the Gradio client (no browser needed).

  PYTHONPATH=app python scripts/uiprobe.py
"""
from gradio_client import Client

client = Client("http://127.0.0.1:7860", verbose=False)
info = client.view_api(all_endpoints=True, return_format="dict", print_info=False)
named = info.get("named_endpoints", {})
print(f"{len(named)} named endpoints: {', '.join(sorted(named))}")
for name in ("/add_effect", "/load_preset", "/save_preset"):
    ep = named.get(name)
    if ep:
        print(f"  {name}: params={[p.get('label') for p in ep['parameters']]} returns={[r.get('label') for r in ep['returns']]}")

if "/add_effect" in named:
    print("add_effect('bitcrush') ->", client.predict("bitcrush", api_name="/add_effect"))
    print("add_effect('ring_mod') ->", client.predict("ring_mod", api_name="/add_effect"))
if "/save_preset" in named:
    print("save_preset ->", client.predict("probe-preset", "made by uiprobe", api_name="/save_preset"))
if "/load_preset" in named:
    print("load_preset ->", client.predict("probe-preset", api_name="/load_preset"))
