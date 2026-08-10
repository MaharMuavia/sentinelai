"use client";

import { useEffect, useState } from "react";
import { Database, Cpu, GitPullRequest, CheckCircle2, AlertTriangle, RefreshCw, Server } from "lucide-react";
import { fetchIntegrationsStatus, IntegrationStatus } from "@/lib/api";

export default function IntegrationsPage() {
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      setStatus(await fetchIntegrationsStatus());
    } catch (error: unknown) {
      console.error(error);
      setError(error instanceof Error ? error.message : "Failed to verify integration status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    fetchIntegrationsStatus()
      .then((result) => {
        if (!cancelled) {
          setStatus(result);
          setError(null);
        }
      })
      .catch((error: unknown) => {
        console.error(error);
        if (!cancelled) setError(error instanceof Error ? error.message : "Failed to verify integration status");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-600 text-white shadow-md">
              <Database className="w-6 h-6" />
            </div>
            Integrations & Service Topology
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Explicit connectivity checks for DataHub and GitHub, with deterministic fallback status for AI reasoning.
          </p>
        </div>

        <button
          onClick={() => void loadStatus()}
          className="px-4 py-2.5 rounded-xl bg-white hover:bg-slate-50 text-slate-700 text-xs font-mono font-bold border border-slate-200 shadow-sm transition flex items-center gap-2 self-start sm:self-auto cursor-pointer"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Verify Live Status
        </button>
      </div>

      {error && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}. Confirm that the API is running and try again.
        </div>
      )}

      {loading && !status ? (
        <div className="p-12 text-center text-slate-500 font-mono">Verifying live service topology status...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* DataHub Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4 hover:shadow-md transition">
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-blue-50 text-blue-600 border border-blue-100">
                  <Database className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">{status?.datahub.name}</h3>
                  <p className="text-xs text-slate-500">Organizational Metadata System of Truth</p>
                </div>
              </div>

              <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold flex items-center gap-1 ${
                status?.datahub.connected
                  ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                  : "bg-amber-100 text-amber-800 border border-amber-200"
              }`}>
                {status?.datahub.connected ? <CheckCircle2 className="w-3 h-3" /> : <AlertTriangle className="w-3 h-3" />}
                {status?.datahub.connected ? "LIVE MCP CONNECTED" : "DATAHUB UNAVAILABLE"}
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono text-slate-600">
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Endpoint:</span>
                <span className="font-bold text-slate-900">{status?.datahub.url}</span>
              </div>
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Active Mode:</span>
                <span className="font-bold text-slate-900">{status?.datahub.mode}</span>
              </div>
            </div>
          </div>

          {/* AI Reasoning Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4 hover:shadow-md transition">
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-purple-50 text-purple-600 border border-purple-100">
                  <Cpu className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">{status?.llm.name}</h3>
                  <p className="text-xs text-slate-500">Structured Evidence Reasoning Engine</p>
                </div>
              </div>

              <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> READY
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono text-slate-600">
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Model:</span>
                <span className="font-bold text-slate-900">{status?.llm.model}</span>
              </div>
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Active Engine:</span>
                <span className="font-bold text-slate-900">{status?.llm.mode}</span>
              </div>
            </div>
          </div>

          {/* GitHub Actions Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4 hover:shadow-md transition">
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-slate-100 text-slate-800 border border-slate-200">
                  <GitPullRequest className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">{status?.github.name}</h3>
                  <p className="text-xs text-slate-500">Pre-Merge Pull Request Review Client</p>
                </div>
              </div>

              <span className={`px-2.5 py-1 rounded-full text-[10px] font-mono font-bold flex items-center gap-1 ${
                status?.github.connected
                  ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                  : "bg-slate-100 text-slate-700"
              }`}>
                {status?.github.connected ? <CheckCircle2 className="w-3 h-3" /> : <AlertTriangle className="w-3 h-3" />}
                {status?.github.connected
                  ? "API VERIFIED"
                  : status?.github.configured ? "UNVERIFIED" : "DISABLED"}
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono text-slate-600">
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Target Repository:</span>
                <span className="font-bold text-slate-900">{status?.github.repository}</span>
              </div>
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Active Mode:</span>
                <span className="font-bold text-slate-900">{status?.github.mode}</span>
              </div>
            </div>
          </div>

          {/* SQLite Storage Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4 hover:shadow-md transition">
            <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-4">
              <div className="flex items-center gap-3">
                <div className="p-3 rounded-xl bg-emerald-50 text-emerald-600 border border-emerald-100">
                  <Server className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">Local Audit Storage</h3>
                  <p className="text-xs text-slate-500">Persistent SQLite Change Control History</p>
                </div>
              </div>

              <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> ACTIVE
              </span>
            </div>

            <div className="space-y-2 text-xs font-mono text-slate-600">
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Database File:</span>
                <span className="font-bold text-slate-900">./sentinel.db</span>
              </div>
              <div className="flex justify-between p-2 bg-slate-50 rounded-lg">
                <span>Audit Table:</span>
                <span className="font-bold text-slate-900">audit_events & investigations</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
