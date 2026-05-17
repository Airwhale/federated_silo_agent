import { MermaidDiagram } from "@/components/MermaidDiagram";

const userFlow = `
sequenceDiagram
    actor Analyst as AML analyst
    participant A1 as A1 monitor
    participant A2 as A2 investigator
    participant F1 as F1 coordinator
    participant A3 as Peer bank A3 responders
    participant F2 as F2 graph analyst
    participant F3 as F3 sanctions screen
    participant F4 as F4 SAR drafter
    participant F5 as F5 audit

    Analyst->>A1: Review local alert
    A1->>A2: Send hash-only alert signal
    A2->>F1: Request Section 314(b) coordination
    F1->>A3: Route signed, purpose-bound query
    A3-->>F1: Return aggregate signals or refusal
    F1->>F2: Ask for cross-bank pattern analysis
    F1->>F3: Ask for sanctions and PEP context
    F2-->>F4: Pattern evidence with provenance
    F3-->>F4: Watchlist context without raw names
    F4->>F5: Draft SAR evidence packet
    F5-->>Analyst: Audit findings and review status
`;

const trustBoundaryFlow = `
flowchart LR
    subgraph Investigator["Investigating bank"]
        A1["A1 local monitor"]
        A2["A2 investigator"]
    end

    subgraph Federation["Federation TEE"]
        F1["F1 coordinator"]
        F2["F2 graph"]
        F3["F3 screen"]
        F4["F4 SAR"]
        F5["F5 audit"]
    end

    subgraph Silo["Each peer bank silo"]
        A3["A3 responder"]
        P7["P7 stats primitives"]
        DB[("Raw bank database")]
    end

    A1 -->|"local alert summary"| A2
    A2 -->|"hash tokens + purpose"| F1
    F1 -->|"signed route approval"| A3
    A3 -->|"approved primitive call"| P7
    P7 -.->|"raw data stays inside"| DB
    P7 -->|"counts, histograms, provenance"| A3
    A3 -->|"signed aggregate response"| F1
    F1 --> F2
    F1 --> F3
    F2 --> F4
    F3 --> F4
    F4 --> F5
`;

const protectionStack = `
flowchart TB
    Input["Prompt or structured message"]
    LT["Lobster Trap"]
    F6["F6 AML policy adapter"]
    Envelope["Signed envelope and allowlist"]
    Replay["Freshness and replay cache"]
    Schema["Pydantic schema contract"]
    Silo["A3 silo decision"]
    Primitive["P7 aggregate primitive"]
    Audit["Audit and provenance record"]

    Input --> LT
    LT --> F6
    F6 --> Envelope
    Envelope --> Replay
    Replay --> Schema
    Schema --> Silo
    Silo --> Primitive
    Primitive --> Audit
`;

const dataRelease = `
flowchart LR
    Raw["Raw names, accounts, transactions"]
    Hash["Cross-bank hash tokens"]
    Aggregate["Counts, histograms, graph intermediaries"]
    DP["DP budget and noise metadata"]
    Refusal["Structured refusals"]
    Audit["Audit trail"]

    Raw -.->|"never leaves bank"| Raw
    Hash -->|"allowed when purpose-bound"| Audit
    Aggregate -->|"allowed through A3/P7"| DP
    DP --> Audit
    Refusal --> Audit
`;

const protectionCards = [
  {
    title: "Hash-only linkage",
    body: "Banks correlate the same shell entity with stable tokens, not customer names. This makes cross-bank pattern detection possible without exposing identities in the normal query path.",
  },
  {
    title: "Signed envelopes",
    body: "Messages carry canonical body hashes, signatures, freshness checks, nonces, and request-response bindings. This is the layer that proves who sent what and blocks tampering or replay.",
  },
  {
    title: "Silo sovereignty",
    body: "F1 can coordinate, but each A3 responder still decides locally whether the request is allowed, useful, and inside the bank's privacy budget.",
  },
  {
    title: "Fixed data primitives",
    body: "Cross-bank data access goes through declared aggregate primitives. The model cannot ask for raw SQL rows or unbounded transaction dumps.",
  },
  {
    title: "Differential privacy",
    body: "Counts and histograms debit a privacy ledger and add calibrated noise where that protection is meaningful. Binary presence checks are handled by hash linkage and audit controls instead.",
  },
  {
    title: "Audit as product",
    body: "Every route, refusal, policy verdict, primitive call, DP debit, and SAR contribution is designed to be inspectable by compliance staff.",
  },
];

const lobsterTrapRules = [
  "Inspects natural-language prompts before they reach model routes.",
  "Blocks prompt injection, jailbreak attempts, credential requests, exfiltration requests, sensitive path access, and private-data extraction.",
  "Works with the AML adapter to enforce role and purpose rules around Section 314(b) coordination.",
  "Redacts or blocks customer-name leakage depending on the channel and message type.",
  "Records normalized policy verdicts so F5 and the UI can audit whether each governed message passed policy.",
];

