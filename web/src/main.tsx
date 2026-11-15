import {
  StrictMode,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { createRoot } from "react-dom/client";
import ForceGraph2D from "react-force-graph-2d";
import "./style.css";

const AccuracyChart = lazy(() => import("./AccuracyChart"));

type Mode = "trained" | "sandbox";
type Tab = "Ask" | "Graph" | "Proof";
type GNode = {
  id: string;
  type: string;
  label: string;
  state: string;
  x?: number;
  y?: number;
};
type GEdge = {
  id: string;
  source: string;
  target: string;
  type: string;
  wins: number;
  losses: number;
  certified: boolean;
  used?: boolean;
  sql?: string;
  note?: string;
};
type Graph = { nodes: GNode[]; edges: GEdge[] };
type Suggestion = {
  question: string;
  hint?: string;
  followup?: string;
  verified?: boolean;
};
type Database = {
  id: string;
  tables: number | null;
  rules: number | null;
  trained: boolean;
  suggestions: Suggestion[];
};
type Answer = {
  ask_id: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
  error: string | null;
  block: string;
  graph: Graph;
  prompt_tokens: number;
  ms: number;
  proposal: boolean;
};
type Rule = { id: string; term: string; sql: string; note: string };
type Point = {
  checkpoint: number;
  questions_seen: number;
  n: number;
  expected: number;
  complete: boolean;
  accuracy: number | null;
  ci95: number[] | null;
  mean_prompt_tokens: number | null;
  mean_block_chars: number | null;
};
type Summary = {
  run: string;
  model: string;
  effort: string;
  date: string;
  expected_test_count: number;
  systems: Record<string, Point[]>;
  comparisons: Record<string, { points: number; ci95: number[] }>;
  gap_closed: number | null;
  missing: string[];
  complete: boolean;
  per_db: Array<{
    db_id: string;
    n: number;
    floor: number | null;
    ceiling: number | null;
    vector: number | null;
    flat: number | null;
    lore: number | null;
    rules: number;
  }>;
  usage: { input_tokens: number; output_tokens: number; calls: number } | null;
};
type Load = {
  trained: boolean;
  counts: { total: { entities: number; relations: number } };
  levels: Array<{
    concurrency: number;
    p50_ms: number;
    p95_ms: number;
    p99_ms: number;
    requests_per_second: number;
    error_count: number;
  }>;
};
type Proof = { summary: Summary | null; load: Load | null };
const emptyGraph: Graph = { nodes: [], edges: [] };
const palette: Record<string, string> = {
  Term: "#295f4d",
  Column: "#7997ab",
  Table: "#b69a72",
  Example: "#bc7964",
};

async function api<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json().catch(() => null);
  if (!response.ok || data === null)
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : response.ok
          ? "The server sent an invalid response. Please retry."
          : `Request failed (HTTP ${response.status}). Please retry.`,
    );
  return data as T;
}

function Logo() {
  return (
    <svg viewBox="0 0 36 36" width="36" height="36" aria-hidden="true">
      <path
        d="M9 9L27 15L17 28Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <circle cx="9" cy="9" r="4" fill="currentColor" />
      <circle cx="27" cy="15" r="3.5" fill="currentColor" />
      <circle cx="17" cy="28" r="3.5" fill="currentColor" />
    </svg>
  );
}

