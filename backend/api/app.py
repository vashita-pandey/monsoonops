import json
import os
import boto3
from botocore.config import Config
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from rules import evaluate

table = boto3.resource("dynamodb").Table(os.environ.get("TABLE_NAME", "MonsoonOps"))
BUCKET = os.environ.get("EVIDENCE_BUCKET", "monsoonops-evidence-366339682342")
s3 = boto3.client(
    "s3",
    region_name="ap-south-1",
    endpoint_url="https://s3.ap-south-1.amazonaws.com",
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

SIMULATED_FORECAST_MM = 90
STAGES = ["issued", "admin_notified", "site_red", "locked"]
UPLOAD_TYPES = {"image/jpeg": "jpg", "image/png": "png", "text/plain": "txt"}


# ---------- helpers ----------

def to_json(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(f"Cannot serialize {type(o)}")


def respond(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=to_json),
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except ValueError:
        return {}


def log(inc_id, actor, action):
    table.put_item(Item={
        "pk": f"INC#{inc_id}", "sk": f"LOG#{now_iso()}",
        "actor": actor, "action": action,
    })


def set_fields(key, fields):
    names = {f"#f{i}": k for i, k in enumerate(fields)}
    values = {f":v{i}": v for i, v in enumerate(fields.values())}
    expr = "SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields)))
    table.update_item(
        Key=key, UpdateExpression=expr,
        ExpressionAttributeNames=names, ExpressionAttributeValues=values,
    )


# ---------- site ----------

def get_site(site_id):
    item = table.get_item(Key={"pk": f"SITE#{site_id}", "sk": "PROFILE"}).get("Item")
    if not item:
        return respond(404, {"error": "site not found"})
    return respond(200, item)


# ---------- incidents and tasks ----------

def get_incident(inc_id):
    return table.get_item(Key={"pk": "SITE#demo", "sk": f"INC#{inc_id}"}).get("Item")


def latest_incident_id():
    r = table.query(
        KeyConditionExpression=Key("pk").eq("SITE#demo") & Key("sk").begins_with("INC#"),
        ScanIndexForward=False, Limit=1,
    )
    return r["Items"][0]["incidentId"] if r["Items"] else None


def load_task(inc_id, task_id):
    return table.get_item(Key={"pk": f"INC#{inc_id}", "sk": f"TASK#{task_id}"}).get("Item")


def all_tasks(inc_id):
    return table.query(
        KeyConditionExpression=Key("pk").eq(f"INC#{inc_id}") & Key("sk").begins_with("TASK#")
    )["Items"]


def simulate(site_id):
    site = table.get_item(Key={"pk": f"SITE#{site_id}", "sk": "PROFILE"}).get("Item")
    if not site:
        return respond(404, {"error": "site not found"})

    level, reason = evaluate(SIMULATED_FORECAST_MM, site)
    inc_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    inc_pk = f"INC#{inc_id}"

    templates = table.query(KeyConditionExpression=Key("pk").eq("TEMPLATE"))["Items"]
    vehicles = table.query(
        KeyConditionExpression=Key("pk").eq(f"SITE#{site_id}") & Key("sk").begins_with("VEH#")
    )["Items"]

    items = [
        {
            "pk": f"SITE#{site_id}", "sk": inc_pk,
            "incidentId": inc_id, "state": level,
            "triggerSource": "SIMULATED",
            "forecastMm": SIMULATED_FORECAST_MM,
            "reason": reason, "startedAt": now_iso(),
            "windowAt": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
            "timeOffsetMin": 0, "escalationStage": 0, "siteRed": False,
        },
        {
            "pk": inc_pk, "sk": f"LOG#{now_iso()}",
            "actor": "system",
            "action": f"Simulated rain started. Site set to {level}: {reason}",
        },
    ]

    n = 0

    def add_task(role, title, critical, evidence, extra=None):
        nonlocal n
        n += 1
        task = {
            "pk": inc_pk, "sk": f"TASK#{n:03d}",
            "taskId": f"{n:03d}", "incidentId": inc_id,
            "role": role, "title": title,
            "critical": critical, "evidence": evidence,
            "status": "open",
        }
        if extra:
            task.update(extra)
        items.append(task)

    for t in templates:
        if t["role"] == "resident":
            for v in vehicles:
                add_task(
                    "resident",
                    f"Move vehicle ending {v['plateLast4']} from {v['bay']} to {v['moveToSlot']}",
                    t["critical"], t["evidence"],
                    {"vehicleKey": v["sk"], "assignee": v["flat"]},
                )
        else:
            add_task(t["role"], t["title"], t["critical"], t["evidence"])

    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)

    return respond(200, {
        "incidentId": inc_id, "state": level,
        "reason": reason, "tasksCreated": n,
    })


def list_tasks(inc_id, role):
    items = all_tasks(inc_id)
    if role:
        items = [i for i in items if i["role"] == role]
    return respond(200, {"tasks": items})


def ack_task(inc_id, task_id, body):
    task = load_task(inc_id, task_id)
    if not task:
        return respond(404, {"error": "task not found"})
    who = body.get("by", "unknown")
    try:
        table.update_item(
            Key={"pk": f"INC#{inc_id}", "sk": f"TASK#{task_id}"},
            UpdateExpression="SET #s = :a, acknowledgedAt = :t, acknowledgedBy = :w",
            ConditionExpression="#s = :o",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":a": "acknowledged", ":o": "open", ":t": now_iso(), ":w": who,
            },
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(409, {"error": "task is not open"})
        raise
    log(inc_id, who, f"Acknowledged: {task['title']}")
    return respond(200, {"status": "acknowledged"})


def upload_url(inc_id, task_id, body):
    task = load_task(inc_id, task_id)
    if not task:
        return respond(404, {"error": "task not found"})
    content_type = body.get("contentType", "image/jpeg")
    if content_type not in UPLOAD_TYPES:
        return respond(400, {"error": "unsupported file type"})
    stamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
    key = f"{inc_id}/{task_id}/{stamp}.{UPLOAD_TYPES[content_type]}"
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=300,
    )
    return respond(200, {"uploadUrl": url, "key": key})


