import json
import os
import boto3
from datetime import datetime, timezone
from decimal import Decimal
from boto3.dynamodb.conditions import Key
from rules import evaluate
from botocore.exceptions import ClientError

table = boto3.resource("dynamodb").Table(os.environ.get("TABLE_NAME", "MonsoonOps"))

SIMULATED_FORECAST_MM = 90


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


def get_site(site_id):
    item = table.get_item(Key={"pk": f"SITE#{site_id}", "sk": "PROFILE"}).get("Item")
    if not item:
        return respond(404, {"error": "site not found"})
    return respond(200, item)


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
    items = table.query(
        KeyConditionExpression=Key("pk").eq(f"INC#{inc_id}") & Key("sk").begins_with("TASK#")
    )["Items"]
    if role:
        items = [i for i in items if i["role"] == role]
    return respond(200, {"tasks": items})

def get_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except ValueError:
        return {}


def load_task(inc_id, task_id):
    return table.get_item(Key={"pk": f"INC#{inc_id}", "sk": f"TASK#{task_id}"}).get("Item")


def all_tasks(inc_id):
    return table.query(
        KeyConditionExpression=Key("pk").eq(f"INC#{inc_id}") & Key("sk").begins_with("TASK#")
    )["Items"]


def log(inc_id, actor, action):
    table.put_item(Item={
        "pk": f"INC#{inc_id}", "sk": f"LOG#{now_iso()}",
        "actor": actor, "action": action,
    })


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


def complete_task(inc_id, task_id, body):
    task = load_task(inc_id, task_id)
    if not task:
        return respond(404, {"error": "task not found"})
    who = body.get("by", "unknown")
    evidence = (body.get("evidence") or "").strip()
    verified_by = (body.get("verifiedBy") or "").strip()
    need = task["evidence"]

    if need in ("photo", "testlog") and not evidence:
        return respond(400, {"error": f"this task needs {need} evidence"})
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
def handler(event, context):
    method = event["requestContext"]["http"]["method"]
    parts = event["rawPath"].strip("/").split("/")
    query = event.get("queryStringParameters") or {}

    if method == "GET" and len(parts) == 2 and parts[0] == "site":
        return get_site(parts[1])

    if method == "POST" and parts == ["incident", "simulate"]:
        return simulate("demo")

    if method == "GET" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "tasks":
        return list_tasks(parts[1], query.get("role"))

    if method == "GET" and len(parts) == 3 and parts[0] == "incident" and parts[2] == "score":
        return readiness(parts[1])

    if method == "POST" and len(parts) == 5 and parts[0] == "incident" and parts[2] == "task":
        if parts[4] == "ack":
            return ack_task(parts[1], parts[3], get_body(event))
        if parts[4] == "complete":
            return complete_task(parts[1], parts[3], get_body(event))

    return respond(404, {"error": "route not found"})