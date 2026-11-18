import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { ItemRenderer } from "./components/Items.jsx";

const TOKEN_KEY = "setbacks_study_token";

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
function writeToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
}

function Paragraphs({ text, className = "" }) {
  return (
    <div className={`space-y-3 leading-relaxed ${className}`}>
      {(text || "").split(/\n\s*\n/).map((para, i) => {
        const lines = para.split("\n");
        if (lines.every((l) => l.trim().startsWith("- "))) {
          return (
            <ul key={i} className="list-disc space-y-1 pl-5">
              {lines.map((l, j) => <li key={j}>{l.trim().slice(2)}</li>)}
            </ul>
          );
        }
        return <p key={i}>{para}</p>;
      })}
    </div>
  );
}

function ProgressBar({ progress }) {
  if (!progress) return null;
  const pct = Math.round((100 * progress.index) / Math.max(progress.total, 1));
  return (
    <div className="sticky top-0 z-20 border-b border-stone-200 bg-stone-50/95 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-2.5">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-200" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-accent transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
        <span className="w-10 text-right text-xs tabular-nums text-ink-faint">{pct}%</span>
      </div>
    </div>
  );
}

function MessageCard({ label, text, compact = false }) {
  return (
    <article className={`rounded-xl border border-accent/30 bg-white shadow-sm ${compact ? "p-4" : "p-5 sm:p-6"}`}>
      <div className="mb-2 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">{label}</span>
        <span className="text-sm font-semibold text-accent-strong">Message {label}</span>
      </div>
      <p className={`whitespace-pre-line leading-relaxed ${compact ? "text-sm" : "text-[15px] sm:text-base"}`}>{text}</p>
    </article>
  );
}

function missingRequired(items, answers) {
  const errs = {};
  for (const it of items) {
    if (it.required === false) continue;
    const v = answers[it.code];
    const empty = v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0);
    if (empty) errs[it.code] = it.type === "rank" ? "Please rank the messages and tick the box below." : "Please answer this question.";
    else if (it.type === "text" && it.min_chars && v.trim().length < it.min_chars)
      errs[it.code] = `Please write at least ${it.min_chars} characters (you have ${v.trim().length}).`;
  }
  return errs;
}

