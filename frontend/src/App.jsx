import { useState, useEffect } from "react";
import "./App.css";

// ─── Config ───────────────────────────────────────────────
// Change this to your Render URL after deploy
const API_BASE = process.env.REACT_APP_API_URL || "http://localhost:8000";

// ─── Helper ───────────────────────────────────────────────
function ConfBar({ value }) {
  const color = value >= 0.85 ? "#10b981" : value >= 0.65 ? "#f59e0b" : "#ef4444";
  return (
    <div className="conf-bar">
      <span>confidence</span>
      <div className="conf-track">
        <div className="conf-fill" style={{ width: `${Math.round(value * 100)}%`, background: color }} />
      </div>
      <span style={{ color, fontWeight: 500 }}>{value.toFixed(2)}</span>
    </div>
  );
}

function AgentBadge({ name }) {
  const cls = { logic: "agent-logic", security: "agent-security", style: "agent-style", test: "agent-test" };
  return <span className={`agent-badge ${cls[name] || ""}`}>{name.toUpperCase()}</span>;
}

function StatusBadge({ status }) {
  const map = {
    auto_posted: ["badge-success", "auto posted"],
    approved: ["badge-success", "approved"],
    held_for_human: ["badge-warning", "held for human"],
    rejected: ["badge-muted", "rejected"],
    pending: ["badge-muted", "pending"],
  };
  const [cls, label] = map[status] || ["badge-muted", status];
  return <span className={`badge ${cls}`}>{label}</span>;
}

// ─── Pipeline Step ─────────────────────────────────────────
const PIPELINE_STEPS = [
  { label: "GitHub\nfetch", icon: "⬇️" },
  { label: "Retrieval\nagent", icon: "🔍" },
  { label: "Logic\nagent", icon: "🧠" },
  { label: "Security\nagent", icon: "🔒" },
  { label: "Style\nagent", icon: "✨" },
  { label: "Test\nagent", icon: "🧪" },
  { label: "Confidence\nscorer", icon: "📊" },
  { label: "HITL\ngate", icon: "👤" },
  { label: "GitHub\npost", icon: "✅" },
];

function PipelineView({ stepIndex, done }) {
  return (
    <div className="pipeline">
      {PIPELINE_STEPS.map((s, i) => {
        const state = done ? "done" : i < stepIndex ? "done" : i === stepIndex ? "running" : "pending";
        return (
          <div key={i} className="pipe-wrap">
            <div className={`pipe-step ${state}`}>
              <div className="pipe-icon">{state === "done" ? "✓" : state === "running" ? "⟳" : s.icon}</div>
              <div className="pipe-label">{s.label}</div>
            </div>
            {i < PIPELINE_STEPS.length - 1 && <div className="pipe-arrow">›</div>}
          </div>
        );
      })}
    </div>
  );
}

// ─── Comment Card ──────────────────────────────────────────
function CommentCard({ comment, onDecide }) {
  return (
    <div className="comment-card">
      <div className="comment-header">
        <AgentBadge name={comment.agent_name} />
        <span className="file-path">{comment.file_path}</span>
        <StatusBadge status={comment.status} />
      </div>
      <div className="comment-body">{comment.comment}</div>
      <div className="comment-meta">
        <ConfBar value={comment.confidence_score} />
        <span>{comment.failure_type}</span>
      </div>
      {comment.status === "held_for_human" && onDecide && (
        <div className="comment-actions">
          <button className="btn btn-sm btn-success" onClick={() => onDecide(comment.id, "approved")}>
            ✓ Approve
          </button>
          <button className="btn btn-sm btn-danger" onClick={() => onDecide(comment.id, "rejected")}>
            ✗ Reject
          </button>
        </div>
      )}
    </div>
  );
}