def complete_task(inc_id, task_id, body):
    task = load_task(inc_id, task_id)
    if not task:
        return respond(404, {"error": "task not found"})
    who = body.get("by", "unknown")
    evidence = (body.get("evidence") or "").strip()
    verified_by = (body.get("verifiedBy") or "").strip()
    need = task["evidence"]

    if need in ("photo", "testlog"):
        if not evidence:
            return respond(400, {"error": f"this task needs {need} evidence"})
        try:
            s3.head_object(Bucket=BUCKET, Key=evidence)
        except ClientError:
            return respond(400, {"error": "evidence file not found, upload it first"})
    if need == "second_person" and (not verified_by or verified_by == who):
        return respond(400, {"error": "this task needs a different person to confirm it"})

    try:
        table.update_item(
            Key={"pk": f"INC#{inc_id}", "sk": f"TASK#{task_id}"},
            UpdateExpression="SET #s = :d, doneAt = :t, doneBy = :w, evidenceKey = :e, verifiedBy = :v",
            ConditionExpression="#s <> :d",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":d": "done", ":t": now_iso(), ":w": who,
                ":e": evidence or "none", ":v": verified_by or "none",
            },
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return respond(409, {"error": "task is already done"})
        raise

    if task.get("vehicleKey"):
        table.update_item(
            Key={"pk": "SITE#demo", "sk": task["vehicleKey"]},
            UpdateExpression="SET moved = :m, movedAt = :t",
            ExpressionAttributeValues={":m": True, ":t": now_iso()},
        )

    log(inc_id, who, f"Completed: {task['title']} (proof: {need})")
    return respond(200, {"status": "done"})


def readiness(inc_id):
    tasks = all_tasks(inc_id)
    critical = [t for t in tasks if t["critical"]]
    done = [t for t in critical if t["status"] == "done"]
    vehicles = [t for t in tasks if t.get("vehicleKey")]
    moved = [t for t in vehicles if t["status"] == "done"]
    pct = round(100 * len(done) / len(critical)) if critical else 100
    return respond(200, {
        "readinessPercent": pct,
        "criticalDone": len(done),
        "criticalTotal": len(critical),
        "vehiclesMoved": len(moved),
        "vehiclesTotal": len(vehicles),
        "unacknowledged": len([t for t in tasks if t["status"] == "open"]),
    })


# ---------- escalation and time-warp ----------

def clock(inc):
    started = datetime.fromisoformat(inc["startedAt"])
    if inc.get("windowAt"):
        window = datetime.fromisoformat(inc["windowAt"])
    else:
        window = started + timedelta(hours=6)
    offset = int(inc.get("timeOffsetMin", 0))
    now = datetime.now(timezone.utc) + timedelta(minutes=offset)
    return (window - now).total_seconds() / 3600


def stage_for(hours_left):
    if hours_left <= 0:
        return 3
    if hours_left <= 1:
        return 2
    if hours_left <= 3:
        return 1
    return 0


