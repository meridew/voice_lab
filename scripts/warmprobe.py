"""Time two conversions through the running UI's /convert endpoint: the first loads the models, the second is warm.

  PYTHONPATH=app python scripts/warmprobe.py   (server started with VOICE_LAB_SHOW_API=1)
"""
import time

from gradio_client import Client

client = Client("http://127.0.0.1:7860", verbose=False)
source = "20260907-114706_male-stand-in.wav"
for label in ("cold", "warm"):
    t = time.time()
    out = client.predict(source, "harbour-master", "v1", False, 0, True, 15, 0.7, True, 0.7, 0.7, f"probe {label}", api_name="/convert")
    status = out[2] if isinstance(out, (list, tuple)) and len(out) > 2 else out
    print(f"{label}: {time.time() - t:.0f}s wall; status: {status}")
