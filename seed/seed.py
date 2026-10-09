import boto3
from decimal import Decimal

table = boto3.resource("dynamodb", region_name="ap-south-1").Table("MonsoonOps")

SITE = "SITE#demo"

site = {
    "pk": SITE, "sk": "PROFILE",
    "name": "Green Meadows Apartments (demo)",
    "basementLevels": 2,
    "lowLying": True,
    "floodHistory": True,
    "pumpStatus": "untested",
    "roofAreaM2": 800,
    "runoffCoeff": Decimal("0.8"),
    "rainwaterPits": ["PIT-1", "PIT-2"],
    "lowLyingBays": ["B2-01", "B2-02", "B2-03"],
    "moveToSlots": [f"P1-{i:02d}" for i in range(1, 13)],
    "thresholds": {"watchMm": Decimal("64.5"), "highMm": Decimal("115.6")},
}

# (role, title, critical, evidence)
templates = [
    ("admin", "Confirm the rain trigger and review site status", False, "none"),
    ("admin", "Confirm free move-to slots on higher levels", False, "none"),
    ("security", "Clear the basement ramp", True, "photo"),
    ("security", "Check the pump panel has power", True, "photo"),
    ("security", "Check in on opted-in vulnerable residents", True, "second_person"),
    ("security", "Move visitor vehicles out of basement", False, "second_person"),
    ("maintenance", "Clear drain gratings", True, "photo"),
    ("maintenance", "Clear the sump pit", True, "photo"),
    ("maintenance", "Run a pump test", True, "testlog"),
    ("maintenance", "Inspect rainwater inlet and recharge pit", True, "photo"),
    ("resident", "Move your vehicle to your assigned slot", True, "none"),
]

items = [site]

for role, title, critical, evidence in templates:
    items.append({
        "pk": "TEMPLATE", "sk": f"{role}#{title}",
        "role": role, "title": title,
        "critical": critical, "evidence": evidence,
    })

# 10 vehicles: 5 on B2 (lowest), 5 on B1
n = 1
for level in ("B2", "B1"):
    for bay in range(1, 6):
        items.append({
            "pk": SITE, "sk": f"VEH#{n:03d}",
            "owner": f"Demo Resident {n}",
            "flat": f"A-{100 + n}",
            "plateLast4": f"{1000 + n * 37}",
            "level": level,
            "bay": f"{level}-{bay:02d}",
            "moveToSlot": f"P1-{n:02d}",
            "moved": False,
        })
        n += 1

with table.batch_writer() as batch:
    for item in items:
        batch.put_item(Item=item)

print(f"Loaded {len(items)} items")