export function AboutView() {
  return (
    <div className="mx-auto flex w-full max-w-[1700px] flex-col gap-4">
      <section className="grid gap-4 rounded-xl border border-slate-800 bg-slate-950 p-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(360px,0.8fr)]">
        <div className="space-y-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">
              About the demo
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal text-slate-50">
              Cross-bank AML investigation without raw data sharing
            </h1>
          </div>
          <p className="max-w-4xl text-sm leading-6 text-slate-300">
            Money laundering often spans several banks. Each institution sees only a
            local slice, so a ring can stay below every individual threshold while the
            pooled pattern is obvious. This project shows how bank-owned agents can
            coordinate under Section 314(b)-shaped rules, share only bounded signals,
            and produce an auditable SAR-ready evidence trail.
          </p>
          <p className="max-w-4xl text-sm leading-6 text-slate-300">
            The key claim is not that an LLM should freely inspect bank data. The key
            claim is that a typed, policy-governed federation can let specialist agents
            reason over aggregate evidence while each bank keeps raw customer records
            inside its own boundary.
          </p>
        </div>

        <div className="grid gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-emerald-200">
            What judges should look for
          </h2>
          <JudgePoint label="Federation" text="The pattern appears only after banks contribute governed signals." />
          <JudgePoint label="Privacy" text="Raw transactions and names stay inside the bank silos." />
          <JudgePoint label="Policy" text="Lobster Trap and F6 block unsafe model-channel requests." />
          <JudgePoint label="Auditability" text="Every answer has provenance, budget, route, and policy evidence." />
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <MermaidDiagram chart={userFlow} title="Investigation user flow" />
        <MermaidDiagram chart={trustBoundaryFlow} title="Trust-boundary data flow" />
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-100">
            What the system is doing
          </h2>
          <div className="mt-4 grid gap-3">
            <StepCard
              index="1"
              title="Detect a local alert"
              body="A bank-local monitor raises a suspicious activity signal from its own data."
            />
            <StepCard
              index="2"
              title="Ask a governed cross-bank question"
              body="The investigator asks F1 to coordinate with peer banks using hash tokens and a declared AML purpose."
            />
            <StepCard
              index="3"
              title="Let silos answer only what they can"
              body="Each A3 responder checks routing, purpose, schema, primitive allowlist, and DP budget before answering."
            />
            <StepCard
              index="4"
              title="Compose evidence"
              body="F2, F3, and F4 turn aggregate signals into pattern analysis, sanctions context, and a SAR draft."
            />
            <StepCard
              index="5"
              title="Audit the run"
              body="F5 reviews policy verdicts, route decisions, budget pressure, and provenance gaps."
            />
          </div>
        </div>
        <MermaidDiagram chart={protectionStack} title="Protection stack for governed messages" />
      </section>

      <section className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-5">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
              Lobster Trap implementation
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-normal text-slate-50">
              The model path is policy-gated before it reaches Gemini
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              Lobster Trap is the visible policy checkpoint for LLM-channel traffic.
              In this architecture, each trust domain has its own local route:
              agent to Lobster Trap to LiteLLM to the provider. The project then wraps
              that generic policy layer with an AML-specific F6 adapter that understands
              roles, routes, declared purpose, redaction, and audit semantics.
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-300">
              Lobster Trap is not the cryptographic integrity layer. It answers "is this
              prompt or response safe under policy?" The signed-envelope layer answers
              "who sent this, was it modified, is it fresh, and is this sender allowed?"
              The demo matters because both layers are visible and testable.
            </p>
          </div>
          <div className="grid gap-2">
            {lobsterTrapRules.map((rule) => (
              <div
                key={rule}
                className="rounded-lg border border-cyan-400/20 bg-slate-950/70 p-3 text-sm text-slate-300"
              >
                {rule}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="rounded-xl border border-slate-800 bg-slate-950 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-100">
            Data protections
          </h2>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {protectionCards.map((card) => (
              <div key={card.title} className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
                <h3 className="text-sm font-semibold text-slate-100">{card.title}</h3>
                <p className="mt-2 text-xs leading-5 text-slate-400">{card.body}</p>
              </div>
            ))}
          </div>
        </div>
        <MermaidDiagram chart={dataRelease} title="What may cross a bank boundary" />
      </section>

      <section className="rounded-xl border border-slate-800 bg-slate-950 p-5">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-100">
          How to read the rest of the console
        </h2>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <GuideCard
            title="Demo Flow"
            body="Follow the canonical AML story, click nodes and edges, and see how evidence moves without raw data leaving silos."
          />
          <GuideCard
            title="Console"
            body="Inspect topology, timeline, system readiness, provider health, component state, and controlled interactions."
          />
          <GuideCard
            title="Lobster Trap"
            body="Try safe and malicious prompts against the policy gate and see what would be allowed toward an LLM route."
          />
        </div>
      </section>
    </div>
  );
}

function JudgePoint({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded border border-emerald-500/20 bg-slate-950/60 p-3">
      <span className="text-xs font-semibold uppercase tracking-wide text-emerald-200">
        {label}
      </span>
      <p className="mt-1 text-slate-300">{text}</p>
    </div>
  );
}

function StepCard({ index, title, body }: { index: string; title: string; body: string }) {
  return (
    <div className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded border border-cyan-400/30 bg-cyan-500/10 text-xs font-semibold text-cyan-200">
        {index}
      </div>
      <div>
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        <p className="mt-1 text-xs leading-5 text-slate-400">{body}</p>
      </div>
    </div>
  );
}

function GuideCard({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/40 p-3">
      <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
      <p className="mt-2 text-xs leading-5 text-slate-400">{body}</p>
    </div>
  );
}
