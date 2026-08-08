"use client";

import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls, Node, Edge, MarkerType } from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import { ShieldAlert, Database, BarChart3, Cpu, AlertTriangle, CheckCircle } from 'lucide-react';

interface ImpactGraphProps {
  graphData: {
    nodes: Array<{
      id: string;
      label: string;
      type: string;
      platform: string;
      classification: string;
      owners: string[];
      tags: string[];
    }>;
    edges: Array<{
      source: string;
      target: string;
      lineage_type: string;
      field_mapping?: string;
      hop_count: number;
    }>;
  };
}

export function ImpactGraph({ graphData }: ImpactGraphProps) {
  const { nodes, edges } = useMemo(() => {
    if (!graphData || !graphData.nodes) return { nodes: [], edges: [] };

    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: 'LR', nodesep: 80, ranksep: 250, marginx: 40, marginy: 40 });

    graphData.nodes.forEach((n) => {
      dagreGraph.setNode(n.id, { width: 280, height: 110 });
    });

    (graphData.edges || []).forEach((e) => {
      dagreGraph.setEdge(e.source, e.target);
    });

    dagre.layout(dagreGraph);

    const flowNodes: Node[] = graphData.nodes.map((n) => {
      const isRoot = n.type === 'CHANGED_DATASET';
      const isConfirmed = n.classification === 'CONFIRMED_IMPACT';
      const isUnaffected = n.classification === 'UNLIKELY_IMPACT';
      const isML = n.platform === 'mlflow' || n.label.includes('model');
      const isDashboard = n.platform === 'looker' || n.label.includes('dashboard');
      const nodeWithPosition = dagreGraph.node(n.id);

      return {
        id: n.id,
        position: { x: nodeWithPosition.x - 140, y: nodeWithPosition.y - 55 },
        data: {
          label: (
            <div className={`p-3.5 rounded-xl border text-left shadow-sm w-60 bg-white transition hover:shadow-md ${
              isRoot ? 'border-amber-400 ring-2 ring-amber-400/20' :
              isConfirmed ? 'border-red-400 ring-2 ring-red-400/20' :
              isUnaffected ? 'border-slate-200 opacity-60' :
              'border-yellow-400'
            }`}>
              <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-2">
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-slate-100 uppercase tracking-wider text-slate-700">
                  {n.platform}
                </span>
                <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded-full flex items-center gap-1 ${
                  isRoot ? 'bg-amber-100 text-amber-800' :
                  isConfirmed ? 'bg-red-100 text-red-800' :
                  isUnaffected ? 'bg-emerald-100 text-emerald-800' : 'bg-yellow-100 text-yellow-800'
                }`}>
                  {isRoot && <AlertTriangle className="w-3 h-3 text-amber-600" />}
                  {isConfirmed && <ShieldAlert className="w-3 h-3 text-red-600" />}
                  {isUnaffected && <CheckCircle className="w-3 h-3 text-emerald-600" />}
                  {n.classification}
                </span>
              </div>
              <div className="font-bold text-xs text-slate-900 truncate flex items-center gap-2">
                {isDashboard && <BarChart3 className="w-4 h-4 text-blue-600 shrink-0" />}
                {isML && <Cpu className="w-4 h-4 text-purple-600 shrink-0" />}
                {!isDashboard && !isML && <Database className="w-4 h-4 text-slate-500 shrink-0" />}
                {n.label}
              </div>
              {n.owners && n.owners.length > 0 && (
                <div className="text-[11px] text-slate-500 mt-2 truncate pt-1 border-t border-slate-100 flex items-center justify-between">
                  <span>Owner: <strong className="text-slate-700">{n.owners[0]}</strong></span>
                </div>
              )}
            </div>
          )
        },
        style: { background: 'transparent', border: 'none', padding: 0 }
      };
    });

    const flowEdges: Edge[] = (graphData.edges || []).map((e, idx) => ({
      id: `edge-${idx}`,
      source: e.source,
      target: e.target,
      animated: e.lineage_type === 'FIELD_LEVEL',
      style: {
        stroke: e.lineage_type === 'FIELD_LEVEL' ? '#dc2626' : '#94a3b8',
        strokeWidth: e.lineage_type === 'FIELD_LEVEL' ? 2.5 : 1.5
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: e.lineage_type === 'FIELD_LEVEL' ? '#dc2626' : '#94a3b8'
      }
    }));

    return { nodes: flowNodes, edges: flowEdges };
  }, [graphData]);

  return (
    <div className="w-full h-96 bg-slate-50 border border-slate-200 rounded-xl overflow-hidden relative shadow-inner">
      <div className="absolute top-3 left-3 z-10 bg-white/90 backdrop-blur border border-slate-200 px-3 py-2 rounded-lg text-xs font-mono flex items-center gap-4 text-slate-700 shadow-sm">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span> Changed Dataset</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-500"></span> Confirmed Impact</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-yellow-500"></span> Potential</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-slate-400"></span> Unaffected</span>
      </div>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background color="#cbd5e1" gap={18} />
        <Controls className="bg-white border-slate-200 text-slate-700 shadow-sm" />
      </ReactFlow>
    </div>
  );
}