// ─── PR Review Tab ─────────────────────────────────────────
function PRReviewTab() {
  const [repo, setRepo] = useState("Saksham-Arora18/hello");
  const [prNum, setPrNum] = useState("1");
  const [running, setRunning] = useState(false);
  const [stepIdx, setStepIdx] = useState(-1);
  const [done, setDone] = useState(false);
  const [logs, setLogs] = useState([]);
  const [comments, setComments] = useState([]);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  function addLog(cls, msg) {
    setLogs((prev) => [...prev, { cls, msg, id: Date.now() + Math.random() }]);
  }

  async function runReview() {
    if (!repo || !prNum) { setError("Enter repo name and PR number"); return; }
    setError("");
    setRunning(true);
    setDone(false);
    setStepIdx(0);
    setLogs([]);
    setComments([]);
    setStats(null);

    try {
      // Step 0 — fetch metadata
      addLog("log-info", `Fetching PR #${prNum} from ${repo}...`);
      const metaRes = await fetch(`${API_BASE}/api/pr-metadata?repo=${encodeURIComponent(repo)}&pr_number=${prNum}`);
      if (!metaRes.ok) throw new Error("Could not fetch PR metadata");
      const meta = await metaRes.json();
      addLog("log-success", `PR: "${meta.title}" · ${meta.files_changed} file(s) changed`);
      setStepIdx(1);

      // Step 1–8 — run full pipeline
      addLog("log-info", "Starting review pipeline...");
      const reviewRes = await fetch(`${API_BASE}/api/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, pr_number: parseInt(prNum) }),
      });
      if (!reviewRes.ok) throw new Error("Pipeline failed");
      const result = await reviewRes.json();

      // Animate steps
      for (let i = 2; i < PIPELINE_STEPS.length; i++) {
        await new Promise((r) => setTimeout(r, 400));
        setStepIdx(i);
        addLog("log-success", `[${PIPELINE_STEPS[i].label.replace("\n", " ")}] complete`);
      }

      setComments(result.comments || []);
      setStats(result.stats || null);
      addLog("log-success", `Done — ${result.stats?.auto_posted || 0} auto posted, ${result.stats?.held || 0} held for human`);
      setDone(true);
    } catch (err) {
      addLog("log-warn", `Error: ${err.message}`);
      // Demo mode — show mock data if backend not connected
      simulateDemo();
    } finally {
      setRunning(false);
    }
  }

  async function simulateDemo() {
    const mockComments = [
      { id: 1, agent_name: "security", file_path: "utils/helpers.py", confidence_score: 0.99, failure_type: "engineering", status: "auto_posted", comment: "Direct string interpolation in SQL query — SQL injection vulnerability. Use parameterized queries instead." },
      { id: 2, agent_name: "security", file_path: "auth/login.py", confidence_score: 0.97, failure_type: "engineering", status: "auto_posted", comment: "MD5 is cryptographically broken for password hashing. Replace with bcrypt.hashpw()." },
      { id: 3, agent_name: "logic", file_path: "auth/login.py", confidence_score: 0.60, failure_type: "engineering", status: "held_for_human", comment: "db.find() can return None if user doesn't exist, but user.password is accessed without a null check." },
      { id: 4, agent_name: "test", file_path: "auth/login.py", confidence_score: 0.88, failure_type: "engineering", status: "auto_posted", comment: "login() function has no corresponding test cases. Critical paths untested." },
      { id: 5, agent_name: "style", file_path: "auth/login.py", confidence_score: 0.75, failure_type: "llm_uncertain", status: "held_for_human", comment: "login() function is missing a docstring — return values and exceptions are undocumented." },
    ];
    for (let i = 2; i < PIPELINE_STEPS.length; i++) {
      await new Promise((r) => setTimeout(r, 350));
      setStepIdx(i);
      addLog("log-success", `[${PIPELINE_STEPS[i].label.replace("\n", " ")}] complete`);
    }
    setComments(mockComments);
    setStats({ total: 5, auto_posted: 3, held: 2, rejected: 0 });
    addLog("log-info", "Demo mode — backend not connected, showing mock data");
    setDone(true);
  }

  async function handleDecide(commentId, decision) {
    try {
      await fetch(`${API_BASE}/api/comments/${commentId}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });
    } catch {}
    setComments((prev) => prev.map((c) => c.id === commentId ? { ...c, status: decision } : c));
  }

  return (
    <div>
      <div className="topbar">
        <h1>PR Review Agent</h1>
        <span className="badge badge-success">● Live</span>
      </div>

      {stats && (
        <div className="cards-grid">
          {[
            { label: "Total issues", value: stats.total },
            { label: "Auto posted", value: stats.auto_posted },
            { label: "Held for human", value: stats.held },
            { label: "Rejected", value: stats.rejected ?? 0 },
          ].map((m) => (
            <div key={m.label} className="metric">
              <div className="metric-label">{m.label}</div>
              <div className="metric-value">{m.value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="section">
        <div className="section-title">Trigger review</div>
        <div className="trigger-form">
          <div className="form-group" style={{ flex: 2 }}>
            <label>GitHub repo</label>
            <input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/repository" />
          </div>
          <div className="form-group" style={{ width: 90 }}>
            <label>PR number</label>
            <input type="number" value={prNum} onChange={(e) => setPrNum(e.target.value)} placeholder="1" />
          </div>
          <button className="btn btn-primary" onClick={runReview} disabled={running}>
            {running ? "Running..." : "▶ Run review"}
          </button>
        </div>
        {error && <div className="error-msg">{error}</div>}
      </div>

      {(running || done) && (
        <div className="section">
          <div className="section-header">
            <div className="section-title">Pipeline status</div>
            <span className={`badge ${done ? "badge-success" : "badge-accent"}`}>
              {done ? "Complete" : "Running"}
            </span>
          </div>
          <PipelineView stepIndex={stepIdx} done={done} />
          {logs.length > 0 && (
            <div className="log-area">
              {logs.map((l) => (
                <div key={l.id} className={`log-line ${l.cls}`}>{l.msg}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {comments.length > 0 && (
        <div className="section">
          <div className="section-header">
            <div className="section-title">Review comments</div>
            <span className="badge badge-muted">{comments.length} comment{comments.length !== 1 ? "s" : ""}</span>
          </div>
          {comments.map((c) => (
            <CommentCard key={c.id} comment={c} onDecide={handleDecide} />
          ))}
        </div>
      )}
    </div>
  );
}

// ─── HITL Tab ──────────────────────────────────────────────
function HITLTab({ onCountChange }) {
  const [items, setItems] = useState([
    { id: 1, agent_name: "logic", file_path: "auth/login.py", confidence_score: 0.60, failure_type: "engineering", status: "held_for_human", comment: "db.find() can return None but user.password accessed without null check — AttributeError at runtime." },
    { id: 2, agent_name: "style", file_path: "auth/login.py", confidence_score: 0.75, failure_type: "llm_uncertain", status: "held_for_human", comment: "login() missing docstring — return values and exceptions undocumented." },
  ]);

  useEffect(() => {
    onCountChange(items.filter((i) => i.status === "held_for_human").length);
  }, [items, onCountChange]);

  function decide(id, decision) {
    setItems((prev) => prev.map((i) => i.id === id ? { ...i, status: decision } : i));
  }

  const pending = items.filter((i) => i.status === "held_for_human");

  return (
    <div>
      <div className="topbar">
        <h1>HITL approval queue</h1>
        <span className="badge badge-warning">{pending.length} pending</span>
      </div>
      <div className="section">
        <div className="section-title">Awaiting your decision</div>
        {pending.length === 0
          ? <div className="empty-state">All caught up — no comments pending review.</div>
          : items.map((c) => <CommentCard key={c.id} comment={c} onDecide={decide} />)
        }
      </div>
    </div>
  );
}

// ─── History Tab ───────────────────────────────────────────
function HistoryTab() {
  const rows = [
    { status: "auto_posted", agent: "SECURITY", file: "utils/helpers.py", comment: "SQL injection vulnerability", conf: 0.99 },
    { status: "auto_posted", agent: "SECURITY", file: "auth/login.py", comment: "MD5 weak hashing", conf: 0.97 },
    { status: "auto_posted", agent: "TEST", file: "auth/login.py", comment: "login() has no test cases", conf: 0.88 },
    { status: "rejected", agent: "STYLE", file: "utils/helpers.py", comment: "Variable naming preference", conf: 0.52 },
    { status: "approved", agent: "LOGIC", file: "auth/login.py", comment: "None check missing", conf: 0.60 },
  ];
  const dotColor = { auto_posted: "#10b981", approved: "#10b981", rejected: "#ef4444" };
  return (
    <div>
      <div className="topbar"><h1>Review history</h1></div>
      <div className="section">
        <div className="section-title">Recent decisions</div>
        {rows.map((r, i) => (
          <div key={i} className="status-row">
            <div className="status-dot" style={{ background: dotColor[r.status] || "#888" }} />
            <span className="status-label">{r.status}</span>
            <span>[{r.agent}] {r.file} — {r.comment}</span>
            <span className="badge badge-muted" style={{ marginLeft: "auto" }}>{r.conf.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Coming Soon Tab ───────────────────────────────────────
function ComingSoonTab({ title, icon, description }) {
  return (
    <div>
      <div className="topbar"><h1>{title}</h1><span className="badge badge-muted">Coming soon</span></div>
      <div className="section">
        <div className="empty-state">
          <div style={{ fontSize: 32, marginBottom: 8 }}>{icon}</div>
          {description}
        </div>
      </div>
    </div>
  );
}

// ─── Root App ──────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState("pr");
  const [hitlCount, setHitlCount] = useState(2);

  const navItems = [
    { id: "pr", label: "PR Review", icon: "⬡" },
    { id: "bug", label: "Bug Triage", icon: "🐛" },
    { id: "doc", label: "Doc Compliance", icon: "📄" },
    { id: "hitl", label: "HITL Queue", icon: "👤", badge: hitlCount },
    { id: "history", label: "History", icon: "📋" },
  ];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo">AU<span>RA</span></div>
        <div className="nav-section">WORKFLOWS</div>
        {navItems.slice(0, 3).map((n) => (
          <button key={n.id} className={`nav-item ${tab === n.id ? "active" : ""}`} onClick={() => setTab(n.id)}>
            <span>{n.icon}</span> {n.label}
          </button>
        ))}
        <div className="nav-section">PLATFORM</div>
        {navItems.slice(3).map((n) => (
          <button key={n.id} className={`nav-item ${tab === n.id ? "active" : ""}`} onClick={() => setTab(n.id)}>
            <span>{n.icon}</span> {n.label}
            {n.badge > 0 && <span className="badge badge-warning" style={{ marginLeft: "auto" }}>{n.badge}</span>}
          </button>
        ))}
        <div className="sidebar-footer">
          <div>v1.0 · LangGraph</div>
          <div>Docker + Render</div>
        </div>
      </aside>

      <main className="main">
        {tab === "pr" && <PRReviewTab />}
        {tab === "bug" && <ComingSoonTab title="Bug Triage Agent" icon="🐛" description="Classify severity, detect duplicates, assign developers automatically." />}
        {tab === "doc" && <ComingSoonTab title="Document Compliance Agent" icon="📄" description="Upload contracts or policies for automated risk and compliance review." />}
        {tab === "hitl" && <HITLTab onCountChange={setHitlCount} />}
        {tab === "history" && <HistoryTab />}
      </main>
    </div>
  );
}
