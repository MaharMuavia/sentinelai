"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { GitPullRequest, Play, CheckCircle2, Loader2, Sparkles, AlertTriangle, Code } from "lucide-react";

interface WorkflowStreamPayload {
  type?: string;
  stage?: string;
  message?: string;
  data?: { investigation_id?: string };
}

const WORKFLOW_STAGES = [
  { id: "RECEIVE_CHANGE", label: "Receive Change Payload", desc: "Ingest proposed schema diff" },
  { id: "NORMALIZE_CHANGE", label: "Normalize Schema Diff", desc: "Parse breaking vs non-breaking changes" },
  { id: "LOAD_DATAHUB_CONTEXT", label: "Load DataHub Context", desc: "Fetch entity schema, owners & tags" },
  { id: "BUILD_EVIDENCE_GRAPH", label: "Build Evidence Graph", desc: "Trace fine-grained column lineage" },
  { id: "VERIFY_CONSUMERS", label: "Verify Consumers", desc: "Inspect query logs & field maps" },
  { id: "COMPUTE_RISK", label: "Compute Risk & Completeness", desc: "Apply transparent rule policy" },
  { id: "GENERATE_EXPLANATION", label: "Generate AI Reasoning", desc: "Formulate evidence-grounded decision" },
  { id: "GENERATE_REMEDIATION", label: "Generate SQLGlot Patch", desc: "Transform downstream dbt model AST" },
  { id: "VALIDATE_REMEDIATION", label: "Validate Patch Syntax", desc: "Ensure zero deleted column references" },
  { id: "HUMAN_APPROVAL", label: "Check Safety Policy", desc: "Verify read & safe-write permissions" },
  { id: "ACT", label: "Prepare GitHub Review", desc: "Format PR review comment & diff" },
  { id: "WRITE_BACK", label: "Writeback to DataHub", desc: "Persist Sentinel investigation aspect" },
  { id: "COMPLETE", label: "Complete Investigation", desc: "Save local SQLite audit trail" }
];

