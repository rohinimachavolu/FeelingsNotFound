import React, { useEffect, useState } from "react";

const PW_KEY = "setbacks_admin_pw";

function authHeader(pw) {
  return { Authorization: "Basic " + btoa("admin:" + pw) };
}

const EXPORTS = [
  { kind: "long", title: "Long format", desc: "One row per participant × condition. P and M items repeated; F items as columns. Ready for mixed-effects models." },
  { kind: "wide", title: "Wide format", desc: "One row per participant. Per-condition columns are prefixed CONDITION__." },
  { kind: "scores", title: "Scale & change scores", desc: "Scale means after reverse-scoring (R) items, plus F − M change scores per item and per appraisal dimension." },
  { kind: "flags", title: "Flags", desc: "Attention check failures, speeders (< 5 min), safety flags, generation errors, length warnings." },
  { kind: "messages", title: "Messages", desc: "Every generated feedback message with condition, label, model, prompt version and word count." },
];

export default function Admin() {
  const [pw, setPw] = useState(() => { try { return sessionStorage.getItem(PW_KEY) || ""; } catch { return ""; } });
  const [input, setInput] = useState("");
  const [summary, setSummary] = useState(null);
  const [flags, setFlags] = useState([]);
  const [error, setError] = useState(null);
  const [source, setSource] = useState("");
  const [completedOnly, setCompletedOnly] = useState(false);

  const load = async (password) => {
    setError(null);
    try {
      const [s, f] = await Promise.all([
        fetch("/api/admin/summary", { headers: authHeader(password) }),
        fetch("/api/admin/flags", { headers: authHeader(password) }),
      ]);
      if (s.status === 401) throw new Error("Wrong password.");
      if (!s.ok) throw new Error((await s.json()).detail || `Error ${s.status}`);
      setSummary(await s.json());
      setFlags(await f.json());
      try { sessionStorage.setItem(PW_KEY, password); } catch { /* ignore */ }
      setPw(password);
    } catch (e) {
      setError(e.message);
      setPw("");
      setSummary(null);
    }
  };

  useEffect(() => { if (pw) load(pw); /* eslint-disable-next-line */ }, []);

  const download = async (kind) => {
    const qs = new URLSearchParams();
    if (source) qs.set("source", source);
    if (completedOnly) qs.set("completed_only", "true");
    const res = await fetch(`/api/admin/export/${kind}.csv?${qs}`, { headers: authHeader(pw) });
    if (!res.ok) { setError(`Export failed (${res.status})`); return; }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().slice(0, 10);
    a.download = `${kind}${source ? "_" + source : ""}${completedOnly ? "_completed" : ""}_${stamp}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (!summary) {
    return (
      <div className="mx-auto max-w-sm px-4 py-24">
        <form className="card" onSubmit={(e) => { e.preventDefault(); load(input); }}>
          <h1 className="mb-4 text-lg font-semibold">Study admin</h1>
          <label className="mb-1 block text-sm text-ink-soft" htmlFor="pw">Password</label>
          <input id="pw" type="password" className="w-full rounded-lg border border-stone-300 px-3 py-2" value={input} onChange={(e) => setInput(e.target.value)} autoFocus />
          {error ? <p className="q-error">{error}</p> : null}
          <button className="btn-primary mt-4 w-full" type="submit">Sign in</button>
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Study admin</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => load(pw)}>Refresh</button>
          <button className="btn-ghost" onClick={() => { try { sessionStorage.removeItem(PW_KEY); } catch { /* ignore */ } setPw(""); setSummary(null); }}>Sign out</button>
        </div>
      </div>
      {error ? <p className="q-error mb-4">{error}</p> : null}

      <section className="mb-6 grid gap-4 md:grid-cols-3">
        {Object.entries(summary.participants).map(([src, counts]) => (
          <div key={src} className="card">
            <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">{src}</h2>
            <dl className="space-y-1 text-sm">
              {Object.entries(counts).map(([status, n]) => (
                <div key={status} className="flex justify-between"><dt>{status}</dt><dd className="font-semibold tabular-nums">{n}</dd></div>
              ))}
            </dl>
          </div>
        ))}
        <div className="card">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">Completed by Latin-square row</h2>
          <dl className="space-y-1 text-sm">
            {Object.entries(summary.completed_by_latin_row).map(([r, n]) => (
              <div key={r} className="flex justify-between"><dt>Row {r}</dt><dd className="font-semibold tabular-nums">{n}</dd></div>
            ))}
          </dl>
        </div>
      </section>

      <section className="card mb-6">
        <h2 className="mb-3 text-lg font-semibold">Exports</h2>
        <div className="mb-4 flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">Source
            <select className="rounded-lg border border-stone-300 px-2 py-1" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All</option><option value="human">Human</option><option value="persona">Persona</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" className="accent-accent" checked={completedOnly} onChange={(e) => setCompletedOnly(e.target.checked)} />
            Completed only
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {EXPORTS.map((x) => (
            <div key={x.kind} className="flex items-start justify-between gap-3 rounded-lg border border-stone-200 p-4">
              <div><div className="font-semibold">{x.title}</div><div className="text-sm text-ink-faint">{x.desc}</div></div>
              <button className="btn-primary shrink-0" onClick={() => download(x.kind)}>CSV</button>
            </div>
          ))}
        </div>
      </section>

      <section className="card mb-6">
        <h2 className="mb-3 text-lg font-semibold">Message length by condition</h2>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-ink-faint"><th className="py-1">Condition</th><th>n</th><th>Mean words</th><th>Min</th><th>Max</th></tr></thead>
          <tbody>
            {Object.entries(summary.word_counts).map(([c, w]) => (
              <tr key={c} className="border-t border-stone-100"><td className="py-1">{c}</td><td>{w.n}</td><td>{w.mean}</td><td>{w.min}</td><td>{w.max}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card mb-6">
        <h2 className="mb-3 text-lg font-semibold">Flags ({flags.length})</h2>
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white"><tr className="text-left text-ink-faint"><th className="py-1">ID</th><th>Source</th><th>PID</th><th>Flag</th><th>Detail</th></tr></thead>
            <tbody>
              {flags.map((f, i) => (
                <tr key={i} className="border-t border-stone-100 align-top">
                  <td className="py-1 pr-2">{f.participant_id}</td><td className="pr-2">{f.source}</td><td className="pr-2">{f.pid}</td>
                  <td className="pr-2 font-medium">{f.flag_type}</td><td className="break-all text-ink-faint">{f.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <DeleteAll pw={pw} onDone={() => load(pw)} />
    </div>
  );
}

function DeleteAll({ pw, onDone }) {
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      const res = await fetch("/api/admin/delete-all", {
        method: "POST",
        headers: { ...authHeader(pw), "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: typed }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
      const d = data.deleted;
      setResult(`Deleted ${d.participants} participants, ${d.responses} responses, ${d.messages} messages, ${d.flags} flags.`);
      setOpen(false);
      setTyped("");
      onDone();
    } catch (e) {
      setResult(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card border-red-200">
      <h2 className="mb-1 text-lg font-semibold text-red-800">Delete all data</h2>
      <p className="mb-4 text-sm text-ink-faint">
        All study data must be deleted when the course ends. This permanently removes every participant (human and persona),
        response, message, flag and timing record. Download any exports you need first. This cannot be undone.
      </p>
      {result ? <p className="mb-3 text-sm font-medium">{result}</p> : null}
      {!open ? (
        <button className="btn border border-red-300 bg-white text-red-700 hover:bg-red-50" onClick={() => setOpen(true)}>Delete all data…</button>
      ) : (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <label htmlFor="confirm-delete" className="mb-2 block text-sm font-medium text-red-900">
            Type <span className="font-mono">DELETE</span> to confirm.
          </label>
          <input id="confirm-delete" className="w-full max-w-xs rounded-lg border border-red-300 px-3 py-2 font-mono" value={typed}
            onChange={(e) => setTyped(e.target.value)} autoFocus autoComplete="off" />
          <div className="mt-3 flex gap-2">
            <button className="btn bg-red-700 text-white hover:bg-red-800" disabled={typed !== "DELETE" || busy} onClick={run}>
              {busy ? "Deleting…" : "Permanently delete everything"}
            </button>
            <button className="btn-ghost" onClick={() => { setOpen(false); setTyped(""); }}>Cancel</button>
          </div>
        </div>
      )}
    </section>
  );
}
