"""Ad-hoc test of the admin endpoints (not part of the app)."""
import os
import sys
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    r = client.get("/admin/summary")
    j = r.json()
    print("summary: total=%d enabled=%d ai=%s" % (
        j["resources_total"], j["resources_enabled"], j["ai_models"]))

    r = client.get("/admin/resources")
    for cat, lst in r.json().items():
        print(cat, "->", [x["id"] for x in lst])

    r = client.put("/admin/resources/solar_pv", json={"status": "OFFLINE"})
    print("solar ->", r.json()["resource"]["status"])

    r = client.get("/admin/resources/solar_pv")
    print("get solar status:", r.json()["status"])

    r = client.post("/admin/resources/solar_pv/toggle", params={"online": True})
    print("toggle solar online ->", r.json()["status"])

    r = client.put("/admin/resources/battery", json={"soc_percent": 85})
    print("battery soc ->", r.json()["resource"]["soc_percent"])

    r = client.put("/admin/config", json={"name": "Polar Station B"})
    print("station name ->", r.json()["updated"]["name"])
    # restore
    client.put("/admin/config", json={"name": "Polar Research Station A"})

    r = client.put("/admin/resources/battery", json={"soc_percent": 200})
    print("bad soc ->", r.status_code, r.json())

    r = client.put("/admin/resources/battery", json={"soc_percent": "abc"})
    print("non-numeric soc ->", r.status_code, r.json())

    r = client.put("/admin/resources/solar_pv", json={"status": "ZOMBIE"})
    print("bad status ->", r.status_code, r.json())

    r = client.put("/admin/resources/hydropower", json={"status": "ONLINE", "capacity_kw": 250})
    print("hydropower online ->", r.json()["resource"])