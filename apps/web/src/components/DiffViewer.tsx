"use client";

import { useState } from "react";
import { CheckCircle, AlertTriangle, FileCode, Copy, Check } from "lucide-react";

interface DiffViewerProps {
  remediation: any;
}

export function DiffViewer({ remediation }: DiffViewerProps) {
  const [copied, setCopied] = useState(false);

  if (!remediation) {
    return (
      <div className="bg-white border border-slate-200 p-8 rounded-xl text-center text-slate-500 shadow-sm">
        No SQL/dbt remediation patch artifact required for this change.
      </div>
    );
  }

  const { file_path, unified_diff, validation, remediated_sql } = remediation;
  const isPassed = validation?.is_valid;

  const handleCopy = () => {
    navigator.clipboard.writeText(unified_diff);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-5 shadow-sm">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-4">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-blue-50 text-blue-600 border border-blue-100">
            <FileCode className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-mono font-bold text-slate-900 text-sm">{file_path}</h3>
            <p className="text-xs text-slate-500">Target Downstream dbt Model Transformation</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleCopy}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono text-xs border border-slate-200 transition flex items-center gap-1.5"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
            {copied ? "Copied Diff" : "Copy Patch"}
          </button>

          <span className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold flex items-center gap-1.5 ${
            isPassed ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'
          }`}>
            {isPassed ? <CheckCircle className="w-4 h-4 text-emerald-600" /> : <AlertTriangle className="w-4 h-4 text-red-600" />}
            SQLGlot: {validation?.status}
          </span>
        </div>
      </div>

      {/* Unified Diff Box */}
      <div>
        <h4 className="text-xs font-mono font-bold text-slate-700 mb-2 flex items-center justify-between">
          <span>Validated Unified Diff (.patch):</span>
          <span className="text-[10px] text-slate-400 font-normal">Removed lines highlighted red, syntax validated</span>
        </h4>
        <pre className="bg-slate-900 border border-slate-800 p-4 rounded-xl text-xs font-mono overflow-x-auto text-slate-200 leading-relaxed shadow-inner">
          {unified_diff.split('\n').map((line: string, i: number) => {
            let lineStyle = "text-slate-300";
            if (line.startsWith('+')) lineStyle = "text-emerald-400 bg-emerald-950/50 px-1.5 py-0.5 rounded block w-full font-bold";
            else if (line.startsWith('-')) lineStyle = "text-red-400 bg-red-950/50 px-1.5 py-0.5 rounded block w-full font-bold";
            else if (line.startsWith('@')) lineStyle = "text-blue-400 font-semibold";
            return <div key={i} className={lineStyle}>{line}</div>;
          })}
        </pre>
      </div>

      {/* Remediated SQL Output */}
      <div>
        <h4 className="text-xs font-mono font-bold text-slate-700 mb-2">Remediated AST Output SQL:</h4>
        <pre className="bg-slate-50 border border-slate-200 p-4 rounded-xl text-xs font-mono text-emerald-800 overflow-x-auto">
          {remediated_sql}
        </pre>
      </div>
    </div>
  );
}