const PRESETS = {
  COLUMN_REMOVED: {
    before: {
      dataset: { urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name: "raw_customers", platform: "snowflake", env: "PROD" },
      fields: [
        { name: "customer_id", type: "STRING", nullable: false, description: "Unique customer key" },
        { name: "email", type: "STRING", nullable: true, description: "Customer email address" },
        { name: "country", type: "STRING", nullable: true, description: "ISO country code" },
        { name: "created_at", type: "TIMESTAMP", nullable: false, description: "Account creation timestamp" }
      ]
    },
    after: {
      dataset: { urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name: "raw_customers", platform: "snowflake", env: "PROD" },
      fields: [
        { name: "customer_id", type: "STRING", nullable: false, description: "Unique customer key" },
        { name: "country", type: "STRING", nullable: true, description: "ISO country code" },
        { name: "created_at", type: "TIMESTAMP", nullable: false, description: "Account creation timestamp" }
      ]
    }
  },
  TYPE_CHANGED: {
    before: {
      dataset: { urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name: "raw_customers", platform: "snowflake", env: "PROD" },
      fields: [
        { name: "customer_id", type: "STRING", nullable: false },
        { name: "email", type: "STRING", nullable: true }
      ]
    },
    after: {
      dataset: { urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name: "raw_customers", platform: "snowflake", env: "PROD" },
      fields: [
        { name: "customer_id", type: "BIGINT", nullable: false },
        { name: "email", type: "STRING", nullable: true }
      ]
    }
  },
  SAFE_ADDITIVE: {
    before: {
      dataset: { urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name: "raw_customers", platform: "snowflake", env: "PROD" },
      fields: [
        { name: "customer_id", type: "STRING", nullable: false },
        { name: "email", type: "STRING", nullable: true }
      ]
    },
    after: {
      dataset: { urn: "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name: "raw_customers", platform: "snowflake", env: "PROD" },
      fields: [
        { name: "customer_id", type: "STRING", nullable: false },
        { name: "email", type: "STRING", nullable: true },
        { name: "signup_source", type: "STRING", nullable: true, description: "Acquisition channel" }
      ]
    }
  }
};

export default function AnalyzePage() {
  const router = useRouter();
  const [beforeJson, setBeforeJson] = useState(JSON.stringify(PRESETS.COLUMN_REMOVED.before, null, 2));
  const [afterJson, setAfterJson] = useState(JSON.stringify(PRESETS.COLUMN_REMOVED.after, null, 2));
  const [prUrl, setPrUrl] = useState("");
  
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStageIdx, setCurrentStageIdx] = useState<number>(-1);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const applyPreset = (key: keyof typeof PRESETS) => {
    setBeforeJson(JSON.stringify(PRESETS[key].before, null, 2));
    setAfterJson(JSON.stringify(PRESETS[key].after, null, 2));
    setErrorMsg(null);
  };

  const handleRunAnalysis = async () => {
    setIsAnalyzing(true);
    setErrorMsg(null);
    setCurrentStageIdx(0);
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 120_000);

    try {
      const before = JSON.parse(beforeJson);
      const after = JSON.parse(afterJson);

      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE}/api/changes/analyze/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          before_schema: before,
          after_schema: after,
          pr_url: prUrl
        })
      });

      if (!response.ok) throw new Error('Failed to start analysis');
      if (!response.body) throw new Error('No stream body');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let investigationId = '';
      let streamError = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6)) as WorkflowStreamPayload;
              if (payload.type === 'RESULT') {
                investigationId = payload.data?.investigation_id ?? '';
                setCurrentStageIdx(WORKFLOW_STAGES.length - 1);
              } else if (payload.type === 'ERROR') {
                streamError = payload.message || 'Investigation failed before completion';
              } else if (payload.stage) {
                const stageIdx = WORKFLOW_STAGES.findIndex(s => s.id === payload.stage);
                if (stageIdx >= 0) setCurrentStageIdx(stageIdx);
              }
            } catch (error: unknown) {
              console.warn("Ignored malformed workflow event", error);
            }
          }
        }
      }

      if (streamError) throw new Error(streamError);
      if (!investigationId) throw new Error('Analysis stream ended without an investigation result.');
      router.push(`/investigations/${investigationId}`);
    } catch (err: unknown) {
      console.error(err);
      const message = err instanceof Error && err.name === 'AbortError'
        ? 'Analysis timed out after 120 seconds.'
        : err instanceof Error ? err.message : 'Failed to analyze change payload.';
      setErrorMsg(message);
    } finally {
      window.clearTimeout(timeoutId);
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-600 text-white shadow-md">
              <GitPullRequest className="w-6 h-6" />
            </div>
            Analyze Proposed Schema Change
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Predict downstream data breaks before PR merge using DataHub organizational context.
          </p>
        </div>
      </div>

      {/* Preset Preset Controls */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-slate-700 uppercase tracking-wider flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-blue-600" /> Load Preset Change Scenario
          </span>
          <span className="text-xs text-slate-400">Click to auto-fill before/after schemas</span>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <button
            onClick={() => applyPreset("COLUMN_REMOVED")}
            className="px-4 py-2.5 rounded-xl bg-red-50 hover:bg-red-100 text-red-700 text-xs font-mono font-bold border border-red-200 transition flex items-center gap-2"
          >
            <AlertTriangle className="w-4 h-4 text-red-600" />
            COLUMN_REMOVED (customers.email)
          </button>

          <button
            onClick={() => applyPreset("TYPE_CHANGED")}
            className="px-4 py-2.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-mono font-bold border border-amber-200 transition flex items-center gap-2"
          >
            TYPE_CHANGED (STRING → BIGINT)
          </button>

          <button
            onClick={() => applyPreset("SAFE_ADDITIVE")}
            className="px-4 py-2.5 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-800 text-xs font-mono font-bold border border-emerald-200 transition flex items-center gap-2"
          >
            COLUMN_ADDED (signup_source)
          </button>
        </div>
      </div>

      {/* PR URL Input */}
      <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-2">
        <label htmlFor="pr-url" className="block text-xs font-mono font-bold text-slate-700 uppercase">
          GitHub Pull Request URL (Optional)
        </label>
        <input
          id="pr-url"
          type="url"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
                placeholder="https://github.com/owner/repository/pull/123"
          className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-3 text-xs font-mono text-slate-900 focus:outline-none focus:border-blue-500"
        />
      </div>

      {/* Before & After JSON schema inputs */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <label htmlFor="before-schema" className="text-xs font-mono font-bold text-blue-700 uppercase flex items-center gap-1.5">
              <Code className="w-4 h-4 text-blue-600" /> Current Schema (Before)
            </label>
            <span className="text-[11px] font-mono text-slate-400">JSON Payload</span>
          </div>
          <textarea
            id="before-schema"
            spellCheck={false}
            rows={12}
            value={beforeJson}
            onChange={(e) => setBeforeJson(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-blue-500 leading-relaxed shadow-inner"
          />
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <label htmlFor="after-schema" className="text-xs font-mono font-bold text-amber-700 uppercase flex items-center gap-1.5">
              <Code className="w-4 h-4 text-amber-600" /> Proposed Schema (After)
            </label>
            <span className="text-[11px] font-mono text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
              PROPOSED MODIFICATION
            </span>
          </div>
          <textarea
            id="after-schema"
            spellCheck={false}
            rows={12}
            value={afterJson}
            onChange={(e) => setAfterJson(e.target.value)}
            className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-amber-500 leading-relaxed shadow-inner"
          />
        </div>
      </div>

      {errorMsg && (
        <div role="alert" className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 text-sm flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 shrink-0" />
          {errorMsg}
        </div>
      )}

      {/* Live 13-Stage Workflow Tracker */}
      {isAnalyzing && (
        <div aria-live="polite" className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                <Loader2 className="w-5 h-5 text-blue-600 animate-spin" />
                Sentinel Autonomous Workflow Active
              </h3>
              <p className="text-xs text-slate-500">13-stage bounded state machine evaluating proposed change</p>
            </div>
            <span className="text-xs font-mono font-bold text-blue-700 bg-blue-50 px-3 py-1.5 rounded-lg border border-blue-200">
              Stage {currentStageIdx + 1} of {WORKFLOW_STAGES.length}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {WORKFLOW_STAGES.map((stg, idx) => {
              const isDone = idx < currentStageIdx;
              const isCurrent = idx === currentStageIdx;
              return (
                <div
                  key={stg.id}
                  className={`p-3 rounded-xl border text-xs font-mono transition ${
                    isDone ? "bg-emerald-50 border-emerald-200 text-emerald-900" :
                    isCurrent ? "bg-blue-50 border-blue-500 text-blue-950 ring-2 ring-blue-500/20" :
                    "bg-slate-50 border-slate-200 text-slate-400 opacity-60"
                  }`}
                >
                  <div className="flex items-center gap-2 font-bold mb-1">
                    {isDone ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                    ) : isCurrent ? (
                      <Loader2 className="w-4 h-4 text-blue-600 animate-spin shrink-0" />
                    ) : (
                      <span className="w-4 h-4 rounded-full border border-slate-300 shrink-0 text-[10px] flex items-center justify-center text-slate-500">
                        {idx + 1}
                      </span>
                    )}
                    <span className="truncate">{stg.label}</span>
                  </div>
                  <p className="text-[10px] text-slate-500 truncate">{stg.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Primary CTA */}
      <div className="pt-2 flex justify-end">
        <button
          onClick={handleRunAnalysis}
          disabled={isAnalyzing}
          className="w-full sm:w-auto px-10 py-4 rounded-2xl bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-extrabold text-base shadow-lg shadow-blue-600/30 transition flex items-center justify-center gap-3 cursor-pointer"
        >
          {isAnalyzing ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Running 13-Stage Investigation...
            </>
          ) : (
            <>
              <Play className="w-5 h-5 fill-current" />
              Analyze Proposed Change
            </>
          )}
        </button>
      </div>
    </div>
  );
}