function GraphView({ graph }: { graph: Graph }) {
  const parent = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(500);
  const [selected, setSelected] = useState<GNode | null>(null);
  const data = useMemo(
    () => ({
      nodes: graph.nodes.map((n) => ({ ...n })),
      links: graph.edges.map((e) => ({ ...e })),
    }),
    [graph],
  );
  useEffect(() => {
    if (!parent.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(180, entries[0].contentRect.width)),
    );
    observer.observe(parent.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    setSelected(null);
  }, [graph]);
  return (
    <div className="graph-wrap" ref={parent}>
      {graph.nodes.length ? (
        <>
          <div
            role="img"
            aria-label="Learned knowledge graph. Dark edges were used to answer. The rules are also available as a table."
          >
            <ForceGraph2D<GNode, GEdge>
              graphData={data}
              width={width}
              height={330}
              backgroundColor="#fbfcf8"
              nodeLabel=""
              cooldownTicks={100}
              nodeRelSize={5}
              linkColor={(link) => (link.used ? "#2c634d" : "#d3dcd5")}
              linkWidth={(link) => (link.used ? 2.5 : 1)}
              linkDirectionalArrowLength={4}
              linkDirectionalArrowRelPos={1}
              onNodeClick={(node) => setSelected(node)}
              nodeCanvasObject={(node, ctx, scale) => {
                const x = node.x ?? 0,
                  y = node.y ?? 0;
                if (node.state === "new" || node.state === "used") {
                  ctx.beginPath();
                  ctx.arc(x, y, 8, 0, 2 * Math.PI);
                  ctx.fillStyle = node.state === "new" ? "#e0edbf" : "#e0eae1";
                  ctx.fill();
                }
                ctx.beginPath();
                ctx.arc(x, y, node.type === "Term" ? 4.5 : 3, 0, 2 * Math.PI);
                ctx.fillStyle = palette[node.type] ?? "#8b9c8c";
                ctx.fill();
                if (node.type === "Term" || selected?.id === node.id) {
                  ctx.font = `${11 / Math.sqrt(scale)}px system-ui`;
                  ctx.fillStyle = "#33483c";
                  ctx.textAlign = "center";
                  ctx.fillText(
                    node.label.slice(0, 42),
                    x,
                    y + 14 / Math.sqrt(scale),
                  );
                }
              }}
            />
          </div>
          {selected && (
            <div className="node-detail">
              <span className="eyebrow">{selected.type}</span>
              <p>{selected.label}</p>
            </div>
          )}
        </>
      ) : (
        <div className="empty graph-empty">
          <Logo />
          <h3>A little knowledge goes a long way.</h3>
          <p>
            Verified feedback will connect business phrases to the columns they
            mean.
          </p>
        </div>
      )}
      <div className="graph-key">
        {["Term", "Column", "Table", "Example"].map((type) => (
          <span key={type}>
            <i style={{ background: palette[type] }} />
            {type}
          </span>
        ))}
      </div>
    </div>
  );
}

const num = (value: number | null | undefined, digits = 1) =>
  value == null
    ? "pending"
    : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const percent = (value: number | null) =>
  value == null ? "pending" : `${num(value)}%`;