function ItemsForm({ state, onSubmit, submitting }) {
  const [answers, setAnswers] = useState({});
  const [errors, setErrors] = useState({});
  const items = state.items || [];

  const set = (code, v) => {
    setAnswers((a) => ({ ...a, [code]: v }));
    setErrors((e) => { const n = { ...e }; delete n[code]; return n; });
  };

  const handle = async (e) => {
    e.preventDefault();
    const errs = missingRequired(items, answers);
    setErrors(errs);
    if (Object.keys(errs).length) {
      const first = document.querySelector(`[data-code="${Object.keys(errs)[0]}"]`);
      first && first.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    const payload = {};
    for (const [k, v] of Object.entries(answers)) {
      if (v === null || v === undefined || v === "") continue;
      payload[k] = typeof v === "string" ? v.trim() : v;
    }
    const serverErrors = await onSubmit(payload);
    if (serverErrors) setErrors(serverErrors);
  };

  let lastKind = null;
  let n = 0;
  return (
    <form onSubmit={handle} noValidate>
      {items.map((it) => {
        const header = it.type === "likert" && it.scale_kind && it.scale_kind !== lastKind && state.scale_instructions?.[it.scale_kind];
        if (it.type === "likert") lastKind = it.scale_kind;
        n += 1;
        return (
          <div key={it.code} data-code={it.code}>
            {header ? <p className="mb-1 mt-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">{state.scale_instructions[it.scale_kind]}</p> : null}
            <ItemRenderer item={it} number={state.kind === "consent" ? null : n} value={answers[it.code]}
              onChange={(v) => set(it.code, v)} other={answers[`${it.code}_OTHER`]} onOther={(v) => set(`${it.code}_OTHER`, v)}
              error={errors[it.code]} messages={state.messages || []} />
          </div>
        );
      })}
      {Object.keys(errors).length ? (
        <p className="q-error mt-4" role="alert">Please check the highlighted questions above.</p>
      ) : null}
      <div className="mt-6 flex justify-end">
        <button type="submit" className="btn-primary" disabled={submitting}>{submitting ? "Saving…" : "Continue"}</button>
      </div>
    </form>
  );
}

function Spinner() {
  return <div className="h-10 w-10 animate-spin rounded-full border-4 border-accent-soft border-t-accent" aria-hidden />;
}

export default function Survey() {
  const [token, setToken] = useState(readToken());
  const [state, setState] = useState(null);
  const [fatal, setFatal] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const generating = useRef(false);

  // Boot: resume an existing session or start a new one with ?pid= and ?source=.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const pid = params.get("pid") || params.get("PROLIFIC_PID") || null;
    const source = params.get("source") || null;
    const fresh = params.get("new") === "1";
    (async () => {
      try {
        if (token && !fresh) {
          try {
            setState(await api.state(token));
            return;
          } catch (e) {
            if (e.status !== 404) throw e;
          }
        }
        const res = await api.start(pid, source);
        writeToken(res.token);
        setToken(res.token);
        setState(res.state);
      } catch (e) {
        setFatal(e.message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runGeneration = useCallback(async () => {
    if (generating.current || !token) return;
    generating.current = true;
    setState((s) => ({ ...s, kind: "generate" }));
    try {
      setState(await api.generate(token));
    } catch (e) {
      setState((s) => ({ ...s, kind: "error", body: "Sorry, something went wrong while preparing your messages. Please try again." }));
    } finally {
      generating.current = false;
    }
  }, [token]);

  useEffect(() => {
    if (state && state.kind === "generate") runGeneration();
  }, [state, runGeneration]);

  useEffect(() => { window.scrollTo(0, 0); }, [state?.step]);

  const submit = async (answers) => {
    setSubmitting(true);
    try {
      const next = await api.submit(token, state.step, answers);
      setState(next);
      return null;
    } catch (e) {
      if (e.status === 422) return e.errors;
      if (e.status === 409) { setState(await api.state(token)); return null; }
      setFatal(e.message);
      return null;
    } finally {
      setSubmitting(false);
    }
  };

  if (fatal) {
    return (
      <Shell>
        <div className="card"><h1 className="mb-2 text-lg font-semibold">Something went wrong</h1><p className="text-ink-soft">{fatal}</p>
          <button className="btn-ghost mt-4" onClick={() => window.location.reload()}>Reload</button></div>
      </Shell>
    );
  }
  if (!state) return <Shell><div className="flex justify-center py-24"><Spinner /></div></Shell>;

  const { kind } = state;

  if (kind === "generate") {
    return (
      <Shell progress={state.progress}>
        <div className="card flex flex-col items-center gap-5 py-16 text-center">
          <Spinner />
          <p className="max-w-sm text-ink-soft">{state.body || "Preparing your messages…"}</p>
        </div>
      </Shell>
    );
  }
  if (kind === "error") {
    return (
      <Shell progress={state.progress}>
        <div className="card text-center">
          <h1 className="mb-2 text-lg font-semibold">We couldn't prepare your messages</h1>
          <p className="text-ink-soft">{state.body}</p>
          <button className="btn-primary mt-5" onClick={runGeneration}>Try again</button>
        </div>
      </Shell>
    );
  }
  if (kind === "end" || kind === "support") {
    return (
      <Shell progress={state.progress}>
        <div className="card">
          {state.title ? <h1 className="mb-3 text-xl font-semibold">{state.title}</h1> : null}
          <Paragraphs text={state.body} className="text-ink-soft" />
          {state.support ? (
            <section className="mt-6 rounded-lg border border-accent/30 bg-accent-soft p-4">
              <h2 className="mb-2 font-semibold text-accent-strong">{state.support_title}</h2>
              <Paragraphs text={state.support} className="text-sm text-ink-soft" />
            </section>
          ) : null}
          {state.footer ? <p className="mt-5 text-sm text-ink-faint">{state.footer}</p> : null}
        </div>
      </Shell>
    );
  }

  if (kind === "feedback") {
    return (
      <Shell progress={state.progress}>
        {state.instruction ?<p className="mb-3 text-sm text-ink-soft">{state.instruction}</p> : null}
        <div className="sticky top-[45px] z-10 -mx-1 mb-4 max-h-[42vh] overflow-y-auto px-1 pb-1 sm:max-h-none">
          <MessageCard label={state.label} text={state.message} />
        </div>
        <div className="card"><ItemsForm key={state.step} state={state} onSubmit={submit} submitting={submitting} /></div>
      </Shell>
    );
  }

  if (kind === "compare") {
    return (
      <Shell progress={state.progress} wide>
        {state.instructions ? <p className="mb-3 text-ink-soft">{state.instructions}</p> : null}
        <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {state.messages.map((m) => <MessageCard key={m.label} label={m.label} text={m.text} compact />)}
        </div>
        <div className="card"><ItemsForm key={state.step} state={state} onSubmit={submit} submitting={submitting} /></div>
      </Shell>
    );
  }

  return (
    <Shell progress={state.progress}>
      <div className="card">
        {state.title ? <h1 className="mb-3 text-xl font-semibold">{state.title}</h1> : null}
        {kind === "consent" ? <Paragraphs text={state.body} className="mb-6 text-ink-soft" /> : null}
        {state.instructions ? <p className="mb-4 text-ink-soft">{state.instructions}</p> : null}
        <ItemsForm key={state.step} state={state} onSubmit={submit} submitting={submitting} />
      </div>
    </Shell>
  );
}

function Shell({ children, progress, wide = false }) {
  return (
    <div className="min-h-screen">
      <ProgressBar progress={progress} />
      <main className={`mx-auto px-4 py-6 sm:py-10 ${wide ? "max-w-6xl" : "max-w-3xl"}`}>{children}</main>
    </div>
  );
}
