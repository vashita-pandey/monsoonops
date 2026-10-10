const API = "https://d2go5yhddh.execute-api.ap-south-1.amazonaws.com";

async function call(method, path, body) {
  const res = await fetch(API + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

export const getSite = () => call("GET", "/site/demo");
export const getStatus = () => call("GET", "/incident/latest/status");
export const getScore = () => call("GET", "/incident/latest/score");
export const getTasks = (role) =>
  call("GET", "/incident/latest/tasks" + (role ? `?role=${role}` : ""));
export const simulate = () => call("POST", "/incident/simulate");
export const timeWarp = (minutes) => call("POST", "/demo/time-warp", { minutes });

export const ackTask = (taskId, by) =>
  call("POST", `/incident/latest/task/${taskId}/ack`, { by });

export const completeTask = (taskId, body) =>
  call("POST", `/incident/latest/task/${taskId}/complete`, body);

export async function uploadEvidence(taskId, blob, contentType) {
  const { uploadUrl, key } = await call(
    "POST",
    `/incident/latest/task/${taskId}/upload-url`,
    { contentType }
  );
  const res = await fetch(uploadUrl, {
    method: "PUT",
    headers: { "Content-Type": contentType },
    body: blob,
  });
  if (!res.ok) throw new Error("Upload failed. Please try again.");
  return key;
}