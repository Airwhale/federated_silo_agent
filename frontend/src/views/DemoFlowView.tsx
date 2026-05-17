import * as Dialog from "@radix-ui/react-dialog";
import {
  BookOpen,
  Download,
  ExternalLink,
  Info,
  Network,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { describeError } from "@/api/errors";
import {
  useCaseNotebookReport,
  useComponent,
  useGenerateCaseNotebook,
  useTimeline,
} from "@/api/hooks";
import type {
  ComponentId,
  ProbeKind,
  SnapshotStatus,
  TimelineEventSnapshot,
} from "@/api/types";
import { AttackLabSelectorCard } from "@/components/attack/AttackLabSelectorCard";
import { KeyValueGrid, type KeyValueRow } from "@/components/inspector/KeyValueGrid";
import { RawJsonPanel } from "@/components/inspector/RawJsonPanel";
import { useSessionContext } from "@/components/SessionContext";
import { StatusPill } from "@/components/StatusPill";

type ScenarioId = "s1_structuring_ring" | "s2_layering" | "s3_sanctions_evasion";
type StageId =
  | "A1"
  | "A2"
  | "F1"
  | "A3_ALPHA"
  | "A3_BETA"
  | "A3_GAMMA"
  | "F1_AGGREGATE"
  | "A2_SYNTHESIS"
  | "F2"
  | "F3"
  | "F4"
  | "F5";
type EdgeId =
  | "A1_TO_A2"
  | "A2_TO_F1"
  | "F1_TO_ALPHA_A3"
  | "F1_TO_BETA_A3"
  | "F1_TO_GAMMA_A3"
  | "ALPHA_A3_TO_F1"
  | "BETA_A3_TO_F1"
  | "GAMMA_A3_TO_F1"
  | "F1_TO_A2_SYNTHESIS"
  | "A2_TO_F2"
  | "F2_TO_F3"
  | "F2_TO_F4"
  | "F3_TO_F4"
  | "F4_TO_F5";

type ScenarioConfig = {
  id: ScenarioId;
  label: string;
  shortLabel: string;
  amlPattern: string;
  plainDefinition: string;
  expectedSignal: string;
};

type FlowStage = {
  id: StageId;
  label: string;
  domain: string;
  componentId: ComponentId;
  instanceId?: "investigator" | "federation" | "bank_alpha" | "bank_beta" | "bank_gamma";
  summary: string;
  output: string;
  activeNode: string;
  communicatesWith: string;
  outputDetail: string;
  whyItMatters: string;
  graphClass: string;
  matches: (event: TimelineEventSnapshot) => boolean;
};

type FlowEdge = {
  id: EdgeId;
  from: StageId;
  to: StageId;
  label: string;
  path: string;
  hotspotClass: string;
  connects: string;
  correctOutput: string;
  protection: string;
  risk: string;
};

const SCENARIOS: ScenarioConfig[] = [
  {
    id: "s1_structuring_ring",
    label: "S1: Structuring ring",
    shortLabel: "Structuring",
    amlPattern: "structuring ring",
    plainDefinition: "many small transfers shaped to avoid thresholds",
    expectedSignal: "F2 should find a ring pattern and F4 should produce a high-priority SAR draft.",
  },
  {
    id: "s2_layering",
    label: "S2: Layering chain",
    shortLabel: "Layering",
    amlPattern: "layering chain",
    plainDefinition: "funds move through hops to hide origin",
    expectedSignal: "F2 should expose movement across banks, even when no silo sees the whole path.",
  },
  {
    id: "s3_sanctions_evasion",
    label: "S3: Sanctions evasion",
    shortLabel: "Sanctions",
    amlPattern: "sanctions evasion",
    plainDefinition: "activity routes around a screened party or watchlist risk",
    expectedSignal: "F3 should add watchlist context and F4 should cite it without leaking raw lists.",
  },
];

const FLOW_STAGES: FlowStage[] = [
  {
    id: "A1",
    label: "A1 alert",
    domain: "Investigator bank",
    componentId: "A1",
    instanceId: "bank_alpha",
    summary: "Finds a local suspicious seed without sending raw customer data.",
    output: "Hash-only alert candidate",
    activeNode: "Bank Alpha A1 local monitor",
    communicatesWith: "Local bank data only; no federation message yet.",
    outputDetail:
      "A hash-only alert seed that says something looks unusual without naming the customer.",
    whyItMatters:
      "The demo starts with one bank seeing only its own slice. Privacy is preserved before federation begins.",
    graphClass: "lg:left-[3%] lg:top-[12%] lg:w-[13%]",
    matches: (event) => event.component_id === "A1" || event.title.includes("bank_alpha.A1"),
  },
  {
    id: "A2",
    label: "A2 query",
    domain: "Investigator bank",
    componentId: "A2",
    instanceId: "bank_alpha",
    summary: "Turns the alert into a narrow Section 314(b) request.",
    output: "Signed query draft",
    activeNode: "Bank Alpha A2 investigator",
    communicatesWith: "F1 federation coordinator.",
    outputDetail:
      "A signed Section 314(b) query containing hashes, purpose, route kind, and bounded request shape.",
    whyItMatters:
      "A2 narrows the question before it leaves the bank, so peers are not asked for broad data dumps.",
    graphClass: "lg:left-[18%] lg:top-[12%] lg:w-[13%]",
    matches: (event) =>
      (event.component_id === "A2" || event.title.includes("bank_alpha.A2"))
      && !event.detail.toLowerCase().includes("sar contribution"),
  },
  {
    id: "F1",
    label: "F1 route",
    domain: "Federation TEE",
    componentId: "F1",
    instanceId: "federation",
    summary: "Verifies the query, approves routes, and fans out to peer silos.",
    output: "Route approvals",
    activeNode: "F1 federation coordinator in the TEE",
    communicatesWith: "A2 on ingress; Bank Beta and Bank Gamma A3 responders on fan-out.",
    outputDetail:
      "Signed route approvals and per-bank contribution requests bound to the original query body.",
    whyItMatters:
      "F1 coordinates the peer federation without becoming an LLM. It checks authorization and prevents route drift.",
    graphClass: "lg:left-[40%] lg:top-[12%] lg:w-[14%]",
    matches: (event) =>
      isLiveTurnEvent(event, "F1", "federation.F1")
      && event.detail.toLowerCase().includes("routed"),
  },
  {
    id: "A3_ALPHA",
    label: "Alpha A3/P7",
    domain: "Bank Alpha silo",
    componentId: "bank_alpha.A3",
    instanceId: "bank_alpha",
    summary: "Available local silo responder, but not called in this Alpha-investigates-peers story.",
    output: "Optional local DP aggregate",
    activeNode: "Bank Alpha A3 responder plus P7 privacy primitives",
    communicatesWith: "Only used when F1 needs Alpha's silo responder. This scenario uses Alpha A1/A2 locally instead.",
    outputDetail:
      "No Alpha A3 response is expected in the default run. Alpha's local evidence enters through A1/A2.",
    whyItMatters:
      "The pending state is intentional here: Alpha is the investigating bank, while Beta and Gamma are the peer silos being queried.",
    graphClass: "lg:left-[5%] lg:top-[72%] lg:w-[15%]",
    matches: (event) =>
      event.component_id === "bank_alpha.A3"
      || (event.component_id === "P7" && event.title.toLowerCase().includes("alpha")),
  },
  {
    id: "A3_BETA",
    label: "Beta A3/P7",
    domain: "Bank Beta silo",
    componentId: "bank_beta.A3",
    instanceId: "bank_beta",
    summary: "Beta checks policy and returns approved DP aggregates.",
    output: "DP aggregate evidence",
    activeNode: "Bank Beta A3 responder plus P7 privacy primitives",
    communicatesWith: "F1 sends a signed contribution request; Beta A3 returns aggregate fields.",
    outputDetail:
      "Bank Beta DP-noised counts, histograms, or graph features. Raw rows and names stay inside Beta.",
    whyItMatters:
      "The laundering pattern needs multiple banks. Beta adds signal without sharing raw customer records.",
    graphClass: "lg:left-[22%] lg:top-[72%] lg:w-[15%]",
    matches: (event) =>
      event.component_id === "bank_beta.A3"
      || (event.component_id === "P7" && event.title.toLowerCase().includes("beta")),
  },
  {
    id: "A3_GAMMA",
    label: "Gamma A3/P7",
    domain: "Bank Gamma silo",
    componentId: "bank_gamma.A3",
    instanceId: "bank_gamma",
    summary: "Gamma checks policy and returns approved DP aggregates.",
    output: "DP aggregate evidence",
    activeNode: "Bank Gamma A3 responder plus P7 privacy primitives",
    communicatesWith: "F1 sends a signed contribution request; Gamma A3 returns aggregate fields.",
    outputDetail:
      "Bank Gamma DP-noised counts, histograms, or graph features. Raw rows and names stay inside Gamma.",
    whyItMatters:
      "Gamma completes the cross-bank view while preserving the same local controls as the other silos.",
    graphClass: "lg:left-[39%] lg:top-[72%] lg:w-[15%]",
    matches: (event) =>
      event.component_id === "bank_gamma.A3"
      || (event.component_id === "P7" && event.title.toLowerCase().includes("gamma")),
  },
  {
    id: "F1_AGGREGATE",
    label: "F1 aggregate",
    domain: "Federation TEE",
    componentId: "F1",
    instanceId: "federation",
    summary: "Combines signed A3 responses into the bounded answer for A2.",
    output: "Aggregated peer response",
    activeNode: "F1 federation coordinator, aggregation phase",
    communicatesWith: "Each A3 response on ingress; A2 receives the aggregate response.",
    outputDetail:
      "A signed Sec314bResponse containing only the fields that A3s were allowed to release.",
    whyItMatters:
      "This is where silo answers are combined. A3 does not hand raw or direct data to F2.",
    graphClass: "lg:left-[40%] lg:top-[42%] lg:w-[14%]",
    matches: (event) =>
      isLiveTurnEvent(event, "F1", "federation.F1")
      && event.detail.toLowerCase().includes("aggregated response"),
  },
  {
    id: "A2_SYNTHESIS",
    label: "A2 synthesis",
    domain: "Investigator bank",
    componentId: "A2",
    instanceId: "bank_alpha",
    summary: "Reviews F1's aggregate response and emits SAR-ready contribution evidence.",
    output: "SAR contribution",
    activeNode: "Bank Alpha A2 investigator, synthesis phase",
    communicatesWith: "F1 aggregate response on input; F1/F4 assembly path on output.",
    outputDetail:
      "A structured SARContribution with hash-only evidence and deterministic amount range in the canonical run.",
    whyItMatters:
      "A2 remains the investigator of record. Federation specialists work from this bounded contribution.",
    graphClass: "lg:left-[5%] lg:top-[42%] lg:w-[16%]",
    matches: (event) =>
      (event.component_id === "A2" || event.title.includes("bank_alpha.A2"))
      && event.detail.toLowerCase().includes("sar contribution"),
  },
  {
    id: "F2",
    label: "F2 graph",
    domain: "Federation TEE",
    componentId: "F2",
    instanceId: "federation",
    summary: "Looks for laundering structure across the silo aggregates.",
    output: "Pattern finding",
    activeNode: "F2 graph analysis",
    communicatesWith: "F1-built graph request on input; F3 and F4 consume the graph finding.",
    outputDetail:
      "A graph finding such as structuring ring or layering chain, with confidence and evidence references.",
    whyItMatters:
      "F2 finds the AML pattern that no single bank can see alone, using aggregate-only inputs.",
    graphClass: "lg:left-[67%] lg:top-[12%] lg:w-[13%]",
    matches: (event) => event.component_id === "F2" || event.title.includes("federation.F2"),
  },
  {
    id: "F3",
    label: "F3 screen",
    domain: "Federation TEE",
    componentId: "F3",
    instanceId: "federation",
    summary: "Adds sanctions and PEP context from hash-only watchlist checks.",
    output: "Sanctions context",
    activeNode: "F3 sanctions screener",
    communicatesWith: "F2 suspect hashes on input; F4 consumes the sanctions context.",
    outputDetail:
      "Bounded sanctions or PEP hit metadata, not the full watchlist and not raw customer identifiers.",
    whyItMatters:
      "Sanctions context changes urgency, but the system must not leak watchlist internals.",
    graphClass: "lg:left-[67%] lg:top-[48%] lg:w-[13%]",
    matches: (event) => event.component_id === "F3" || event.title.includes("federation.F3"),
  },
  {
    id: "F4",
    label: "F4 SAR",
    domain: "Federation TEE",
    componentId: "F4",
    instanceId: "federation",
    summary: "Drafts a SAR from validated evidence and provenance.",
    output: "SAR draft",
    activeNode: "F4 SAR drafter",
    communicatesWith: "A2 contribution, F2 pattern finding, and F3 sanctions result.",
    outputDetail:
      "A SAR draft with deterministic fields and a narrative limited to validated evidence.",
    whyItMatters:
      "The LLM can help write, but it must not invent facts. F4 keeps provenance attached to the report.",
    graphClass: "lg:left-[84%] lg:top-[30%] lg:w-[12%]",
    matches: (event) => event.component_id === "F4" || event.title.includes("federation.F4"),
  },
  {
    id: "F5",
    label: "F5 audit",
    domain: "Federation TEE",
    componentId: "F5",
    instanceId: "federation",
    summary: "Reviews message order, policy verdicts, budget use, and refusal handling.",
    output: "Audit finding summary",
    activeNode: "F5 audit reviewer",
    communicatesWith: "Audit chain, F4 SAR output, policy records, and DP provenance.",
    outputDetail:
      "A finding list over route purpose, rate limits, LT verdicts, budget use, and missing audit events.",
    whyItMatters:
      "Judges can see whether the system only got an answer, or got it through governed, reviewable steps.",
    graphClass: "lg:left-[84%] lg:top-[70%] lg:w-[12%]",
    matches: (event) => event.component_id === "F5" || event.title.includes("federation.F5"),
  },
];

const FLOW_EDGES: FlowEdge[] = [
  {
    id: "A1_TO_A2",
    from: "A1",
    to: "A2",
    label: "A1 to A2",
    path: "M16 23 L18 23",
    hotspotClass: "left-[16%] top-[21%]",
    connects: "Bank Alpha A1 hands a local suspicious-activity seed to Bank Alpha A2.",
    correctOutput:
      "A hash-only alert candidate with evidence references and typology hints. No customer name, account number, or raw transaction row should appear.",
    protection:
      "The hop stays inside Bank Alpha. Raw data remains local; downstream messages start from hashes and bounded alert metadata.",
    risk:
      "Bad state: A1 emits raw customer data or broad data requests before A2 narrows the investigation.",
  },
  {
    id: "A2_TO_F1",
    from: "A2",
    to: "F1",
    label: "A2 to F1",
    path: "M31 23 C34 23 37 23 40 23",
    hotspotClass: "left-[34%] top-[21%]",
    connects: "A2 sends the Section 314(b) request to F1 in the federation TEE.",
    correctOutput:
      "A signed Sec314bQuery with purpose, target banks, route kind, nonce, expiry, and hash-only query payload.",
    protection:
      "F1 checks signature, allowlist, freshness, replay, purpose, route shape, and body binding before fan-out.",
    risk:
      "Bad state: unsigned, stale, replayed, over-broad, or purpose-free queries reach a silo.",
  },
  {
    id: "F1_TO_ALPHA_A3",
    from: "F1",
    to: "A3_ALPHA",
    label: "F1 to Alpha A3",
    path: "M47 33 C42 51 18 59 12.5 72",
    hotspotClass: "left-[29%] top-[50%]",
    connects: "F1 routes a signed local contribution request to Bank Alpha A3.",
    correctOutput:
      "A route approval plus local contribution request bound to the original query body and scoped to approved aggregate fields.",
    protection:
      "A3 verifies F1 signature, route approval, body hash, replay/freshness, local policy, and DP budget before any primitive runs.",
    risk:
      "Bad state: A3 accepts a request not signed by F1 or not bound to the approved query body.",
  },
  {
    id: "F1_TO_BETA_A3",
    from: "F1",
    to: "A3_BETA",
    label: "F1 to Beta A3",
    path: "M47 33 C43 52 33 60 29.5 72",
    hotspotClass: "left-[38%] top-[55%]",
    connects: "F1 routes a signed peer request to Bank Beta A3.",
    correctOutput:
      "A peer contribution request asking only for approved DP aggregates or graph intermediaries.",
    protection:
      "Beta A3 enforces route approval, signature, replay/freshness, local policy, and per-requester DP budget.",
    risk:
      "Bad state: the request asks Beta for raw rows, unsupported query shapes, or unapproved metrics.",
  },
  {
    id: "F1_TO_GAMMA_A3",
    from: "F1",
    to: "A3_GAMMA",
    label: "F1 to Gamma A3",
    path: "M47 33 C48 52 46.5 61 46.5 72",
    hotspotClass: "left-[47%] top-[55%]",
    connects: "F1 routes a signed peer request to Bank Gamma A3.",
    correctOutput:
      "A peer contribution request with the same approved query shape as the other silos.",
    protection:
      "Gamma A3 performs the same cryptographic, route, policy, replay, and DP checks as every silo.",
    risk:
      "Bad state: one silo has weaker checks than the others or silently accepts a route mismatch.",
  },
  {
    id: "ALPHA_A3_TO_F1",
    from: "A3_ALPHA",
    to: "F1_AGGREGATE",
    label: "Alpha A3 to F1",
    path: "M12.5 72 C23 64 33 59 40 54",
    hotspotClass: "left-[25%] top-[62%]",
    connects: "Bank Alpha A3 sends its allowed aggregate response back to F1.",
    correctOutput:
      "A signed Sec314bResponse with DP aggregate fields, provenance records, and any refusal reason if Alpha cannot answer.",
    protection:
      "Response is signed by A3; raw rows stay in Alpha; DP noise and ledger records travel as provenance.",
    risk:
      "Bad state: response omits provenance, hides budget use, or includes raw bank data.",
  },
  {
    id: "BETA_A3_TO_F1",
    from: "A3_BETA",
    to: "F1_AGGREGATE",
    label: "Beta A3 to F1",
    path: "M29.5 72 C34 63 38 58 40 54",
    hotspotClass: "left-[35%] top-[63%]",
    connects: "Bank Beta A3 sends its allowed aggregate response back to F1.",
    correctOutput:
      "A signed Sec314bResponse containing only approved aggregate fields and provenance.",
    protection:
      "F1 verifies A3 identity and response binding; Beta protects raw data with local policy and DP primitives.",
    risk:
      "Bad state: Beta sends fields outside the route approval or loses refusal details.",
  },
  {
    id: "GAMMA_A3_TO_F1",
    from: "A3_GAMMA",
    to: "F1_AGGREGATE",
    label: "Gamma A3 to F1",
    path: "M46.5 72 L46.5 57",
    hotspotClass: "left-[45.5%] top-[64%]",
    connects: "Bank Gamma A3 sends its allowed aggregate response back to F1.",
    correctOutput:
      "A signed response with aggregate values, DP provenance, or a typed refusal.",
    protection:
      "Gamma signs the response; F1 verifies the sender and preserves partial refusals instead of treating missing data as clean.",
    risk:
      "Bad state: a missing Gamma answer is hidden from A2, F4, or F5.",
  },
  {
    id: "F1_TO_A2_SYNTHESIS",
    from: "F1_AGGREGATE",
    to: "A2_SYNTHESIS",
    label: "F1 aggregate to A2",
    path: "M40 51 C34 51 27 51 21 51",
    hotspotClass: "left-[31%] top-[49%]",
    connects: "F1 returns the aggregate peer response to A2 for investigator synthesis.",
    correctOutput:
      "A bounded Sec314bResponse with successful fields, provenance, and partial-refusal notes when any silo declined.",
    protection:
      "F1 signs the aggregate response and keeps each field tied to source provenance and route approval.",
    risk:
      "Bad state: F1 changes the question, drops refusals, or makes the response look complete when peers refused.",
  },
  {
    id: "A2_TO_F2",
    from: "A2_SYNTHESIS",
    to: "F2",
    label: "A2 evidence to F2",
    path: "M21 47 C38 35 55 23 67 23",
    hotspotClass: "left-[54%] top-[30%]",
    connects: "A2's SAR-ready contribution feeds the graph-analysis request assembled for F2.",
    correctOutput:
      "A GraphAnalysisRequest with DP-noised graph summaries, hash tokens, and evidence references.",
    protection:
      "F2 receives aggregate graph intermediaries, not raw bank transactions. Schema checks reject invented or raw identifiers.",
    risk:
      "Bad state: F2 sees raw transactions or is allowed to invent stronger suspect hashes.",
  },
  {
    id: "F2_TO_F3",
    from: "F2",
    to: "F3",
    label: "F2 to F3",
    path: "M73.5 35 L73.5 48",
    hotspotClass: "left-[72.5%] top-[40%]",
    connects: "F2 passes suspect hash context to F3 for sanctions and PEP screening.",
    correctOutput:
      "A bounded sanctions-check request with hash tokens and graph finding references.",
    protection:
      "F3 screens hashes and returns limited hit metadata. It does not expose raw watchlist contents or customer names.",
    risk:
      "Bad state: watchlist internals or raw customer identifiers leak into the graph result.",
  },
  {
    id: "F2_TO_F4",
    from: "F2",
    to: "F4",
    label: "F2 to F4",
    path: "M80 24 C83 25 84 31 84 39",
    hotspotClass: "left-[82%] top-[30%]",
    connects: "F2 sends the graph pattern finding to F4 for SAR drafting.",
    correctOutput:
      "A pattern finding such as structuring ring or layering chain, with confidence, evidence IDs, and provenance.",
    protection:
      "F4 must draft from supplied findings only. LT/F6 and schema checks guard against fabricated evidence.",
    risk:
      "Bad state: the report narrative contains graph claims not present in F2's structured finding.",
  },
  {
    id: "F3_TO_F4",
    from: "F3",
    to: "F4",
    label: "F3 to F4",
    path: "M80 57 C83 55 84 50 84 43",
    hotspotClass: "left-[82%] top-[50%]",
    connects: "F3 sends sanctions and PEP context to F4.",
    correctOutput:
      "A sanctions result with match status, confidence, watchlist category, and evidence references.",
    protection:
      "Only bounded hit metadata moves forward; raw watchlist records and secrets stay out of the SAR draft.",
    risk:
      "Bad state: F4 cites sanctions facts without a validated F3 result.",
  },
  {
    id: "F4_TO_F5",
    from: "F4",
    to: "F5",
    label: "F4 to F5",
    path: "M90 51 L90 70",
    hotspotClass: "left-[89%] top-[60%]",
    connects: "F4 sends the SAR draft and evidence trail to F5 for governance review.",
    correctOutput:
      "A SAR draft plus audit window covering route purpose, policy verdicts, DP ledger, refusals, and provenance.",
    protection:
      "F5 is read-only. It checks audit continuity and flags gaps rather than mutating the SAR or protected state.",
    risk:
      "Bad state: the demo produces a report without auditable route, policy, or budget evidence.",
  },
];

const CRYPTO_PROBES: ProbeKind[] = [
  "unsigned_message",
  "body_tamper",
  "wrong_role",
  "replay_nonce",
];
const A3_PROBES: ProbeKind[] = [
  "route_mismatch",
  "unsupported_query_shape",
  "budget_exhaustion",
];
const MODEL_PROBES: ProbeKind[] = ["prompt_injection"];

function probeKindsForStage(stage: FlowStage): ProbeKind[] {
  if (stage.id === "A2" || stage.id === "F1" || stage.id === "F1_AGGREGATE") {
    return CRYPTO_PROBES;
  }
  if (stage.id === "A3_ALPHA" || stage.id === "A3_BETA" || stage.id === "A3_GAMMA") {
    return A3_PROBES;
  }
  if (stage.id === "F2" || stage.id === "F4") {
    return MODEL_PROBES;
  }
  return [];
}

function probeKindsForEdge(edge: FlowEdge): ProbeKind[] {
  if (edge.to === "A3_ALPHA" || edge.to === "A3_BETA" || edge.to === "A3_GAMMA") {
    return ["route_mismatch", "body_tamper"];
  }
  if (edge.to === "F2" || edge.to === "F4") {
    return MODEL_PROBES;
  }
  if (edge.to === "F1" || edge.to === "F1_AGGREGATE" || edge.to === "A2_SYNTHESIS") {
    return CRYPTO_PROBES;
  }
  return [];
}

function modelRouteNote(stage: FlowStage): string | null {
  switch (stage.id) {
    case "A1":
      return "Optional model use starts from local alert summaries only. Any prompt must pass local Lobster Trap before LiteLLM/provider.";
    case "A2":
      return "A2 can use a model to draft a narrow query, but F1 still requires signed, hash-only, schema-valid output.";
    case "F2":
      return "F2 uses deterministic graph rules first. If model fallback is used, it sees DP-noised graph summaries, not raw rows.";
    case "F4":
      return "F4 uses the model for SAR narrative wording only. Required fields and provenance remain deterministic.";
    default:
      return null;
  }
}

function visibleFlowEdges(): FlowEdge[] {
  return FLOW_EDGES.filter((edge) => edge.from !== "A3_ALPHA" && edge.to !== "A3_ALPHA");
}

function scenarioById(id: ScenarioId): ScenarioConfig {
  return SCENARIOS.find((scenario) => scenario.id === id) ?? SCENARIOS[0];
}

function isLiveTurnEvent(
  event: TimelineEventSnapshot,
  componentId: ComponentId,
  agentId: string,
): boolean {
  return event.component_id === componentId && event.title === `Live turn: ${agentId}`;
}

function latestStageEvent(
  events: TimelineEventSnapshot[],
  stage: FlowStage,
): TimelineEventSnapshot | undefined {
  return [...events].reverse().find(stage.matches);
}

function stageStatus(events: TimelineEventSnapshot[], stage: FlowStage): SnapshotStatus {
  if (stage.id === "A3_ALPHA" && !latestStageEvent(events, stage)) return "simulated";
  const event = latestStageEvent(events, stage);
  if (!event) return "pending";
  if (event.status === "blocked" || event.status === "error") return event.status;
  return "live";
}

function stageTone(status: SnapshotStatus, selected: boolean): string {
  if (selected) return "border-sky-400/80 bg-sky-500/15";
  if (status === "live") return "border-emerald-400/50 bg-emerald-500/10";
  if (status === "blocked" || status === "error") return "border-rose-400/50 bg-rose-500/10";
  if (status === "simulated") return "border-cyan-400/40 bg-cyan-500/10";
  return "border-slate-800 bg-slate-900/50";
}

function graphCaption(stage: FlowStage): string {
  switch (stage.id) {
    case "A1":
      return "Local alert seed";
    case "A2":
      return "Signed Section 314(b) query";
    case "F1":
      return "Signed route approvals";
    case "A3_ALPHA":
      return "Not used in this scenario";
    case "A3_BETA":
      return "Beta policy + DP aggregate";
    case "A3_GAMMA":
      return "Gamma policy + DP aggregate";
    case "F1_AGGREGATE":
      return "A3 responses -> A2";
    case "A2_SYNTHESIS":
      return "SAR contribution evidence";
    case "F2":
      return "Cross-bank pattern finding";
    case "F3":
      return "Sanctions and PEP context";
    case "F4":
      return "SAR draft with provenance";
    case "F5":
      return "Audit finding summary";
  }
}

function latestFinding(events: TimelineEventSnapshot[], scenario: ScenarioConfig): string {
  const f2Event = [...events].reverse().find((event) => event.title.includes("federation.F2"));
  if (f2Event) return f2Event.detail;
  return `Expected AML target: ${scenario.amlPattern}. ${scenario.expectedSignal}`;
}

export function DemoFlowView() {
  const { sessionId, session, setSelection } = useSessionContext();
  const [selectedStageId, setSelectedStageId] = useState<StageId>("F2");
  const [selectedEdgeId, setSelectedEdgeId] = useState<EdgeId | null>(null);
  const [openEdgeDrawerId, setOpenEdgeDrawerId] = useState<EdgeId | null>(null);
  const [autoReportSessionId, setAutoReportSessionId] = useState<string | null>(null);

  const timeline = useTimeline(sessionId);
  const report = useGenerateCaseNotebook(sessionId);
  const latestReport = useCaseNotebookReport(sessionId);
  const events = timeline.data ?? session?.latest_events ?? [];
  const selectedScenario = scenarioById(
    (session?.scenario_id as ScenarioId | undefined) ?? "s1_structuring_ring",
  );
  const selectedStage = FLOW_STAGES.find((stage) => stage.id === selectedStageId)
    ?? FLOW_STAGES.find((stage) => stage.id === "F2")
    ?? FLOW_STAGES[0];
  const selectedEdge = FLOW_EDGES.find((edge) => edge.id === selectedEdgeId) ?? null;
  const openEdge = FLOW_EDGES.find((edge) => edge.id === openEdgeDrawerId) ?? null;
  const selectedComponent = useComponent(sessionId, selectedStage.componentId, selectedStage.instanceId);
  const selectedStageStatus = stageStatus(events, selectedStage);
  const activeReport = report.data ?? latestReport.data;
  const generatedReport = activeReport?.status === "live" ? activeReport : null;

  const currentStageIndex = useMemo(() => {
    const indexes = FLOW_STAGES.map((stage, index) =>
      latestStageEvent(events, stage) ? index : -1,
    ).filter((index) => index >= 0);
    return indexes.length ? Math.max(...indexes) : 0;
  }, [events]);

  useEffect(() => {
    const completed =
      session?.phase === "Canonical demo completed with SAR draft and clean audit.";
    if (
      !completed
      || !sessionId
      || report.data
      || latestReport.data?.status === "live"
      || report.isPending
      || autoReportSessionId === sessionId
    ) {
      return;
    }
    setAutoReportSessionId(sessionId);
    report.mutate();
  }, [autoReportSessionId, latestReport.data?.status, report, session?.phase, sessionId]);

  const openInspector = () =>
    setSelection({
      componentId: selectedStage.componentId,
      instanceId: selectedStage.instanceId,
    });

  const selectGraphStage = (stageId: StageId) => {
    const stage = FLOW_STAGES.find((item) => item.id === stageId);
    if (!stage) return;
    setSelectedEdgeId(null);
    setOpenEdgeDrawerId(null);
    setSelectedStageId(stage.id);
  };

  const openReportPage = () => {
    if (!generatedReport) return;
    const url = `${window.location.origin}${window.location.pathname}#/notebook`;
    window.open(url, "_blank", "noopener,noreferrer");
  };

  const downloadReportHtml = () => {
    if (!generatedReport) return;
    const fileName = `${generatedReport.scenario_id}_analysis.html`;
    const blob = new Blob([generatedReport.notebook_html], {
      type: "text/html;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="min-w-0 rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/70 px-3 py-2">
        <div className="min-w-0">
          <h1 className="text-sm font-semibold uppercase tracking-wide text-slate-100">
            Run the story
          </h1>
          <p className="mt-1 text-xs text-slate-400">
            Use the top bar: choose a scenario, click <strong>Reset</strong>, then
            <strong> Step</strong> or <strong>Run</strong>. Click any node or edge to change the card below.
          </p>
          <p className="mt-1 text-[11px] text-slate-500">
            <span className="font-semibold text-emerald-100">{selectedScenario.shortLabel}</span>
            <span className="text-slate-600"> | </span>
            {selectedScenario.plainDefinition}. {latestFinding(events, selectedScenario)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={!sessionId || report.isPending}
            onClick={() => report.mutate()}
            className="inline-flex items-center gap-1.5 rounded border border-emerald-400/50 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-100 hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40"
            title="Run the canonical path if needed, then generate notebook and artifact HTML"
          >
            <BookOpen size={13} aria-hidden />
            Generate report
          </button>
          <button
            type="button"
            disabled={!generatedReport}
            onClick={openReportPage}
            className="inline-flex items-center gap-1.5 rounded border border-sky-400/50 bg-sky-500/10 px-2.5 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-500/20 disabled:cursor-not-allowed disabled:opacity-40"
            title={
              generatedReport
                ? "Open the generated notebook report in a separate browser page"
                : "Generate a report first"
            }
          >
            <ExternalLink size={13} aria-hidden />
            View report
          </button>
          <button
            type="button"
            disabled={!generatedReport}
            onClick={downloadReportHtml}
            className="inline-flex items-center gap-1.5 rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-100 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40"
            title={
              generatedReport
                ? "Download the generated notebook report as HTML"
                : "Generate a report first"
            }
          >
            <Download size={13} aria-hidden />
            Download HTML
          </button>
          <StatusPill status={session ? "live" : "pending"} label={session?.phase ?? "not run"} />
        </div>
      </header>

      <div className="space-y-2 p-3">
        <FlowGraph
          events={events}
          currentStageIndex={currentStageIndex}
          selectedStageId={selectedStage.id}
          selectedEdgeId={selectedEdgeId}
          onSelectStage={selectGraphStage}
          onSelectEdge={setSelectedEdgeId}
        >
          <UnifiedInteractionCard
            componentError={selectedComponent.error}
            componentFields={(selectedComponent.data?.fields ?? []).map((field) => ({
              label: field.name,
              value: field.redacted ? "[redacted]" : field.value,
            }))}
            componentRaw={selectedComponent.data}
            componentStatus={
              selectedStage.id === "A3_ALPHA"
                ? selectedStageStatus
                : selectedComponent.data?.status ?? "pending"
            }
            edge={selectedEdge}
            event={latestStageEvent(events, selectedStage)}
            onOpenEdgeDrawer={() => selectedEdge ? setOpenEdgeDrawerId(selectedEdge.id) : undefined}
            onOpenInspector={openInspector}
            scenario={selectedScenario}
            stage={selectedStage}
          />
        </FlowGraph>

        {report.error ?? latestReport.error ? (
          <ErrorBox error={report.error ?? latestReport.error} />
        ) : null}
      </div>
      <EdgeDrawer edge={openEdge} onClose={() => setOpenEdgeDrawerId(null)} />
    </section>
  );
}

function FlowGraph({
  children,
  events,
  currentStageIndex,
  selectedStageId,
  selectedEdgeId,
  onSelectStage,
  onSelectEdge,
}: {
  children?: ReactNode;
  events: TimelineEventSnapshot[];
  currentStageIndex: number;
  selectedStageId: StageId;
  selectedEdgeId: EdgeId | null;
  onSelectStage: (stageId: StageId) => void;
  onSelectEdge: (edgeId: EdgeId) => void;
}) {
  const graphEdges = visibleFlowEdges();

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950 p-2.5">
      <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Edge and node path
          </h2>
          <p className="text-[11px] text-slate-500">
            F1 coordinates the exchange; each A3 sits inside a bank data boundary; F2-F5 consume
            governed outputs. Click a node for state or an edge for the message contract.
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5 text-[10px] uppercase tracking-wide">
          <span className="rounded border border-cyan-400/40 bg-cyan-500/15 px-2 py-1 text-cyan-100">
            Investigator
          </span>
          <span className="rounded border border-emerald-400/40 bg-emerald-500/15 px-2 py-1 text-emerald-100">
            Federation TEE
          </span>
          <span className="rounded border border-amber-300/50 bg-amber-500/15 px-2 py-1 text-amber-100">
            Bank silos
          </span>
        </div>
      </div>

      <div className="relative hidden min-h-[430px] overflow-hidden rounded-lg border border-slate-800/80 bg-slate-900/30 lg:block print:block">
        <div className="pointer-events-none absolute left-[1%] top-[6%] h-[55%] w-[32%] rounded-lg border border-cyan-400/45 bg-cyan-500/12 shadow-[inset_0_0_28px_rgba(34,211,238,0.08)]" />
        <div className="pointer-events-none absolute left-[37%] top-[6%] h-[55%] w-[20%] rounded-lg border border-emerald-400/45 bg-emerald-500/12 shadow-[inset_0_0_28px_rgba(52,211,153,0.08)]" />
        <div className="pointer-events-none absolute bottom-[4%] left-[1%] h-[32%] w-[56%] rounded-lg border border-amber-300/55 bg-amber-500/12 shadow-[inset_0_0_28px_rgba(245,158,11,0.08)]" />
        <div className="pointer-events-none absolute right-[1%] top-[6%] h-[88%] w-[36%] rounded-lg border border-violet-400/45 bg-violet-500/12 shadow-[inset_0_0_28px_rgba(167,139,250,0.08)]" />
        <svg
          className="absolute inset-0 h-full w-full"
          fill="none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-label="Clickable demo flow edges"
        >
          <defs>
            <marker
              id="demo-flow-arrow"
              markerHeight="4"
              markerWidth="5"
              orient="auto"
              refX="4"
              refY="2"
            >
              <path d="M0,0 L5,2 L0,4 Z" fill="currentColor" />
            </marker>
          </defs>
          {graphEdges.map((edge) => {
            const targetStage = FLOW_STAGES.find((stage) => stage.id === edge.to);
            const targetStatus = targetStage ? stageStatus(events, targetStage) : "pending";
            const active = targetStage ? Boolean(latestStageEvent(events, targetStage)) : false;
            return (
              <FlowEdgePath
                key={edge.id}
                edge={edge}
                active={active}
                selected={edge.id === selectedEdgeId}
                status={targetStatus}
                onSelect={() => onSelectEdge(edge.id)}
              />
            );
          })}
        </svg>
        <div className="pointer-events-none absolute left-[2%] top-2 text-[10px] font-semibold uppercase tracking-wide text-cyan-100">
          Investigating bank control
        </div>
        <div className="pointer-events-none absolute left-[38%] top-2 text-[10px] font-semibold uppercase tracking-wide text-emerald-100">
          F1 coordination layer
        </div>
        <div className="pointer-events-none absolute bottom-[35%] left-[2%] text-[10px] font-semibold uppercase tracking-wide text-amber-100">
          Sensitive bank data boundaries
        </div>
        <div className="pointer-events-none absolute right-[2%] top-2 text-[10px] font-semibold uppercase tracking-wide text-violet-100">
          Federation specialists
        </div>
        {graphEdges.map((edge) => (
          <button
            key={`hotspot-${edge.id}`}
            type="button"
            onClick={() => onSelectEdge(edge.id)}
            className={`absolute z-10 inline-flex h-4 w-4 items-center justify-center rounded-full border text-[9px] font-semibold shadow-sm transition ${
              edge.id === selectedEdgeId
                ? "border-sky-300 bg-sky-400 text-slate-950"
                : "border-slate-600 bg-slate-950/80 text-slate-300 hover:border-sky-300 hover:text-sky-100"
            } ${edge.hotspotClass}`}
            aria-label={`Select edge ${edge.label}`}
            title={edge.label}
          >
            i
          </button>
        ))}
        {FLOW_STAGES.map((stage, index) => {
          const status = stageStatus(events, stage);
          const event = latestStageEvent(events, stage);
          const selected = stage.id === selectedStageId;
          const active = index <= currentStageIndex && Boolean(event);
          const displayStatus = status === "simulated" ? status : active ? status : "pending";
          return (
            <FlowNode
              key={stage.id}
              stage={stage}
              status={displayStatus}
              selected={selected}
              onSelect={() => onSelectStage(stage.id)}
            />
          );
        })}
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:hidden print:hidden">
        {FLOW_STAGES.map((stage, index) => {
          const status = stageStatus(events, stage);
          const event = latestStageEvent(events, stage);
          const selected = stage.id === selectedStageId;
          const active = index <= currentStageIndex && Boolean(event);
          const displayStatus = status === "simulated" ? status : active ? status : "pending";
          return (
            <FlowNode
              key={stage.id}
              stage={stage}
              status={displayStatus}
              selected={selected}
              onSelect={() => onSelectStage(stage.id)}
            />
          );
        })}
      </div>
      <div className="mt-2 grid gap-1.5 sm:grid-cols-2 lg:hidden print:hidden">
        {graphEdges.map((edge) => (
          <button
            key={edge.id}
            type="button"
            onClick={() => onSelectEdge(edge.id)}
            className={`rounded border px-2 py-1.5 text-left text-[11px] ${
              edge.id === selectedEdgeId
                ? "border-sky-400/70 bg-sky-500/15 text-sky-100"
                : "border-slate-800 bg-slate-900/60 text-slate-300"
            }`}
          >
            {edge.label}
          </button>
        ))}
      </div>
      {children ? (
        <div className="mt-2 border-t border-slate-800/70 pt-2">
          {children}
        </div>
      ) : null}
    </section>
  );
}

function FlowEdgePath({
  edge,
  active,
  selected,
  status,
  onSelect,
}: {
  edge: FlowEdge;
  active: boolean;
  selected: boolean;
  status: SnapshotStatus;
  onSelect: () => void;
}) {
  const strokeClass = selected
    ? "text-sky-300"
    : active && status === "live"
      ? "text-emerald-300/80"
      : active && (status === "blocked" || status === "error")
        ? "text-rose-300/80"
        : "text-slate-600";

  return (
    <g
      className={`cursor-pointer outline-none transition ${strokeClass}`}
      aria-hidden
      onClick={onSelect}
    >
      <title>{edge.label}</title>
      <path
        d={edge.path}
        stroke="currentColor"
        strokeWidth={selected ? "0.55" : "0.35"}
        markerEnd="url(#demo-flow-arrow)"
      />
      <path
        d={edge.path}
        stroke="transparent"
        strokeWidth="3.2"
        pointerEvents="stroke"
      />
    </g>
  );
}

function FlowNode({
  stage,
  status,
  selected,
  onSelect,
}: {
  stage: FlowStage;
  status: SnapshotStatus;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`min-h-[74px] rounded-lg border p-2 text-left transition lg:absolute ${stage.graphClass} ${stageTone(status, selected)}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-300">
          {stage.label}
        </span>
        {stage.id === "A3_ALPHA" && status === "simulated" ? (
          <StatusPill status="simulated" label="not used" />
        ) : (
          <StatusPill status={status} />
        )}
      </div>
      <p className="mt-1 text-[11px] leading-snug text-slate-400">{graphCaption(stage)}</p>
    </button>
  );
}

function EdgeDrawer({
  edge,
  onClose,
}: {
  edge: FlowEdge | null;
  onClose: () => void;
}) {
  const source = edge ? FLOW_STAGES.find((stage) => stage.id === edge.from) : null;
  const target = edge ? FLOW_STAGES.find((stage) => stage.id === edge.to) : null;
  const rows: KeyValueRow[] = edge
    ? [
        {
          label: "Connects",
          value: `${source?.label ?? edge.from} to ${target?.label ?? edge.to}`,
        },
        {
          label: "How they connect",
          value: edge.connects,
        },
        {
          label: "Correct output",
          value: edge.correctOutput,
        },
        {
          label: "Data protection",
          value: edge.protection,
        },
        {
          label: "Warning sign",
          value: edge.risk,
          tone: "danger",
        },
      ]
    : [];

  return (
    <Dialog.Root open={Boolean(edge)} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/70" />
        <Dialog.Content
          data-inspector-drawer
          className="fixed right-0 top-0 z-50 flex h-full w-full max-w-xl flex-col border-l border-slate-800 bg-slate-950 shadow-2xl"
        >
          <div className="flex items-center justify-between gap-3 border-b border-slate-800 px-3 py-2">
            <div className="min-w-0">
              <Dialog.Title className="truncate text-sm font-semibold text-slate-100">
                {edge?.label ?? "Flow edge"}
              </Dialog.Title>
              <Dialog.Description className="truncate text-[11px] uppercase tracking-wide text-slate-500">
                Message contract between nodes
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="rounded border border-slate-800 p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
              aria-label="Close edge drawer"
            >
              <X size={14} aria-hidden />
            </Dialog.Close>
          </div>
          <div className="flex-1 space-y-3 overflow-y-auto p-3 scrollbar-thin">
            <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-300">
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <StatusPill label={source?.label ?? "source"} />
                <span className="text-slate-600">to</span>
                <StatusPill label={target?.label ?? "target"} />
              </div>
              <p>
                This drawer explains the edge itself: what moves across the connection,
                what a correct handoff looks like, and which privacy or security controls
                protect that data.
              </p>
            </section>
            <KeyValueGrid rows={rows} />
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function UnifiedInteractionCard({
  componentError,
  componentFields,
  componentRaw,
  componentStatus,
  edge,
  event,
  onOpenEdgeDrawer,
  onOpenInspector,
  scenario,
  stage,
}: {
  componentError: unknown;
  componentFields: KeyValueRow[];
  componentRaw: unknown;
  componentStatus: SnapshotStatus;
  edge: FlowEdge | null;
  event?: TimelineEventSnapshot;
  onOpenEdgeDrawer: () => void;
  onOpenInspector: () => void;
  scenario: ScenarioConfig;
  stage: FlowStage;
}) {
  if (edge) {
    const source = FLOW_STAGES.find((item) => item.id === edge.from);
    const target = FLOW_STAGES.find((item) => item.id === edge.to);
    const probeKinds = probeKindsForEdge(edge);
    const rows: KeyValueRow[] = [
      {
        label: "Connects",
        value: `${source?.label ?? edge.from} to ${target?.label ?? edge.to}`,
      },
      { label: "Correct output", value: edge.correctOutput },
      { label: "Data protection", value: edge.protection },
      { label: "Warning sign", value: edge.risk, tone: "danger" },
    ];

    return (
      <section className="rounded-lg border border-slate-800 bg-slate-900/40">
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800/70 px-3 py-2">
          <div className="min-w-0">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
              Selected edge: {edge.label}
            </h2>
            <p className="mt-1 text-[11px] leading-5 text-slate-400">
              Select any node or edge in the graph to update this card. For this edge,
              review the handoff, run relevant attacks, or open full details with Info.
            </p>
          </div>
          <button
            type="button"
            onClick={onOpenEdgeDrawer}
            className="inline-flex items-center gap-1.5 rounded border border-sky-400/50 bg-sky-500/10 px-2.5 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-500/20"
          >
            <Info size={13} aria-hidden />
            Info
          </button>
        </header>
        <div className="grid gap-2 p-3 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.9fr)]">
          <KeyValueGrid rows={rows} />
          {probeKinds.length ? (
            <AttackLabSelectorCard
              description="Run the attacks that are meaningful for this message handoff."
              probeKinds={probeKinds}
              title="Attack this edge"
            />
          ) : (
            <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400">
              No direct probe is mapped to this edge yet. Use the node cards for live subsystem tests.
            </section>
          )}
        </div>
      </section>
    );
  }

  const probeKinds = probeKindsForStage(stage);

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-900/40">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800/70 px-3 py-2">
        <div className="min-w-0">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Selected node: {stage.label}
          </h2>
          <p className="mt-1 text-[11px] leading-5 text-slate-400">
            {stage.summary}
          </p>
          <p className="mt-1 text-[11px] leading-5 text-slate-500">
            Select any node or edge in the graph to update this card. For this node,
            inspect state, run valid attacks, or open full details with Info.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusPill status={componentStatus} label={stage.domain} />
          <button
            type="button"
            onClick={onOpenInspector}
            className="inline-flex items-center gap-1.5 rounded border border-sky-400/50 bg-sky-500/10 px-2.5 py-1.5 text-xs font-medium text-sky-100 hover:bg-sky-500/20"
          >
            <Info size={13} aria-hidden />
            Info
          </button>
        </div>
      </header>
      <div className="grid gap-2 p-3 xl:grid-cols-[minmax(0,1fr)_minmax(23rem,0.9fr)]">
        <div className="space-y-2">
          <StageExplainer
            stage={stage}
            scenario={scenario}
            event={event}
          />
          <InspectPanel
            stage={stage}
            componentStatus={componentStatus}
            rows={componentFields}
            raw={componentRaw}
            error={componentError}
          />
        </div>
        <div className="space-y-2">
          {probeKinds.length ? (
            <AttackLabSelectorCard
              description="Run the attacks that are meaningful for this selected node."
              probeKinds={probeKinds}
              title="Attack this node"
            />
          ) : (
            <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400">
              No direct attack probe is mapped to this node. Continue the story or select a security boundary.
            </section>
          )}
        </div>
      </div>
    </section>
  );
}

function StageExplainer({
  stage,
  scenario,
  event,
}: {
  stage: FlowStage;
  scenario: ScenarioConfig;
  event?: TimelineEventSnapshot;
}) {
  const rows = [
    { label: "Active node", value: stage.activeNode },
    { label: "Communicates with", value: stage.communicatesWith },
    { label: "Output", value: stage.outputDetail },
    { label: "Why it matters", value: stage.whyItMatters },
  ];
  const routeNote = modelRouteNote(stage);
  if (routeNote) {
    rows.push({ label: "Model route", value: routeNote });
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex flex-wrap items-start justify-between gap-2 border-b border-slate-800/70 px-3 py-2">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Step guide
          </h2>
          <p className="text-[11px] text-slate-500">
            What is happening in the {scenario.amlPattern} scenario.
          </p>
        </div>
        <StatusPill status={event ? event.status : "pending"} label={stage.label} />
      </header>
      <div className="space-y-2 p-3 text-xs">
        <p className="rounded border border-slate-800 bg-slate-900/50 p-2 text-slate-300">
          {stage.summary}
        </p>
        <div className="grid gap-2 md:grid-cols-2 2xl:grid-cols-4 print:grid-cols-2">
          {rows.map((row) => (
            <div
              key={row.label}
              className="min-w-0 rounded border border-slate-800 bg-slate-900/50 p-2"
            >
              <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                {row.label}
              </div>
              <p className="mt-1 text-slate-200">{row.value}</p>
            </div>
          ))}
        </div>
        <div className="rounded border border-slate-800 bg-slate-900/50 p-2">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Current event
          </div>
          <p className="mt-1 text-slate-300">
            {event ? event.detail : `Waiting for ${stage.label} to run.`}
          </p>
        </div>
      </div>
    </section>
  );
}

function InspectPanel({
  stage,
  componentStatus,
  rows,
  raw,
  error,
}: {
  stage: FlowStage;
  componentStatus: SnapshotStatus;
  rows: KeyValueRow[];
  raw: unknown;
  error: unknown;
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-slate-950">
      <header className="flex items-center justify-between gap-2 border-b border-slate-800/70 px-3 py-2">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-200">
            Inspect selected stage
          </h2>
          <p className="text-[11px] text-slate-500">{stage.domain}</p>
        </div>
        <StatusPill status={componentStatus} />
      </header>
      <div className="space-y-3 p-3 text-xs">
        <div className="rounded border border-slate-800 bg-slate-900/50 p-3">
          <div className="flex items-start gap-2">
            <Network size={15} className="mt-0.5 shrink-0 text-sky-300" aria-hidden />
            <div>
              <div className="font-semibold text-slate-100">{stage.label}</div>
              <p className="mt-1 text-slate-300">{stage.summary}</p>
            </div>
          </div>
        </div>
        <KeyValueGrid
          rows={rows.length ? rows : [{ label: "State", value: "No snapshot fields loaded yet.", tone: "muted" }]}
        />
        {raw ? <RawJsonPanel value={raw} /> : null}
        {error ? <ErrorBox error={error} /> : null}
      </div>
    </section>
  );
}

function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1.5 text-[11px] text-rose-100">
      {describeError(error)}
    </div>
  );
}
