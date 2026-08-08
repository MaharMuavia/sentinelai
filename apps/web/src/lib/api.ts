export interface IntegrationStatus {
  datahub: { name: string; url: string; connected: boolean; mode: string };
  llm: { name: string; model: string; connected: boolean; mode: string };
  github: { name: string; repository: string; connected: boolean; mode: string };
}

export interface InvestigationSummary {
  id: string;
  dataset_urn: string;
  pr_url?: string;
  source: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  recommendation: 'SAFE_TO_MERGE' | 'MERGE_WITH_CAUTION' | 'BLOCK' | 'INSUFFICIENT_EVIDENCE';
  evidence_completeness: number;
  confirmed_consumers_count: number;
  potential_consumers_count: number;
  datahub_writeback_status: string;
  github_action_status: string;
  created_at: string;
}

export interface InvestigationDetail extends InvestigationSummary {
  changes: any;
  evidence_bundle: any;
  ai_explanation: any;
  remediation?: any;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeoutMs = 5000) => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (err: any) {
    clearTimeout(id);
    if (err.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeoutMs}ms`);
    }
    throw err;
  }
};

export async function fetchIntegrationsStatus(): Promise<IntegrationStatus> {
  const res = await fetchWithTimeout(`${API_BASE}/api/integrations/status`);
  if (!res.ok) throw new Error('Failed to fetch integrations status');
  return res.json();
}

export async function fetchInvestigations(): Promise<InvestigationSummary[]> {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations`);
  if (!res.ok) throw new Error('Failed to fetch investigations');
  return res.json();
}

export async function fetchInvestigation(id: string): Promise<InvestigationDetail> {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch investigation ${id}`);
  return res.json();
}

export async function analyzeChange(beforeSchema: any, afterSchema: any, prUrl?: string) {
  const res = await fetchWithTimeout(`${API_BASE}/api/changes/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      before_schema: beforeSchema,
      after_schema: afterSchema,
      pr_url: prUrl
    })
  });
  if (!res.ok) throw new Error('Failed to analyze change');
  return res.json();
}

export async function triggerWriteback(id: string) {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/writeback`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to writeback to DataHub');
  return res.json();
}

export async function triggerGitHubComment(id: string) {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/github/comment`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to trigger GitHub action');
  return res.json();
}

export async function fetchInvestigationEvents(id: string) {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/events`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}
