import json
import urllib.request
import urllib.error

API = "https://d2go5yhddh.execute-api.ap-south-1.amazonaws.com"


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print("1. Fake evidence name (should be refused):")
print(call("POST", "/incident/latest/task/018/complete",
           {"by": "Ravi", "evidence": "fake-photo.jpg"}))

print("2. Ask for an upload link:")
status, res = call("POST", "/incident/latest/task/018/upload-url",
                   {"contentType": "image/jpeg"})
print(status, res["key"])

print("3. Upload a dummy photo straight to S3:")
put = urllib.request.Request(
    res["uploadUrl"], data=b"pretend this is a pump panel photo",
    method="PUT", headers={"Content-Type": "image/jpeg"},
)
with urllib.request.urlopen(put) as r:
    print(r.status)

print("4. Complete the task with the real key:")
print(call("POST", "/incident/latest/task/018/complete",
           {"by": "Ravi", "evidence": res["key"]}))

print("5. Score:")
print(call("GET", "/incident/latest/score"))