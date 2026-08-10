"use client";

import Link from "next/link";
import { 
  GitPullRequest, ArrowRight, CheckCircle2, ShieldAlert, Sparkles,
  Database, Code, Layers, FileCode
} from "lucide-react";

export default function LandingPage() {
  return (
    <div className="space-y-20 pb-12">
      {/* Hero Section */}
      <section className="relative pt-6 pb-12 text-center space-y-8 max-w-5xl mx-auto">
        {/* Announcement Pill */}
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-xs font-mono font-bold shadow-xs">
          <Sparkles className="w-3.5 h-3.5 text-blue-600" />
          Build with DataHub Hackathon 2026 • Category: Agents That Do Real Work
        </div>

        {/* Main Title */}
        <div className="space-y-4">
          <h1 className="text-4xl sm:text-6xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Know what a data change will break <br className="hidden sm:inline" />
            <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 bg-clip-text text-transparent">
              before you merge it — then fix it.
            </span>
          </h1>
          <p className="text-slate-600 text-base sm:text-lg max-w-3xl mx-auto leading-relaxed">
            Sentinel AI is an autonomous pre-merge Data Reliability Engineer powered by DataHub. 
            It investigates schema diffs, queries organizational lineage, computes evidence-backed risk, 
            generates AST-validated SQLGlot patches, and writes persistent audit records back to DataHub.
          </p>
        </div>

        {/* Action CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-2">
          <Link
            href="/analyze"
            className="w-full sm:w-auto px-8 py-4 rounded-2xl bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-base shadow-lg shadow-blue-600/30 transition flex items-center justify-center gap-2 group cursor-pointer"
          >
            <GitPullRequest className="w-5 h-5" />
            Analyze Proposed Schema Change
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition" />
          </Link>

          <Link
            href="/dashboard"
            className="w-full sm:w-auto px-8 py-4 rounded-2xl bg-white hover:bg-slate-50 text-slate-700 font-extrabold text-base border border-slate-200 shadow-sm transition flex items-center justify-center gap-2 cursor-pointer"
          >
            <Layers className="w-5 h-5 text-slate-500" />
            Open Audit Dashboard
          </Link>
        </div>

        {/* Hero Interactive Visual Showcase Card */}
        <div className="pt-8 max-w-4xl mx-auto text-left">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-xl overflow-hidden">
            {/* Window bar header */}
            <div className="bg-slate-100 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-full bg-red-400"></span>
                <span className="w-3 h-3 rounded-full bg-amber-400"></span>
                <span className="w-3 h-3 rounded-full bg-emerald-400"></span>
                <span className="text-xs font-mono text-slate-500 ml-2 font-bold">Sentinel AI Assessment #734314b3</span>
              </div>
              <span className="text-[10px] font-mono font-bold bg-blue-100 text-blue-800 px-2 py-0.5 rounded">
                PR #42: raw_customers.email removal
              </span>
            </div>

            {/* Showcase Card Content */}
            <div className="p-6 space-y-5 bg-slate-50/50">
              <div className="flex flex-wrap items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-xs">
                <div className="flex items-center gap-3">
                  <span className="px-3 py-1 rounded-full text-xs font-mono font-extrabold bg-red-100 text-red-800 border border-red-200 flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4 text-red-600" />
                    CRITICAL SEVERITY
                  </span>
                  <span className="px-3 py-1 rounded-full text-xs font-mono font-extrabold bg-red-600 text-white">
                    DECISION: BLOCK MERGE
                  </span>
                </div>
                <span className="text-xs font-mono font-bold text-amber-800 bg-amber-50 px-3 py-1 rounded-full border border-amber-200">
                  Illustrative fixture scenario - not live verified
                </span>
              </div>

              {/* Lineage Path Preview */}
              <div className="bg-white p-4 rounded-xl border border-slate-200 space-y-2 text-xs font-mono">
                <div className="text-slate-500 font-bold uppercase text-[10px] tracking-wider">Illustrative Downstream Branches</div>
                <div className="flex items-center gap-2 text-slate-800 font-bold flex-wrap">
                  <span className="px-2.5 py-1 bg-amber-100 text-amber-900 rounded border border-amber-200">raw_customers.email</span>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                  <span className="px-2.5 py-1 bg-red-100 text-red-900 rounded border border-red-200">customer_360.email</span>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                  <span className="px-2.5 py-1 bg-blue-100 text-blue-900 rounded border border-blue-200">marketing_dashboard</span>
                </div>
                <div className="flex items-center gap-2 text-slate-800 font-bold flex-wrap">
                  <span className="px-2.5 py-1 bg-amber-100 text-amber-900 rounded border border-amber-200">raw_customers.email</span>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                  <span className="px-2.5 py-1 bg-red-100 text-red-900 rounded border border-red-200">customer_360.email</span>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                  <span className="px-2.5 py-1 bg-purple-100 text-purple-900 rounded border border-purple-200">churn_model</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Capabilities Grid */}
      <section className="space-y-10">
        <div className="text-center space-y-3 max-w-2xl mx-auto">
          <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">
            Why DataHub Context + Sentinel AI?
          </h2>
          <p className="text-slate-600 text-sm">
            DataHub provides the lineage graph. Sentinel turns that context into an autonomous pre-merge change control and remediation workflow.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm hover:shadow-md transition space-y-3">
            <div className="p-3 rounded-xl bg-blue-50 text-blue-600 border border-blue-100 w-fit">
              <Code className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Deterministic Schema Diff</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Zero-hallucination deterministic comparisons for <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-blue-700">COLUMN_REMOVED</code>, <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-blue-700">TYPE_CHANGED</code>, and nullability modifications.
            </p>
          </div>

          <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm hover:shadow-md transition space-y-3">
            <div className="p-3 rounded-xl bg-indigo-50 text-indigo-600 border border-indigo-100 w-fit">
              <Database className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">DataHub Context Engine</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Queries DataHub through the official MCP tools for lineage, dataset query logs, technical owners, and tags.
            </p>
          </div>

          <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm hover:shadow-md transition space-y-3">
            <div className="p-3 rounded-xl bg-red-50 text-red-600 border border-red-100 w-fit">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Evidence-Backed Classification</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Distinguishes confirmed consumers (executive Looker dashboards, ML feature stores) from connected assets. Never classifies every node as broken.
            </p>
          </div>

          <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm hover:shadow-md transition space-y-3">
            <div className="p-3 rounded-xl bg-emerald-50 text-emerald-600 border border-emerald-100 w-fit">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">Transparent Evidence Score</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Calculates a deterministic score from individually displayed metadata signals. Missing or unavailable evidence remains missing.
            </p>
          </div>

          <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm hover:shadow-md transition space-y-3">
            <div className="p-3 rounded-xl bg-purple-50 text-purple-600 border border-purple-100 w-fit">
              <FileCode className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">SQLGlot AST Patch Generator</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Generates a validated projection-only candidate when the deleted field is safe to remove. References in <code className="font-mono bg-slate-100 px-1 py-0.5 rounded">WHERE</code>, joins, grouping, or other predicates require human review.
            </p>
          </div>

          <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm hover:shadow-md transition space-y-3">
            <div className="p-3 rounded-xl bg-amber-50 text-amber-600 border border-amber-100 w-fit">
              <Sparkles className="w-6 h-6" />
            </div>
            <h3 className="font-bold text-slate-900 text-base">DataHub Writeback Engine</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
            After authenticated approval, writes a real investigation document and Sentinel risk tag when the configured MCP mutation tools succeed.
            </p>
          </div>
        </div>
      </section>

      {/* Side-by-Side Comparison: DataHub Native vs Sentinel AI */}
      <section className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-8 shadow-sm space-y-6">
        <div className="text-center space-y-2 max-w-xl mx-auto">
          <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
            DataHub Impact Analysis vs. Sentinel AI
          </h2>
          <p className="text-xs text-slate-500">How Sentinel turns DataHub context into an actionable change control agent</p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-slate-50 text-slate-500 uppercase border-b border-slate-200">
              <tr>
                <th className="p-4">Capability</th>
                <th className="p-4">DataHub Native</th>
                <th className="p-4 bg-blue-50/60 text-blue-900 font-bold">Sentinel AI Agent</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              <tr>
                <td className="p-4 font-bold text-slate-900">Lineage & Metadata Source</td>
                <td className="p-4 text-slate-600">Provides graph & entities</td>
                <td className="p-4 bg-blue-50/30 text-blue-950 font-bold">Queries DataHub MCP tools</td>
              </tr>
              <tr>
                <td className="p-4 font-bold text-slate-900">Pre-Merge Decision Engine</td>
                <td className="p-4 text-slate-400">Manual inspection</td>
                <td className="p-4 bg-blue-50/30 text-blue-950 font-bold">Autonomous BLOCK / MERGE decision</td>
              </tr>
              <tr>
                <td className="p-4 font-bold text-slate-900">Consumer Discrimination</td>
                <td className="p-4 text-slate-600">Table-level connection</td>
                <td className="p-4 bg-blue-50/30 text-blue-950 font-bold">Verifies field lineage & query history</td>
              </tr>
              <tr>
                <td className="p-4 font-bold text-slate-900">SQL Remediation & Diff</td>
                <td className="p-4 text-slate-400">None</td>
                <td className="p-4 bg-blue-50/30 text-blue-950 font-bold">SQLGlot AST patch & unified diff</td>
              </tr>
              <tr>
                <td className="p-4 font-bold text-slate-900">Organizational Writeback</td>
                <td className="p-4 text-slate-600">Storage target</td>
                <td className="p-4 bg-blue-50/30 text-blue-950 font-bold">Ingests investigation aspects & notes</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Interactive Try Demo Call-to-Action Card */}
      <section className="bg-gradient-to-r from-blue-700 via-indigo-700 to-purple-800 rounded-3xl p-8 sm:p-12 text-white shadow-xl text-center space-y-6">
        <div className="max-w-2xl mx-auto space-y-3">
          <h2 className="text-3xl font-extrabold tracking-tight">
            Ready to test Sentinel AI on your data stack?
          </h2>
          <p className="text-blue-100 text-sm leading-relaxed">
            Launch the analysis workflow against the configured DataHub mode. Every result states whether its evidence is live MCP, an explicit fixture, or unavailable.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-2">
          <Link
            href="/analyze"
            className="px-8 py-4 rounded-2xl bg-white hover:bg-slate-100 text-blue-700 font-extrabold text-base shadow-lg transition flex items-center gap-2 cursor-pointer"
          >
            <GitPullRequest className="w-5 h-5" />
            Launch Analyze Workflow
          </Link>
          <Link
            href="/dashboard"
            className="px-8 py-4 rounded-2xl bg-blue-800/60 hover:bg-blue-800 text-white font-extrabold text-base border border-blue-400/40 backdrop-blur transition flex items-center gap-2 cursor-pointer"
          >
            <Layers className="w-5 h-5" />
            View Audit Dashboard
          </Link>
        </div>
      </section>
    </div>
  );
}
