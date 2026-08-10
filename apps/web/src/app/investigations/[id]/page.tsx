"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ShieldAlert, Database, GitPullRequest, ArrowLeft, Check, Loader2, Clock } from "lucide-react";
import Link from "next/link";
import { approveInvestigation, fetchInvestigation, fetchInvestigationEvents, triggerWriteback, triggerGitHubComment, InvestigationDetail, InvestigationEvent } from "@/lib/api";
import { ImpactGraph } from "@/components/ImpactGraph";
import { EvidenceLedger } from "@/components/EvidenceLedger";
import { DiffViewer } from "@/components/DiffViewer";

type InvestigationTab = "overview" | "graph" | "evidence" | "remediation" | "timeline";

const INVESTIGATION_TABS: Array<{ id: InvestigationTab; label: string }> = [
  { id: "overview", label: "Executive AI Summary" },
  { id: "graph", label: "Blast-Radius Lineage Graph" },
  { id: "evidence", label: "Evidence Ledger" },
  { id: "remediation", label: "SQLGlot Patch Diff" },
  { id: "timeline", label: "Audit Timeline" },
];

export default function InvestigationDetailPage() {
  const { id } = useParams() as { id: string };
  const [data, setData] = useState<InvestigationDetail | null>(null);
  const [events, setEvents] = useState<InvestigationEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<InvestigationTab>("overview");

  const [writebackLoading, setWritebackLoading] = useState(false);
  const [writebackDone, setWritebackDone] = useState(false);

  const [githubLoading, setGithubLoading] = useState(false);
  const [githubDone, setGithubDone] = useState(false);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [authToken, setAuthToken] = useState("");
  const [approvalLoading, setApprovalLoading] = useState(false);

  useEffect(() => {
    if (id) {
      Promise.all([
        fetchInvestigation(id),
        fetchInvestigationEvents(id)
      ])
        .then(([inv, evs]) => {
          setData(inv);
          setEvents(evs);
        })
        .catch((err) => console.error(err))
        .finally(() => setLoading(false));
    }
  }, [id]);

  const handleWriteback = async () => {
    setWritebackLoading(true);
    try {
      const result = await triggerWriteback(id, authToken);
      setWritebackDone(Boolean(result.success));
      setActionMessage(result.message || result.status);
    } catch (e) {
      console.error(e);
      setActionMessage(e instanceof Error ? e.message : "DataHub writeback failed");
    } finally {
      setWritebackLoading(false);
    }
  };

  const handleGitHubComment = async () => {
    setGithubLoading(true);
    try {
      const result = await triggerGitHubComment(id, authToken);
      setGithubDone(Boolean(result.success));
      setActionMessage(result.message || result.status);
    } catch (e) {
      console.error(e);
      setActionMessage(e instanceof Error ? e.message : "GitHub action failed");
    } finally {
      setGithubLoading(false);
    }
  };

  const handleApproval = async () => {
    setApprovalLoading(true);
    setActionMessage(null);
    try {
      const result = await approveInvestigation(id, authToken);
      setData((current) => current ? { ...current, approval_status: result.status } : current);
      setActionMessage(`Approval state: ${result.status}`);
    } catch (error: unknown) {
      console.error(error);
      setActionMessage(error instanceof Error ? error.message : "Approval failed");
    } finally {
      setApprovalLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono flex items-center justify-center gap-3">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
        Loading investigation audit detail...
      </div>
    );
  }

  if (!data) {
    return (
      <div className="p-12 text-center space-y-4">
        <p className="text-red-600 font-bold">Investigation record not found</p>
        <Link href="/" className="text-xs text-blue-600 hover:underline">
          Return to Overview
        </Link>
      </div>
    );
  }

  const { severity, recommendation, evidence_completeness, confirmed_consumers_count, ai_explanation, evidence_bundle, remediation, dataset_urn, approval_status } = data;
  const actionAllowed = approval_status === "APPROVED" && authToken.length > 0;
  const ownerRows = evidence_bundle.graph.nodes.flatMap((node) =>
    node.owners.map((owner) => ({ owner, asset: node.label })),
  );

  return (
    <div className="space-y-8">
      {/* Top Back Navigation */}
      <div>
        <Link href="/" className="inline-flex items-center gap-2 text-xs font-mono text-slate-500 hover:text-slate-900 transition">
          <ArrowLeft className="w-4 h-4" /> Back to Investigations Overview
        </Link>
      </div>

      {/* Hero Header Card */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 space-y-6 shadow-md relative overflow-hidden">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-3">
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="px-3 py-1 rounded-full text-xs font-mono font-extrabold bg-red-100 text-red-800 border border-red-200 flex items-center gap-1.5">
                <ShieldAlert className="w-4 h-4 text-red-600" />
                {severity} SEVERITY
              </span>

              <span className="px-3 py-1 rounded-full text-xs font-mono font-extrabold bg-red-600 text-white shadow-xs">
                DECISION: {recommendation}
              </span>

              <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                Evidence Completeness {evidence_completeness}%
              </span>
            </div>

            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight">
                Investigation Audit #{id}
              </h1>
              <p className="text-xs font-mono text-slate-500 pt-1">
                Target Dataset: <span className="text-slate-900 font-semibold">{dataset_urn}</span>
              </p>
              <p className={`text-xs font-mono font-bold ${actionAllowed ? "text-emerald-700" : "text-amber-700"}`}>
                External action state: {approval_status || "UNKNOWN"}
              </p>
            </div>
          </div>

          {/* Action Triggers */}
          <div className="flex items-center gap-3 flex-wrap max-w-xl justify-end">
            <label className="w-full text-[11px] font-mono text-slate-600">
              Operator token (kept in memory only)
              <input
                type="password"
                value={authToken}
                onChange={(event) => setAuthToken(event.target.value)}
                autoComplete="off"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900"
                placeholder="SENTINEL_AUTH_TOKEN"
              />
            </label>

            {approval_status !== "APPROVED" && (
              <button
                onClick={() => void handleApproval()}
                disabled={approvalLoading || authToken.length === 0}
                className="px-5 py-2.5 rounded-xl bg-amber-600 hover:bg-amber-700 disabled:opacity-60 text-white font-bold text-xs shadow-md transition flex items-center gap-2"
              >
                {approvalLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                Approve External Actions
              </button>
            )}

            <button
              onClick={() => void handleWriteback()}
              disabled={writebackLoading || writebackDone || !actionAllowed}
              className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-bold text-xs shadow-md transition flex items-center gap-2 cursor-pointer"
            >
              {writebackLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : writebackDone ? <Check className="w-4 h-4" /> : <Database className="w-4 h-4" />}
              {writebackDone ? "Persisted to DataHub" : actionAllowed ? "Persist to DataHub" : "Awaiting Approval"}
            </button>

            <button
              onClick={() => void handleGitHubComment()}
              disabled={githubLoading || githubDone || !actionAllowed}
              className="px-5 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white font-bold text-xs shadow-md transition flex items-center gap-2 cursor-pointer"
            >
              {githubLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : githubDone ? <Check className="w-4 h-4" /> : <GitPullRequest className="w-4 h-4" />}
              {githubDone ? "Posted Review to PR" : actionAllowed ? "Post Review to GitHub" : "Approval + Token Required"}
            </button>
          </div>
          {actionMessage && <p className="text-xs font-mono text-slate-600">{actionMessage}</p>}
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-slate-200 flex gap-2 overflow-x-auto">
        {INVESTIGATION_TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-3 text-xs font-mono font-bold border-b-2 transition whitespace-nowrap ${
              activeTab === tab.id
                ? "border-blue-600 text-blue-600 bg-blue-50/50"
                : "border-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === "overview" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-3">
              <h3 className="font-bold text-slate-900 text-base">Executive Summary</h3>
              <p className="text-sm text-slate-700 leading-relaxed font-sans">{ai_explanation?.executive_summary}</p>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-3">
              <h3 className="font-bold text-amber-800 text-base">Why It Matters & Business Impact</h3>
              <p className="text-sm text-slate-700 leading-relaxed font-sans">{ai_explanation?.why_it_matters}</p>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-3">
              <h3 className="font-bold text-blue-800 text-base">Recommended Action Plan</h3>
              <p className="text-sm text-slate-700 leading-relaxed font-sans">{ai_explanation?.recommended_action}</p>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
              <h4 className="font-bold text-slate-900 text-sm">Confirmed Affected Consumers ({confirmed_consumers_count})</h4>
              <div className="space-y-2">
                {ai_explanation?.affected_systems?.map((sys: string, i: number) => (
                  <div key={i} className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono text-slate-800 flex items-center justify-between">
                    <span className="truncate">{sys}</span>
                    <span className="text-[10px] text-red-700 font-bold px-2 py-0.5 rounded-full bg-red-100 border border-red-200">
                      CONFIRMED
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
              <h4 className="font-bold text-slate-900 text-sm">Identified Technical Owners</h4>
              <div className="space-y-2 text-xs font-mono text-slate-600">
                {ownerRows.length > 0 ? ownerRows.map(({ owner, asset }) => (
                  <div key={`${asset}-${owner}`} className="p-2.5 bg-slate-50 rounded-xl border border-slate-200">
                    <span className="text-slate-900 font-bold">{owner}</span> - {asset}
                  </div>
                )) : (
                  <p className="p-2.5 bg-slate-50 rounded-xl border border-slate-200">No verified owner metadata returned.</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === "graph" && (
        <div className="space-y-4">
          <h3 className="font-bold text-slate-900 text-lg">Interactive Blast-Radius Visualization</h3>
          <ImpactGraph graphData={evidence_bundle?.graph} />
        </div>
      )}

      {activeTab === "evidence" && (
        <EvidenceLedger evidenceBundle={evidence_bundle} riskAssessment={data.risk_assessment || { evidence_completeness }} />
      )}

      {activeTab === "remediation" && (
        <DiffViewer remediation={remediation} />
      )}

      {activeTab === "timeline" && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
          <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
            <Clock className="w-5 h-5 text-blue-600" /> Persisted Workflow Audit Log Timeline
          </h3>

          <div className="space-y-3">
            {events.map((ev, i) => (
              <div key={i} className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs font-mono">
                <div className="flex items-center gap-3">
                  <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-800 flex items-center justify-center font-bold text-[10px]">
                    {i + 1}
                  </span>
                  <div>
                    <span className="font-bold text-slate-900">{ev.stage}</span>
                    <p className="text-slate-600 pt-0.5">{ev.message}</p>
                  </div>
                </div>
                <span className="text-[10px] text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full font-bold">
                  {ev.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
