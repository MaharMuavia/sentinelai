"use client";

import { CheckCircle2, AlertCircle, Database, Search, FileCode, ShieldCheck, Tag } from "lucide-react";

interface EvidenceLedgerProps {
  evidenceBundle: any;
  riskAssessment: any;
}

export function EvidenceLedger({ evidenceBundle, riskAssessment }: EvidenceLedgerProps) {
  if (!evidenceBundle) return null;

  const mode = evidenceBundle.integration_mode || "DEMO_FIXTURE";
  const trustLabel = riskAssessment?.evidence_trust || (mode === "LIVE_DATAHUB" ? "LIVE DATAHUB MCP" : "DEMO FIXTURE — NOT LIVE VERIFIED");

  return (
    <div className="space-y-6">
      {/* Integration Mode Badge */}
      <div className="flex items-center justify-between bg-slate-900 text-white p-4 rounded-xl shadow-xs">
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5 text-blue-400" />
          <div>
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300">DataHub Integration State</span>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-extrabold text-sm text-white">{trustLabel}</span>
              {mode === "LIVE_DATAHUB" && (
                <span className="text-[10px] bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-2 py-0.5 rounded-full font-mono font-bold">
                  Verified Live Catalog
                </span>
              )}
              {mode === "DEMO_FIXTURE" && (
                <span className="text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded-full font-mono font-bold">
                  Isolated Demo Fixture Mode — NOT LIVE VERIFIED
                </span>
              )}
              {mode === "DATAHUB_UNAVAILABLE" && (
                <span className="text-[10px] bg-red-500/20 text-red-300 border border-red-500/30 px-2 py-0.5 rounded-full font-mono font-bold">
                  Unreachable (Fail-Closed Policy)
                </span>
              )}
            </div>
          </div>
        </div>

        {evidenceBundle.evidence_provenance_summary && (
          <div className="hidden sm:flex items-center gap-1.5 flex-wrap max-w-md justify-end">
            {evidenceBundle.evidence_provenance_summary.map((prov: string, idx: number) => (
              <span key={idx} className="text-[10px] font-mono bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
                {prov}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Evidence Coverage & Trust Breakdown */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center justify-between mb-5 border-b border-slate-100 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-slate-900 text-base">Evidence Coverage Audit</h3>
              <p className="text-xs text-slate-500">Deterministic verification across 5 organizational metadata signals</p>
            </div>
          </div>
          <div className="text-right">
            <span className="text-xl font-bold font-mono text-emerald-700 bg-emerald-50 border border-emerald-200 px-4 py-1.5 rounded-xl shadow-xs inline-block">
              {mode === "DEMO_FIXTURE" ? `Scenario Coverage: ${riskAssessment?.evidence_completeness}%` : `Evidence Coverage: ${riskAssessment?.evidence_completeness}%`}
            </span>
            <p className="text-[11px] font-mono font-semibold text-slate-500 mt-1">{trustLabel}</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {riskAssessment?.completeness_breakdown?.map((sig: any, idx: number) => (
            <div key={idx} className="bg-slate-50 border border-slate-200 p-4 rounded-xl flex items-start gap-3.5 hover:bg-slate-100/50 transition">
              {sig.is_present ? (
                <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-5 h-5 text-slate-400 shrink-0 mt-0.5" />
              )}
              <div className="flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs font-bold text-slate-900">{sig.signal_name}</span>
                  <span className={`text-[11px] font-mono px-2 py-0.5 rounded-full font-semibold ${
                    sig.is_present ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-200 text-slate-600'
                  }`}>
                    {sig.is_present ? `+${sig.weight}%` : '0%'}
                  </span>
                </div>
                <p className="text-xs text-slate-600 mt-1 leading-relaxed">{sig.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Verified Evidence Ledger Items */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2.5 mb-5 border-b border-slate-100 pb-4">
          <div className="p-2 rounded-lg bg-purple-50 text-purple-600 border border-purple-100">
            <FileCode className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-slate-900 text-base">Provenance-Backed Evidence Ledger</h3>
            <p className="text-xs text-slate-500">Every statement backed by explicit DataHub tool provenance, field mapping, and query logs</p>
          </div>
        </div>

        <div className="space-y-3">
          {evidenceBundle.classified_assets?.flatMap((asset: any) =>
            asset.evidence?.map((ev: any, idx: number) => (
              <div key={`${asset.asset_urn}-${idx}`} className="bg-slate-50 border border-slate-200 p-4 rounded-xl flex items-start justify-between gap-4 hover:border-slate-300 transition">
                <div className="space-y-1.5 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-blue-100 text-blue-800 border border-blue-200">
                      {ev.type}
                    </span>
                    <span className="font-bold text-sm text-slate-900">{asset.name} ({asset.platform})</span>
                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full ${
                      asset.classification === 'CONFIRMED_IMPACT' ? 'bg-red-100 text-red-800 border border-red-200' : 'bg-slate-200 text-slate-700'
                    }`}>
                      {asset.classification}
                    </span>
                  </div>

                  <p className="text-xs font-mono text-slate-700 bg-white p-2.5 rounded-lg border border-slate-200 leading-relaxed">
                    {ev.description}
                  </p>

                  {ev.provenance && (
                    <div className="flex items-center gap-2 text-[10px] font-mono text-slate-500 pt-0.5">
                      <Tag className="w-3 h-3 text-slate-400" />
                      <span>Tool: <strong className="text-slate-700">{ev.provenance.source_tool}</strong></span>
                      <span>•</span>
                      <span>Mode: <strong className="text-slate-700">{ev.provenance.source_mode}</strong></span>
                    </div>
                  )}
                </div>
                <span className="text-[11px] font-mono text-slate-500 bg-slate-200 px-2 py-1 rounded shrink-0">
                  Hop Depth: {asset.hop_count}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
