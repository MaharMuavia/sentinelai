"use client";

import { AlertCircle, CheckCircle2, Database, FileCode } from "lucide-react";
import type { ClassifiedAsset, EvidenceBundle, ImpactEvidence, RiskAssessment } from "@/lib/api";

interface EvidenceLedgerProps {
  evidenceBundle?: EvidenceBundle;
  riskAssessment?: Partial<RiskAssessment>;
}

export function EvidenceLedger({ evidenceBundle, riskAssessment }: EvidenceLedgerProps) {
  if (!evidenceBundle) return null;
  const mode = evidenceBundle.integration_mode || "DATAHUB_UNAVAILABLE";
  const trustLabel = riskAssessment?.evidence_trust || (
    mode === "LIVE_DATAHUB" ? "LIVE DATAHUB MCP" :
    mode === "DEMO_FIXTURE" ? "DEMO FIXTURE - NOT LIVE VERIFIED" : "DATAHUB UNAVAILABLE"
  );
  const signals = riskAssessment?.completeness_breakdown ?? [];
  const evidenceItems: Array<{ asset: ClassifiedAsset; evidence: ImpactEvidence }> = evidenceBundle.classified_assets.flatMap((asset) =>
    asset.evidence.map((evidence) => ({ asset, evidence }))
  ) || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between bg-slate-900 text-white p-4 rounded-xl shadow-xs">
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5 text-blue-400" />
          <div>
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300">DataHub Integration State</span>
            <div className="font-extrabold text-sm text-white">{trustLabel}</div>
          </div>
        </div>
        <span className={`text-[10px] px-2 py-1 rounded font-mono font-bold ${
          mode === "LIVE_DATAHUB" ? "bg-emerald-500/20 text-emerald-300" :
          mode === "DEMO_FIXTURE" ? "bg-amber-500/20 text-amber-300" : "bg-red-500/20 text-red-300"
        }`}>
          {mode === "LIVE_DATAHUB" ? "LIVE MCP" : mode === "DEMO_FIXTURE" ? "NOT LIVE VERIFIED" : "UNAVAILABLE"}
        </span>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-5 border-b border-slate-100 pb-4">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 className="w-5 h-5 text-blue-600" />
            <div>
              <h3 className="font-bold text-slate-900 text-base">Evidence Coverage Audit</h3>
              <p className="text-xs text-slate-500">Each signal is backed by a returned result or shown as unavailable</p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-xl font-bold font-mono text-slate-900 bg-slate-50 border border-slate-200 px-4 py-1.5 rounded-xl inline-block">
              {mode === "DEMO_FIXTURE" ? `Scenario Coverage: ${riskAssessment?.evidence_completeness ?? 0}%` : `Evidence Coverage: ${riskAssessment?.evidence_completeness ?? 0}%`}
            </span>
            <p className="text-[11px] font-mono font-semibold text-slate-500 mt-1">{trustLabel}</p>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {signals.map((signal) => (
            <div key={signal.signal_name} className="bg-slate-50 border border-slate-200 p-4 rounded-xl flex items-start gap-3.5">
              {signal.is_present ? <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0" /> : <AlertCircle className="w-5 h-5 text-slate-400 shrink-0" />}
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-slate-900">{signal.signal_name}</span>
                  <span className="text-[11px] font-mono px-2 py-0.5 rounded-full font-semibold bg-slate-200 text-slate-600">{signal.is_present ? `+${signal.weight}%` : "0%"}</span>
                </div>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">{signal.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2.5 mb-5 border-b border-slate-100 pb-4">
          <FileCode className="w-5 h-5 text-purple-600" />
          <div>
            <h3 className="font-bold text-slate-900 text-base">Provenance-Backed Evidence Ledger</h3>
            <p className="text-xs text-slate-500">Tool, URN, field, retrieval time, and verification state are shown when returned</p>
          </div>
        </div>
        <div className="space-y-3">
          {evidenceItems.map(({ asset, evidence }, index) => (
            <div key={`${asset.asset_urn}-${index}`} className="bg-slate-50 border border-slate-200 p-4 rounded-xl">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800 border border-blue-200">{evidence.type}</span>
                <span className="font-bold text-sm text-slate-900">{asset.name} ({asset.platform || "unknown"})</span>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-full bg-slate-200 text-slate-700">{asset.classification}</span>
              </div>
              <p className="text-xs font-mono text-slate-700 bg-white p-2.5 rounded-lg border border-slate-200 mt-2">{evidence.description}</p>
              {evidence.provenance && <div className="text-[10px] font-mono text-slate-500 mt-2 space-x-2">
                <span>Tool: {evidence.provenance.source_tool}</span>
                <span>Mode: {evidence.provenance.source_mode}</span>
                {evidence.provenance.entity_urn && <span>URN: {evidence.provenance.entity_urn}</span>}
                {evidence.provenance.field_path && <span>Field: {evidence.provenance.field_path}</span>}
                <span>{evidence.provenance.verified ? "VERIFIED" : "UNVERIFIED"}</span>
              </div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
