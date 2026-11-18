import React, { useRef, useState } from "react";

function Question({ item, error, children, number }) {
  return (
    <fieldset className="py-5 first:pt-0 border-b border-stone-100 last:border-b-0" aria-invalid={!!error}>
      <legend className="q-text">
        {number ? <span className="mr-1 text-ink-faint">{number}.</span> : null}
        {item.text}
        {item.required === false ? <span className="ml-1 text-sm font-normal text-ink-faint">(optional)</span> : null}
      </legend>
      {item.help ? <p className="q-help">{item.help.charAt(0).toUpperCase() + item.help.slice(1)}</p> : null}
      <div className="mt-3">{children}</div>
      {error ? <p className="q-error" role="alert">{error}</p> : null}
    </fieldset>
  );
}

export function Likert({ item, value, onChange, error, number }) {
  const points = [];
  for (let i = item.min; i <= item.max; i++) points.push(i);
  const anchors = item.anchors || {};
  const fullLabels = Object.keys(anchors).length === points.length;
  return (
    <Question item={item} error={error} number={number}>
      {/* Mobile: vertical list */}
      <div className="flex flex-col gap-1.5 sm:hidden">
        {points.map((p) => (
          <label key={p}
            className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm ${value === p ? "border-accent bg-accent-soft" : "border-stone-200 bg-white"}`}>
            <input type="radio" name={item.code} className="accent-accent" checked={value === p} onChange={() => onChange(p)} />
            <span className="w-4 font-semibold">{p}</span>
            <span className="text-ink-soft">{anchors[p] || ""}</span>
          </label>
        ))}
      </div>
      {/* Desktop: horizontal scale */}
      <div className="hidden sm:block">
        <div className="grid gap-1.5" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
          {points.map((p) => (
            <button type="button" key={p} onClick={() => onChange(p)} aria-pressed={value === p}
              aria-label={`${p}${anchors[p] ? ` – ${anchors[p]}` : ""}`}
              className={`flex flex-col items-center rounded-lg border px-1 py-2 text-sm transition ${value === p ? "border-accent bg-accent text-white" : "border-stone-200 bg-white hover:border-accent hover:bg-accent-soft"}`}>
              <span className="font-semibold">{p}</span>
              {fullLabels ? <span className={`mt-1 text-[11px] leading-tight ${value === p ? "text-white" : "text-ink-faint"}`}>{anchors[p]}</span> : null}
            </button>
          ))}
        </div>
        {!fullLabels ? (
          <div className="mt-1.5 flex justify-between text-xs text-ink-faint">
            <span>{anchors[item.min] || ""}</span>
            <span>{anchors[item.max] || ""}</span>
          </div>
        ) : null}
      </div>
    </Question>
  );
}

function optionLabel(item, o) {
  if (item.message_choice && o.value !== "None") return `Message ${o.label}`;
  return o.label;
}

export function SingleChoice({ item, value, onChange, other, onOther, error, number }) {
  return (
    <Question item={item} error={error} number={number}>
      <div className={item.message_choice ? "grid grid-cols-2 gap-2 sm:grid-cols-5" : "flex flex-col gap-1.5"}>
        {item.options.map((o) => (
          <div key={o.value}>
            <label className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm ${value === o.value ? "border-accent bg-accent-soft" : "border-stone-200 bg-white hover:bg-stone-50"}`}>
              <input type="radio" name={item.code} className="accent-accent" checked={value === o.value} onChange={() => onChange(o.value)} />
              <span>{optionLabel(item, o)}</span>
            </label>
            {o.text_entry && value === o.value ? (
              <input type="text" className="mt-1.5 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm" placeholder="Please describe"
                value={other || ""} onChange={(e) => onOther(e.target.value)} maxLength={200} />
            ) : null}
          </div>
        ))}
      </div>
    </Question>
  );
}

