async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = new Error((data && data.detail) || `Request failed (${res.status})`);
    err.status = res.status;
    err.errors = (data && data.errors) || {};
    throw err;
  }
  return data;
}

export const api = {
  start: (pid, source) => request("/api/start", { method: "POST", body: JSON.stringify({ pid, source }) }),
  state: (token) => request(`/api/session/${token}`),
  submit: (token, step, answers) =>
    request(`/api/session/${token}/submit`, { method: "POST", body: JSON.stringify({ step, answers }) }),
  generate: (token) => request(`/api/session/${token}/generate`, { method: "POST" }),
};
