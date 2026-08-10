"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Shield, ShieldAlert, CheckCircle, Activity, ArrowRight, GitPullRequest, Search, Sparkles } from "lucide-react";
import { fetchInvestigations, InvestigationSummary } from "@/lib/api";

export default function DashboardPage() {
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");

  useEffect(() => {
    fetchInvestigations()
      .then((data) => {
        setInvestigations(data);
        setLoadError(null);
      })
      .catch((err: unknown) => {
        console.error("Error loading investigations:", err);
        setLoadError(err instanceof Error ? err.message : "Failed to load investigations");
      })
      .finally(() => setLoading(false));
  }, []);

  const totalInv = investigations.length;
  const blockedInv = investigations.filter((i) => i.recommendation === "BLOCK").length;
  const highRiskInv = investigations.filter((i) => i.severity === "CRITICAL" || i.severity === "HIGH").length;
  const protectedAssets = investigations.reduce((acc, i) => acc + (i.confirmed_consumers_count || 0), 0);

  const filteredInvestigations = investigations.filter((inv) => {
    const matchesSearch = inv.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
                          inv.dataset_urn.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesSeverity = severityFilter === "ALL" || inv.severity === severityFilter;
    return matchesSearch && matchesSeverity;
  });

  return (
    <div className="space-y-8">
      {/* Top Banner Header */}
      <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-700 rounded-2xl p-6 sm:p-8 text-white shadow-lg flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2 max-w-2xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 text-xs font-mono font-medium backdrop-blur">
            <Sparkles className="w-3.5 h-3.5" /> Data Reliability Control Center
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight">
            Data Reliability Audit Dashboard
          </h1>
          <p className="text-blue-100 text-sm leading-relaxed">
            Autonomous pre-merge change control powered by DataHub organizational lineage & usage context.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/analyze"
            className="px-5 py-3 rounded-xl bg-white hover:bg-slate-100 text-blue-700 font-extrabold text-sm shadow-md transition flex items-center gap-2 shrink-0"
          >
            <GitPullRequest className="w-4 h-4" />
            Analyze Proposed Change
          </Link>
        </div>
      </div>

      {loadError && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {loadError}. Confirm that the Sentinel API is running, then reload this page.
        </div>
      )}

      {/* Metrics Dashboard Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm hover:shadow-md transition">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-500 uppercase tracking-wider">Total Investigations</span>
            <div className="p-2 rounded-lg bg-blue-50 text-blue-600">
              <Activity className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-slate-900 mt-3 font-mono">{loading ? "..." : totalInv}</p>
          <p className="text-xs text-slate-500 mt-1">Persistent SQLite audit logs</p>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm hover:shadow-md transition">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-500 uppercase tracking-wider">Blocked Merges</span>
            <div className="p-2 rounded-lg bg-red-50 text-red-600">
              <ShieldAlert className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-red-600 mt-3 font-mono">{loading ? "..." : blockedInv}</p>
          <p className="text-xs text-slate-500 mt-1">Unsafe schema breaks prevented</p>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm hover:shadow-md transition">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-500 uppercase tracking-wider">High / Critical Risk</span>
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
              <Shield className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-amber-600 mt-3 font-mono">{loading ? "..." : highRiskInv}</p>
          <p className="text-xs text-slate-500 mt-1">Severity &gt;= HIGH</p>
        </div>

        <div className="bg-white border border-slate-200 p-5 rounded-2xl shadow-sm hover:shadow-md transition">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono font-bold text-slate-500 uppercase tracking-wider">Assets Protected</span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <CheckCircle className="w-5 h-5" />
            </div>
          </div>
          <p className="text-3xl font-extrabold text-emerald-600 mt-3 font-mono">{loading ? "..." : protectedAssets}</p>
          <p className="text-xs text-slate-500 mt-1">Downstream models & dashboards</p>
        </div>
      </div>

      {/* Main Audit History Section */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden space-y-4">
        {/* Table Controls */}
        <div className="p-5 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="font-bold text-slate-900 text-lg">Change Control Audit History</h2>
            <p className="text-xs text-slate-500">Every investigation records verified evidence, risk score, and writeback status</p>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Search */}
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input
                type="text"
                aria-label="Search investigations by URN or ID"
                placeholder="Search URN or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono focus:outline-none focus:border-blue-500 w-48"
              />
            </div>

            {/* Severity Filter */}
            <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-mono">
              {["ALL", "CRITICAL", "HIGH", "LOW"].map((sev) => (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  className={`px-2.5 py-1 rounded-lg transition font-semibold ${
                    severityFilter === sev
                      ? "bg-white text-blue-600 shadow-xs"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {sev}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Table Content */}
        {loading ? (
          <div className="p-12 text-center text-slate-500 font-mono">Loading audit logs...</div>
        ) : filteredInvestigations.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Shield className="w-12 h-12 text-slate-300 mx-auto" />
            <p className="text-slate-700 font-bold text-base">No matching investigations found</p>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              Run an investigation on a dataset or PR to populate Sentinel pre-merge audit history.
            </p>
            <Link
              href="/analyze"
              className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-600 text-white text-xs font-bold shadow-md hover:bg-blue-700 transition mt-2"
            >
              Analyze Proposed Change
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-700">
              <thead className="bg-slate-50 text-xs font-mono text-slate-500 uppercase border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3.5">ID / Dataset URN</th>
                  <th className="px-6 py-3.5">Severity</th>
                  <th className="px-6 py-3.5">Decision</th>
                  <th className="px-6 py-3.5">Evidence Score</th>
                  <th className="px-6 py-3.5">Affected Consumers</th>
                  <th className="px-6 py-3.5">DataHub Writeback</th>
                  <th className="px-6 py-3.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredInvestigations.map((inv) => (
                  <tr key={inv.id} className="hover:bg-slate-50/80 transition group">
                    <td className="px-6 py-4 font-mono text-xs">
                      <div className="font-bold text-slate-900 flex items-center gap-2">
                        {inv.id}
                        {inv.pr_url && (
                          <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded border border-blue-200">
                            PR #42
                          </span>
                        )}
                      </div>
                      <div className="text-slate-500 truncate max-w-xs pt-0.5">{inv.dataset_urn}</div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-2.5 py-1 rounded-full text-xs font-mono font-bold ${
                        inv.severity === 'CRITICAL' ? 'bg-red-100 text-red-800 border border-red-200' :
                        inv.severity === 'HIGH' ? 'bg-amber-100 text-amber-800 border border-amber-200' : 'bg-slate-100 text-slate-700'
                      }`}>
                        {inv.severity}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono font-bold text-xs">
                      <span className={inv.recommendation === 'BLOCK' ? 'text-red-600' : 'text-emerald-600'}>
                        {inv.recommendation}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-emerald-700 font-bold">
                      {inv.evidence_completeness}%
                    </td>
                    <td className="px-6 py-4 text-xs font-mono">
                      <span className="font-bold text-slate-900">{inv.confirmed_consumers_count}</span> confirmed
                    </td>
                    <td className="px-6 py-4 text-xs font-mono">
                      <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                        {inv.datahub_writeback_status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <Link
                        href={`/investigations/${inv.id}`}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-50 hover:bg-blue-100 text-blue-700 text-xs font-semibold border border-blue-200 transition"
                      >
                        View Hero Detail <ArrowRight className="w-3.5 h-3.5" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
