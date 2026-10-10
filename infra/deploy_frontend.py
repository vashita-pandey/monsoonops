import time
import urllib.request
import boto3

amplify = boto3.client("amplify", region_name="ap-south-1")

apps = [a for a in amplify.list_apps()["apps"] if a["name"] == "monsoonops"]
app = apps[0] if apps else amplify.create_app(name="monsoonops")["app"]
app_id = app["appId"]

branches = [b["branchName"] for b in amplify.list_branches(appId=app_id)["branches"]]
if "main" not in branches:
    amplify.create_branch(appId=app_id, branchName="main")

dep = amplify.create_deployment(appId=app_id, branchName="main")
with open("site.zip", "rb") as f:
    req = urllib.request.Request(
        dep["zipUploadUrl"], data=f.read(), method="PUT",
        headers={"Content-Type": "application/zip"},
    )
    urllib.request.urlopen(req)

amplify.start_deployment(appId=app_id, branchName="main", jobId=dep["jobId"])

while True:
    job = amplify.get_job(appId=app_id, branchName="main", jobId=dep["jobId"])
    status = job["job"]["summary"]["status"]
    print("Status:", status)
    if status in ("SUCCEED", "FAILED", "CANCELLED"):
        break
    time.sleep(5)

print("Live at: https://main." + app["defaultDomain"])