export function MultiChoice({ item, value, onChange, other, onOther, error, number }) {
  const selected = value || [];
  const toggle = (v) => onChange(selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]);
  return (
    <Question item={item} error={error} number={number}>
      <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {item.options.map((o) => (
          <div key={o.value}>
            <label className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 text-sm ${selected.includes(o.value) ? "border-accent bg-accent-soft" : "border-stone-200 bg-white hover:bg-stone-50"}`}>
              <input type="checkbox" className="accent-accent" checked={selected.includes(o.value)} onChange={() => toggle(o.value)} />
              <span>{o.label}</span>
            </label>
            {o.text_entry && selected.includes(o.value) ? (
              <input type="text" className="mt-1.5 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm" placeholder="Please describe"
                value={other || ""} onChange={(e) => onOther(e.target.value)} maxLength={200} />
            ) : null}
          </div>
        ))}
      </div>
    </Question>
  );
}

export function TextItem({ item, value, onChange, error, number }) {
  const len = (value || "").trim().length;
  const min = item.min_chars || 0;
  return (
    <Question item={item} error={error} number={number}>
      <textarea className="min-h-[9rem] w-full rounded-lg border border-stone-300 px-3 py-2 text-[15px] leading-relaxed focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        value={value || ""} onChange={(e) => onChange(e.target.value)} maxLength={5000} />
      {min ? (
        <p className={`mt-1 text-xs ${len >= min ? "text-accent" : "text-ink-faint"}`}>
          {len} / {min} characters minimum
        </p>
      ) : null}
    </Question>
  );
}

export function ShortText({ item, value, onChange, error, number }) {
  return (
    <Question item={item} error={error} number={number}>
      <input type="text" className="w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
        value={value || ""} onChange={(e) => onChange(e.target.value)} maxLength={200} />
    </Question>
  );
}

export function Slider({ item, value, onChange, error, number }) {
  const touched = value !== undefined && value !== null;
  return (
    <Question item={item} error={error} number={number}>
      <div className="flex items-center gap-4">
        <input type="range" min={item.min} max={item.max} step={1} value={touched ? value : Math.round((item.min + item.max) / 2)}
          onChange={(e) => onChange(parseInt(e.target.value, 10))} onClick={(e) => onChange(parseInt(e.currentTarget.value, 10))}
          className={`w-full ${touched ? "accent-accent" : "opacity-60"}`} aria-valuetext={touched ? `${value}${item.unit || ""}` : "not answered"} />
        <span className="w-14 text-right font-semibold tabular-nums">{touched ? `${value}${item.unit || ""}` : "–"}</span>
      </div>
      <div className="mt-1 flex justify-between text-xs text-ink-faint">
        <span>{item.min}{item.unit}</span>
        <span>{item.max}{item.unit}</span>
      </div>
      {!touched ? <p className="mt-1 text-xs text-ink-faint">Click or drag the slider to answer.</p> : null}
    </Question>
  );
}

/** Drag-to-rank (with up/down buttons for keyboard and touch users). Value: {label: rank}. */
export function RankList({ item, messages, value, onChange, error, number }) {
  const initial = value
    ? Object.entries(value).sort((a, b) => a[1] - b[1]).map(([l]) => l)
    : messages.map((m) => m.label);
  const [order, setOrder] = useState(initial);
  const [confirmed, setConfirmed] = useState(!!value);
  const dragFrom = useRef(null);
  const emit = (o, conf) => onChange(conf ? Object.fromEntries(o.map((l, i) => [l, i + 1])) : null);
  const move = (from, to) => {
    if (to < 0 || to >= order.length || from === to) return;
    const o = [...order];
    const [x] = o.splice(from, 1);
    o.splice(to, 0, x);
    setOrder(o);
    emit(o, confirmed);
  };
  const preview = (label) => {
    const t = (messages.find((m) => m.label === label) || {}).text || "";
    return t.length > 90 ? `${t.slice(0, 90)}…` : t;
  };
  return (
    <Question item={item} error={error} number={number}>
      <p className="mb-2 text-xs text-ink-faint">Top = most likely to keep you going. Drag a message, or use the arrows.</p>
      <ol className="flex flex-col gap-2">
        {order.map((label, i) => (
          <li key={label} draggable
            onDragStart={() => (dragFrom.current = i)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => { move(dragFrom.current, i); dragFrom.current = null; }}
            className="flex cursor-grab items-center gap-3 rounded-lg border border-stone-200 bg-white px-3 py-2 active:cursor-grabbing">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-bold text-white">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">Message {label}</div>
              <div className="truncate text-xs text-ink-faint">{preview(label)}</div>
            </div>
            <div className="flex shrink-0 flex-col">
              <button type="button" className="px-2 text-ink-soft hover:text-accent disabled:opacity-30" disabled={i === 0}
                onClick={() => move(i, i - 1)} aria-label={`Move message ${label} up`}>▲</button>
              <button type="button" className="px-2 text-ink-soft hover:text-accent disabled:opacity-30" disabled={i === order.length - 1}
                onClick={() => move(i, i + 1)} aria-label={`Move message ${label} down`}>▼</button>
            </div>
          </li>
        ))}
      </ol>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" className="accent-accent" checked={confirmed}
          onChange={(e) => { setConfirmed(e.target.checked); emit(order, e.target.checked); }} />
        This ranking reflects my view.
      </label>
    </Question>
  );
}

export function ItemRenderer(props) {
  const { item } = props;
  switch (item.type) {
    case "likert": return <Likert {...props} />;
    case "single": return <SingleChoice {...props} />;
    case "multi": return <MultiChoice {...props} />;
    case "text": return <TextItem {...props} />;
    case "short_text": return <ShortText {...props} />;
    case "slider": return <Slider {...props} />;
    case "rank": return <RankList {...props} />;
    default: return <p className="text-red-700">Unsupported item type: {item.type}</p>;
  }
}