function ProofView({ proof }: { proof: Proof }) {
  const s = proof.summary;
  const chart = useMemo(() => {
    if (!s) return [];
    const points = new Map<number, Record<string, number>>();
    const floor = s.systems.floor?.[0];
    if (floor?.complete && floor.accuracy != null)
      points.set(0, { seen: 0, lore: floor.accuracy, vector: floor.accuracy });
    for (const name of ["lore", "vector"])
      for (const point of s.systems[name] ?? []) {
        if (point.complete && point.accuracy != null) {
          points.set(point.questions_seen, {
            ...points.get(point.questions_seen),
            seen: point.questions_seen,
            [name]: point.accuracy,
          });
        }
      }
    return [...points.values()].sort((a, b) => a.seen - b.seen);
  }, [s]);
  if (!s)
    return (
      <section className="panel empty">
        <h2>Proof, not promises.</h2>
        <p>
          The benchmark is still running. Measured results will appear here when
          the report is available.
        </p>
      </section>
    );
  const flat = s.systems.flat?.[0];
  return (
    <div className="proof-stack">
      <section className="panel">
        <div className="panel-top">
          <div>
            <span className="eyebrow">Held-out evaluation</span>
            <h2>Does remembering help?</h2>
          </div>
          <span className={`pill ${s.complete ? "green" : ""}`}>
            {s.complete ? "Complete run" : "Benchmark in progress"}
          </span>
        </div>
        <p className="muted">
          {s.model}, {s.effort || "default"} effort. {s.expected_test_count}{" "}
          held-out questions. A query is correct only when its result matches
          the reference result.
        </p>
        {chart.length ? (
          <div className="chart">
            <Suspense
              fallback={
                <div className="empty">Loading the measured curve…</div>
              }
            >
              <AccuracyChart chart={chart} systems={s.systems} flat={flat} />
            </Suspense>
          </div>
        ) : (
          <div className="empty">
            <p>
              Waiting for the first complete checkpoint. Partial scores are not
              presented as final results.
            </p>
          </div>
        )}
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="System comparison table"
        >
          <table>
            <thead>
              <tr>
                <th>System</th>
                <th>Execution accuracy</th>
                <th>95% interval</th>
                <th>Prompt tokens / question</th>
                <th>Knowledge characters</th>
              </tr>
            </thead>
            <tbody>
              {["floor", "ceiling", "vector", "flat", "lore"].map((name) => {
                const p = s.systems[name]?.at(-1);
                return (
                  <tr key={name}>
                    <th>{name === "lore" ? "Lore" : name}</th>
                    <td>
                      {p?.complete
                        ? percent(p.accuracy)
                        : `${p?.n ?? 0} / ${p?.expected ?? s.expected_test_count} pending`}
                    </td>
                    <td>
                      {p?.complete && p.ci95
                        ? p.ci95.map((v) => `${num(v)}%`).join(" to ")
                        : "pending"}
                    </td>
                    <td>
                      {p?.complete ? num(p.mean_prompt_tokens, 0) : "pending"}
                    </td>
                    <td>
                      {p?.complete ? num(p.mean_block_chars, 0) : "pending"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="footnote">
          Accuracy intervals are Wilson intervals. Final differences below use a
          paired bootstrap. Incomplete checkpoints stay out of the chart.
        </p>
        {Object.entries(s.comparisons).length > 0 && (
          <div className="comparison-row">
            {Object.entries(s.comparisons).map(([key, value]) => (
              <div key={key}>
                <span className="eyebrow">{key.replaceAll("_", " ")}</span>
                <strong>
                  {value.points > 0 ? "+" : ""}
                  {num(value.points)} points
                </strong>
                <small>
                  {value.ci95.map((v) => num(v)).join(" to ")} points, paired
                  interval
                </small>
              </div>
            ))}
          </div>
        )}
      </section>
      <section className="panel">
        <span className="eyebrow">Where it helps, and where it doesn't</span>
        <h2>Every database, no cherry-picking.</h2>
        <div
          className="table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Per-database results table"
        >
          <table>
            <thead>
              <tr>
                <th>Database</th>
                <th>Floor</th>
                <th>Ceiling</th>
                <th>Vector</th>
                <th>Flat</th>
                <th>Lore</th>
                <th>Rules</th>
              </tr>
            </thead>
            <tbody>
              {s.per_db.map((db) => (
                <tr key={db.db_id}>
                  <th>{db.db_id.replaceAll("_", " ")}</th>
                  {(
                    ["floor", "ceiling", "vector", "flat", "lore"] as const
                  ).map((name) => (
                    <td key={name}>{percent(db[name])}</td>
                  ))}
                  <td>{db.rules}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="proof-grid">
        <section className="panel">
          <span className="eyebrow">HydraDB grounding · no LLM</span>
          <h2>The graph under load.</h2>
          {proof.load?.trained ? (
            <>
              <p className="muted">
                {num(proof.load.counts.total.entities, 0)} entities and{" "}
                {num(proof.load.counts.total.relations, 0)} relations. Unfrozen
                readers, every call reads HydraDB.
              </p>
              <div
                className="table-scroll"
                tabIndex={0}
                role="region"
                aria-label="Grounding load results table"
              >
                <table>
                  <thead>
                    <tr>
                      <th>Concurrent</th>
                      <th>p50</th>
                      <th>p95</th>
                      <th>p99</th>
                      <th>req/s</th>
                      <th>Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {proof.load.levels.map((level) => (
                      <tr key={level.concurrency}>
                        <td>{level.concurrency}</td>
                        <td>{num(level.p50_ms)} ms</td>
                        <td>{num(level.p95_ms)} ms</td>
                        <td>{num(level.p99_ms)} ms</td>
                        <td>{num(level.requests_per_second)}</td>
                        <td>{level.error_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="muted">
              The trained-graph load measurement is pending. A schema-only smoke
              test is not a load result.
            </p>
          )}
        </section>
        <section className="panel">
          <span className="eyebrow">Method & limits</span>
          <h2>Same model. Real execution.</h2>
          <p>
            Learning uses only a disjoint stream of questions with verified SQL.
            BIRD hint text is withheld, except in the ceiling. Test questions
            never update the benchmark graph.
          </p>
          <p>
            Vector memory receives the same feedback. Flat retrieval uses Lore's
            learned facts without graph traversal. Results describe this model
            and seed, not every SQL workload.
          </p>
          <p>
            HydraDB stores the graph. SelfGraph supplies retrieval, relation
            history, provenance and decision traces. Native join-path search is
            not in these results.
          </p>
          {s.usage && (
            <p className="footnote">
              Recorded for this run: {num(s.usage.input_tokens, 0)} input
              tokens, {num(s.usage.output_tokens, 0)} output tokens and{" "}
              {num(s.usage.calls, 0)} completed model responses. Identical
              prompts share a disk cache.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

function App() {
  const [tab, setTab] = useState<Tab>("Ask");
  const [dbs, setDbs] = useState<Database[]>([]);
  const [db, setDb] = useState("");
  const [mode, setMode] = useState<Mode>("sandbox");
  const [session] = useState(() => {
    const existing = localStorage.getItem("lore.session");
    if (existing && /^[a-f0-9]{32}$/.test(existing)) return existing;
    const id = crypto.randomUUID().replaceAll("-", "");
    localStorage.setItem("lore.session", id);
    return id;
  });
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [proposal, setProposal] = useState<Answer | null>(null);
  const [graph, setGraph] = useState<Graph>(emptyGraph);
  const [proof, setProof] = useState<Proof>({ summary: null, load: null });
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [hint, setHint] = useState("");
  const [corrected, setCorrected] = useState("");
  const [learned, setLearned] = useState<Rule[] | null>(null);
  const active = dbs.find((d) => d.id === db);
  const scope = { db, mode, session };
  const shown = proposal ?? answer;

  useEffect(() => {
    Promise.all([
      api<{ databases: Database[] }>("/api/dbs"),
      api<Proof>("/api/results"),
    ])
      .then(([data, result]) => {
        setDbs(data.databases);
        setDb(data.databases[0]?.id ?? "");
        setMode(data.databases[0]?.trained ? "trained" : "sandbox");
        setProof(result);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setAnswer(null);
    setProposal(null);
    setGraph(emptyGraph);
    setLearned(null);
    setError("");
    setStatus("");
    setFeedbackOpen(false);
    setHint("");
    setCorrected("");
    if (!db) return;
    let ignore = false;
    api<Graph>("/api/graph?" + new URLSearchParams({ db, mode, session }))
      .then((g) => {
        if (!ignore) setGraph(g);
      })
      .catch((e) => {
        if (!ignore) setError(e.message);
      });
    return () => {
      ignore = true;
    };
  }, [db, mode, session]);
  async function task(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await work();
    } catch (e) {
      setStatus("");
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    void task(async () => {
      setStatus("Walking the graph, then asking the model…");
      setAnswer(null);
      setLearned(null);
      setProposal(null);
      setFeedbackOpen(false);
      const result = await api<Answer>("/api/ask", { ...scope, question });
      setAnswer(result);
      setGraph(result.graph);
      setStatus("");
      setHint("");
      setCorrected("");
    });
  }
  function feedback(verdict: "up" | "down" | "confirm") {
    if (!shown) return;
    void task(async () => {
      setStatus(
        verdict === "down" && hint && !corrected
          ? "Preparing a proposal. Nothing is learned until you confirm."
          : "Saving verified feedback…",
      );
      const result = await api<{
        proposal?: Answer;
        learned?: Rule[];
        graph?: Graph;
        verified?: Pick<Answer, "sql" | "columns" | "rows" | "error">;
      }>("/api/feedback", {
        ask_id: shown.ask_id,
        verdict,
        hint: hint || undefined,
        corrected_sql: corrected || undefined,
        sql: verdict === "confirm" ? shown.sql : undefined,
      });
      if (result.proposal) {
        setProposal(result.proposal);
        setGraph(result.proposal.graph);
        setStatus("Review the proposal below. Confirm only if it is correct.");
      } else {
        setLearned(result.learned ?? []);
        if (result.verified)
          setAnswer({ ...shown, ...result.verified, proposal: false });
        else if (proposal) setAnswer({ ...proposal, proposal: false });
        if (result.graph) setGraph(result.graph);
        setFeedbackOpen(false);
        setProposal(null);
        setStatus("Verified feedback saved to your sandbox.");
      }
    });
  }
  function reset() {
    if (
      !window.confirm(
        "Start a fresh sandbox for this database? The shared trained graph will not change.",
      )
    )
      return;
    void task(async () => {
      await api("/api/sandbox/reset", { db, session });
      setGraph(emptyGraph);
      setAnswer(null);
      setProposal(null);
      setLearned(null);
      setFeedbackOpen(false);
      setStatus("Fresh sandbox. Only the database schema is present.");
    });
  }
  const rules = graph.edges.filter((edge) => edge.type === "MEANS");
  const labels = new Map(graph.nodes.map((node) => [node.id, node.label]));
  return (
    <div className="app">
      <header className="header">
        <a className="brand" href="/" aria-label="Lore home">
          <Logo />
          <span>
            lore<span className="brand-dot">.</span>
          </span>
        </a>
        <span className="header-caption">
          The semantic layer that remembers
        </span>
        <span className="built">
          Built on <b>HydraDB</b> + SelfGraph
        </span>
      </header>
      <section className="intro" aria-label="About Lore">
        <div>
          <span className="eyebrow">
            From corrected queries to shared understanding
          </span>
          <h1>
            Your data has rules.
            <br />
            <em>Now your agent remembers.</em>
          </h1>
        </div>
        <p>
          Lore turns verified feedback into a living graph of business rules.
          For the next question, it brings back just the knowledge that applies.
        </p>
      </section>
      <nav className="tabs" aria-label="Workspace">
        {(["Ask", "Graph", "Proof"] as Tab[]).map((name) => (
          <button
            key={name}
            onClick={() => setTab(name)}
            aria-current={tab === name ? "page" : undefined}
          >
            {name}
            <span>
              {name === "Ask"
                ? "Query & teach"
                : name === "Graph"
                  ? "Inspect memory"
                  : "See the evidence"}
            </span>
          </button>
        ))}
      </nav>
      {error && (
        <div className="alert error" role="alert">
          {error}
        </div>
      )}
      {tab !== "Proof" && (
        <div className="workspace">
          <aside className="sidebar">
            <div className="panel settings">
              <span className="eyebrow">Your workspace</span>
              <label htmlFor="database">Database</label>
              <select
                id="database"
                value={db}
                disabled={busy}
                onChange={(e) => {
                  setDb(e.target.value);
                  if (!dbs.find((d) => d.id === e.target.value)?.trained)
                    setMode("sandbox");
                }}
              >
                {dbs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.id.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
              <p className="db-meta">
                {active?.tables != null
                  ? `${active.tables} tables`
                  : "Public BIRD database"}
                {active?.rules != null
                  ? ` · ${active.rules} trained rules`
                  : ""}
              </p>
              <label>Memory mode</label>
              <div className="mode-switch">
                {(["trained", "sandbox"] as Mode[]).map((m) => (
                  <button
                    key={m}
                    disabled={busy || (m === "trained" && !active?.trained)}
                    className={mode === m ? "active" : ""}
                    onClick={() => setMode(m)}
                  >
                    {m === "trained" ? "Trained" : "Sandbox"}
                  </button>
                ))}
              </div>
              <p className="muted small">
                {mode === "trained"
                  ? "Explore learned knowledge from the benchmark. Shared facts stay read-only."
                  : "Your private graph starts with the schema. Teach it with a hint or corrected SQL."}
              </p>
              {mode === "sandbox" && (
                <button
                  className="text-button"
                  onClick={reset}
                  disabled={busy || !db}
                >
                  Start a fresh sandbox <span aria-hidden="true">↗</span>
                </button>
              )}
            </div>
            <div className="starters">
              <span className="eyebrow">A place to start</span>
              {active?.suggestions.length ? (
                active.suggestions.map((s, i) => (
                  <button
                    key={i}
                    disabled={busy}
                    onClick={() => {
                      setTab("Ask");
                      setQuestion(s.question);
                      if (s.hint) setHint(s.hint);
                    }}
                  >
                    <span>{s.question}</span>
                    {s.followup ? (
                      <small>Teach this, then try: {s.followup}</small>
                    ) : (
                      <small>
                        Ask, inspect the answer, then give verified feedback.
                      </small>
                    )}
                  </button>
                ))
              ) : (
                <p className="muted small">
                  Try a question about this database. If the answer misses a
                  business rule, switch to a sandbox and supply the correction.
                  Suggested examples are pending verified replay.
                </p>
              )}
            </div>
            <div className="loop-note">
              <span className="eyebrow">A useful feedback loop</span>
              <p>
                Ask a question.
                <br />
                Verify the answer.
                <br />
                Teach the missing rule.
                <br />
                <strong>Let the next query benefit.</strong>
              </p>
            </div>
          </aside>
          <main className="main-column">
            {tab === "Ask" ? (
              <>
                <section className="panel composer">
                  <div className="panel-top">
                    <span className="eyebrow">Ask in plain language</span>
                    <span className="pill">
                      <span className="dot" />
                      {mode === "trained"
                        ? "Trained memory"
                        : "Private sandbox"}
                    </span>
                  </div>
                  <form onSubmit={ask}>
                    <label className="sr-only" htmlFor="question">
                      Your question
                    </label>
                    <textarea
                      id="question"
                      maxLength={4000}
                      rows={3}
                      placeholder="What would you like to know about this data?"
                      value={question}
                      onChange={(e) => setQuestion(e.target.value)}
                      disabled={busy}
                    />
                    <div className="composer-bottom">
                      <span>
                        SQL is run read-only against the real database.
                      </span>
                      <button
                        className="primary"
                        type="submit"
                        disabled={busy || !db || !question.trim()}
                      >
                        {busy ? "Working…" : "Ask Lore"}
                        <span aria-hidden="true">↗</span>
                      </button>
                    </div>
                  </form>
                </section>
                {status && (
                  <div
                    className={`alert ${busy ? "working" : "success"}`}
                    role="status"
                  >
                    {busy && <span className="spinner" />}
                    {status}
                  </div>
                )}
                {learned && (
                  <section className="learned">
                    <span className="eyebrow">Added to your memory</span>
                    {learned.length ? (
                      learned.map((rule) => (
                        <div key={rule.id}>
                          <strong>{rule.term}</strong>
                          <code>{rule.sql}</code>
                          <p>{rule.note}</p>
                        </div>
                      ))
                    ) : (
                      <p>Saved the verified query. No new rule was added.</p>
                    )}
                  </section>
                )}
                {shown ? (
                  <section className="panel answer">
                    <div className="panel-top">
                      <h2>
                        {proposal
                          ? "A proposal, not a new fact."
                          : "The answer, with its working."}
                      </h2>
                      <span className="muted small">
                        {num(shown.ms / 1000)} s · {num(shown.prompt_tokens, 0)}{" "}
                        prompt tokens
                      </span>
                    </div>
                    {shown.error ? (
                      <div className="alert error">{shown.error}</div>
                    ) : (
                      <div
                        className="result-table table-scroll"
                        tabIndex={0}
                        role="region"
                        aria-label="Query results table"
                      >
                        <table>
                          <thead>
                            <tr>
                              {shown.columns.map((column, i) => (
                                <th key={i}>{column}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {shown.rows.map((row, i) => (
                              <tr key={i}>
                                {row.map((cell, j) => (
                                  <td key={j}>
                                    {cell == null ? (
                                      <span className="null">NULL</span>
                                    ) : typeof cell === "object" ? (
                                      JSON.stringify(cell)
                                    ) : (
                                      String(cell)
                                    )}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {!shown.rows.length && (
                          <p className="muted">The query returned no rows.</p>
                        )}
                      </div>
                    )}
                    <details open>
                      <summary>Generated SQL</summary>
                      <pre>
                        <code>{shown.sql || "No SQL was returned."}</code>
                      </pre>
                    </details>
                    {mode === "sandbox" && learned === null ? (
                      <div className="feedback">
                        {proposal ? (
                          <>
                            <p>
                              Check the SQL and the result before teaching Lore.
                            </p>
                            <button
                              className="primary"
                              disabled={busy || !!shown.error}
                              onClick={() => feedback("confirm")}
                            >
                              Confirm this SQL
                            </button>
                            <button
                              className="secondary"
                              disabled={busy}
                              onClick={() => {
                                setProposal(null);
                                setStatus("");
                              }}
                            >
                              Discard proposal
                            </button>
                          </>
                        ) : (
                          <>
                            <span>Does this answer look right?</span>
                            <button
                              className="secondary"
                              disabled={busy || !!shown.error}
                              onClick={() => feedback("up")}
                            >
                              Yes, verify it
                            </button>
                            <button
                              className="secondary"
                              disabled={busy}
                              onClick={() => setFeedbackOpen(!feedbackOpen)}
                            >
                              Needs a correction
                            </button>
                          </>
                        )}
                        {feedbackOpen && !proposal && (
                          <div className="correction">
                            <label htmlFor="hint">Teach the missing rule</label>
                            <textarea
                              id="hint"
                              value={hint}
                              maxLength={2000}
                              rows={2}
                              placeholder="For example: revenue excludes cancelled orders…"
                              onChange={(e) => setHint(e.target.value)}
                            />
                            <label htmlFor="corrected">
                              Or supply verified SQL
                            </label>
                            <textarea
                              id="corrected"
                              className="code-input"
                              maxLength={20000}
                              value={corrected}
                              rows={3}
                              placeholder="SELECT …"
                              onChange={(e) => setCorrected(e.target.value)}
                            />
                            <button
                              className="primary"
                              disabled={
                                busy || (!hint.trim() && !corrected.trim())
                              }
                              onClick={() => feedback("down")}
                            >
                              {corrected.trim()
                                ? "Learn from this SQL"
                                : "Propose a correction"}
                            </button>
                            <small>
                              A hint produces a proposal. Nothing from that
                              proposal is learned until you confirm it.
                            </small>
                          </div>
                        )}
                      </div>
                    ) : (
                      <p className="footnote">
                        {mode === "sandbox"
                          ? "Verified feedback saved. Ask another question to use this memory."
                          : "The shared trained graph is read-only. Switch to a sandbox to give feedback."}
                      </p>
                    )}
                  </section>
                ) : (
                  !busy && (
                    <section className="panel empty welcome">
                      <span className="eyebrow">
                        Not just SQL. Understanding.
                      </span>
                      <h2>
                        The rules usually live
                        <br />
                        in someone's head.
                      </h2>
                      <p>
                        Ask your first question. A correction becomes a small,
                        inspectable fact, not another prompt someone has to
                        maintain.
                      </p>
                    </section>
                  )
                )}
                <div className="context-grid">
                  <section className="panel compact">
                    <div className="panel-top">
                      <h2>The graph behind the answer</h2>
                      <button
                        className="text-button"
                        onClick={() => setTab("Graph")}
                      >
                        Inspect ↗
                      </button>
                    </div>
                    <GraphView graph={graph} />
                  </section>
                  <section className="panel compact">
                    <span className="eyebrow">
                      Exactly what the model received
                    </span>
                    <h2>The knowledge block</h2>
                    <p className="muted small">
                      Only rules, values, joins and verified examples selected
                      for this question.
                    </p>
                    {shown?.block ? (
                      <pre className="knowledge">{shown.block}</pre>
                    ) : (
                      <div className="empty context-empty">
                        <p>
                          No learned context was added. With an empty memory,
                          Lore uses the same prompt as the floor baseline.
                        </p>
                      </div>
                    )}
                  </section>
                </div>
              </>
            ) : (
              <>
                <section className="panel">
                  <div className="panel-top">
                    <div>
                      <span className="eyebrow">A memory you can inspect</span>
                      <h2>Business meaning, connected.</h2>
                    </div>
                    <span className="pill">
                      {mode === "trained"
                        ? "Shared · read-only"
                        : "Your sandbox"}
                    </span>
                  </div>
                  <GraphView graph={graph} />
                </section>
                <section className="panel">
                  <span className="eyebrow">Rule ledger</span>
                  <h2>Small facts. Clear provenance.</h2>
                  {rules.length ? (
                    <div
                      className="table-scroll"
                      tabIndex={0}
                      role="region"
                      aria-label="Learned rules table"
                    >
                      <table>
                        <thead>
                          <tr>
                            <th>Term</th>
                            <th>SQL meaning</th>
                            <th>Wins</th>
                            <th>Losses</th>
                            <th>Trust</th>
                          </tr>
                        </thead>
                        <tbody>
                          {rules.map((rule) => (
                            <tr key={rule.id}>
                              <th>{labels.get(rule.source) ?? rule.source}</th>
                              <td>
                                <code>{rule.sql}</code>
                                <small className="rule-note">{rule.note}</small>
                              </td>
                              <td>{rule.wins}</td>
                              <td>{rule.losses}</td>
                              <td>
                                {rule.certified ? (
                                  <span className="pill green">Certified</span>
                                ) : mode === "sandbox" ? (
                                  <button
                                    className="secondary"
                                    disabled={busy}
                                    onClick={() =>
                                      void task(async () => {
                                        setGraph(
                                          await api<Graph>("/api/certify", {
                                            ...scope,
                                            relation_id: rule.id,
                                          }),
                                        );
                                        setStatus("Rule certified.");
                                      })
                                    }
                                  >
                                    Certify
                                  </button>
                                ) : (
                                  "Uncertified"
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="muted">
                      No rules yet. Verify a query or correct an answer in a
                      sandbox to build this graph.
                    </p>
                  )}
                </section>
              </>
            )}
          </main>
        </div>
      )}
      {tab === "Proof" && (
        <main aria-label="Benchmark results">
          <ProofView proof={proof} />
        </main>
      )}
      <footer>
        <span>
          lore. <span className="muted">Make every correction count.</span>
        </span>
        <span>Open-source HydraDB · SelfGraph · BIRD</span>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