def run_escalation(inc_id):
    inc = get_incident(inc_id)
    if not inc:
        return
    target = stage_for(clock(inc))
    current = int(inc.get("escalationStage", 0))
    if target <= current:
        return

    tasks = all_tasks(inc_id)
    updates = {"escalationStage": target}

    for s in range(current + 1, target + 1):
        if s == 1:
            open_tasks = [t for t in tasks if t["status"] == "open"]
            for t in open_tasks:
                set_fields({"pk": t["pk"], "sk": t["sk"]},
                           {"escalated": True, "escalatedAt": now_iso()})
            log(inc_id, "system",
                f"3 hours left: {len(open_tasks)} unacknowledged tasks escalated to admin and security head")
        elif s == 2:
            critical_open = [t for t in tasks if t["critical"] and t["status"] != "done"]
            residents_open = [t for t in tasks if t["role"] == "resident" and t["status"] != "done"]
            if critical_open:
                updates["siteRed"] = True
            log(inc_id, "system",
                f"1 hour left: {len(critical_open)} critical tasks still open, "
                f"site red: {bool(critical_open)}; {len(residents_open)} residents reminded")
        elif s == 3:
            critical = [t for t in tasks if t["critical"]]
            done = [t for t in critical if t["status"] == "done"]
            pct = round(100 * len(done) / len(critical)) if critical else 100
            updates["lockedScore"] = pct
            updates["lockedAt"] = now_iso()
            log(inc_id, "system", f"Rain window reached. Readiness locked at {pct}%")

    set_fields({"pk": "SITE#demo", "sk": f"INC#{inc_id}"}, updates)


def status_view(inc_id):
    inc = get_incident(inc_id)
    if not inc:
        return respond(404, {"error": "incident not found"})
    tasks = all_tasks(inc_id)
    return respond(200, {
        "incidentId": inc_id,
        "riskLevel": inc["state"],
        "stage": STAGES[int(inc.get("escalationStage", 0))],
        "hoursToWindow": round(clock(inc), 2),
        "siteRed": bool(inc.get("siteRed", False)),
        "escalatedTasks": len([t for t in tasks if t.get("escalated")]),
        "lockedScore": int(inc["lockedScore"]) if "lockedScore" in inc else None,
        "simulatedClockOffsetMin": int(inc.get("timeOffsetMin", 0)),
    })


def time_warp(body):
    inc_id = body.get("incidentId") or latest_incident_id()
    if not inc_id or not get_incident(inc_id):
        return respond(404, {"error": "no incident to warp"})
    minutes = int(body.get("minutes", 60))
    table.update_item(
        Key={"pk": "SITE#demo", "sk": f"INC#{inc_id}"},
        UpdateExpression="ADD timeOffsetMin :m",
        ExpressionAttributeValues={":m": minutes},
    )
    log(inc_id, "demo", f"Time-warp: clock moved forward {minutes} min (SIMULATED)")
    run_escalation(inc_id)
    return status_view(inc_id)

def vehicle_priority(inc_id):
    site = table.get_item(Key={"pk": "SITE#demo", "sk": "PROFILE"}).get("Item", {})
    low = set(site.get("lowLyingBays", []))
    vehicles = table.query(
        KeyConditionExpression=Key("pk").eq("SITE#demo") & Key("sk").begins_with("VEH#")
    )["Items"]
    done_keys = {
        t["vehicleKey"] for t in all_tasks(inc_id)
        if t.get("vehicleKey") and t["status"] == "done"
    }
    rows = []
    for v in vehicles:
        rows.append({
            "vehicleKey": v["sk"], "flat": v["flat"], "plateLast4": v["plateLast4"],
            "level": v["level"], "bay": v["bay"], "moveToSlot": v["moveToSlot"],
            "lowLying": v["bay"] in low,
            "moved": v["sk"] in done_keys,
        })
    rows.sort(key=lambda r: (r["moved"], -int(r["level"][1:]),
                             0 if r["lowLying"] else 1, r["bay"]))
    remaining = len([r for r in rows if not r["moved"]])
    return respond(200, {"vehicles": rows, "remaining": remaining, "total": len(rows)})
# ---------- router ----------

def handler(event, context):
    method = event["requestContext"]["http"]["method"]
    parts = event["rawPath"].strip("/").split("/")
    query = event.get("queryStringParameters") or {}
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": {}, "body": ""}

    if len(parts) > 1 and parts[0] == "incident" and parts[1] == "latest":
        latest = latest_incident_id()
        if not latest:
            return respond(404, {"error": "no incident yet"})
        parts[1] = latest

    if method == "GET" and len(parts) == 2 and parts[0] == "site":
        return get_site(parts[1])

    if method == "POST" and parts == ["incident", "simulate"]:
        return simulate("demo")

    if method == "GET" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "tasks":
        return list_tasks(parts[1], query.get("role"))

    if method == "GET" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "score":
        return readiness(parts[1])

    if method == "GET" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "status":
        return status_view(parts[1])

    if method == "POST" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "escalate":
        run_escalation(parts[1])
        return status_view(parts[1])

    if method == "POST" and len(parts) == 5 and parts[0] == "incident" and parts[2] == "task":
        if parts[4] == "ack":
            return ack_task(parts[1], parts[3], get_body(event))
        if parts[4] == "upload-url":
            return upload_url(parts[1], parts[3], get_body(event))
        if parts[4] == "complete":
            return complete_task(parts[1], parts[3], get_body(event))

    if method == "POST" and parts == ["demo", "time-warp"]:
        return time_warp(get_body(event))
    if method == "GET" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "vehicles":
        return vehicle_priority(parts[1])
    return respond(404, {"error": "route not found"})