export interface IntegrationStatus {
  datahub: { name: string; url: string; connected: boolean; mode: string; discovered_tools?: string[] };
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
  approval_status?: string;
  integration_mode?: string;
  evidence_trust?: string;
}

export interface SchemaFieldInput {
  name: string;
  type: string;
  nullable: boolean;
  description?: string;
}

export interface SchemaSnapshotInput {
  dataset: {
    urn: string;
    name: string;
    platform?: string;
    env?: string;
  };
  fields: SchemaFieldInput[];
}

export interface EvidenceProvenance {
  source_mode: string;
  source_tool: string;
  entity_urn?: string;
  field_path?: string;
  retrieved_at?: string;
  source_reference?: string;
  verified: boolean;
}

export interface ImpactEvidence {
  type: string;
  description: string;
  provenance?: EvidenceProvenance;
}

export interface ClassifiedAsset {
  asset_urn: string;
  name: string;
  platform?: string;
  classification: string;
  evidence: ImpactEvidence[];
}

export interface ImpactGraphData {
  nodes: Array<{
    id: string;
    label: string;
    type: string;
    platform?: string;
    classification: string;
    owners: string[];
    tags: string[];
  }>;
  edges: Array<{
    source: string;
    target: string;
    lineage_type: string;
    field_mapping?: string;
    hop_count?: number;
  }>;
}

export interface EvidenceBundle {
  integration_mode: string;
  graph: ImpactGraphData;
  classified_assets: ClassifiedAsset[];
}

export interface CompletenessSignal {
  signal_name: string;
  is_present: boolean;
  weight: number;
  description: string;
}

export interface RiskAssessment {
  evidence_completeness: number;
  evidence_trust: string;
  completeness_breakdown: CompletenessSignal[];
  [key: string]: unknown;
}

export interface AIExplanation {
  executive_summary: string;
  why_it_matters: string;
  recommended_action: string;
  affected_systems: string[];
}

export interface RemediationArtifact {
  file_path: string;
  unified_diff: string;
  remediated_sql: string;
  validation: {
    is_valid: boolean;
    status: string;
  };
}

export interface InvestigationEvent {
  id: number;
  stage: string;
  status: string;
  message: string;
  details?: Record<string, unknown>;
  created_at?: string;
}

export interface ExternalActionResult {
  status: string;
  success: boolean;
  message: string;
}

export interface ApprovalResult {
  status: string;
  approved_at?: string;
  approved_by?: string;
}

const authorizationHeaders = (authToken: string): HeadersInit => ({
  Authorization: `Bearer ${authToken}`,
});

export interface InvestigationDetail extends InvestigationSummary {
  changes: Record<string, unknown>;
  evidence_bundle: EvidenceBundle;
  risk_assessment?: RiskAssessment;
  ai_explanation: AIExplanation;
  remediation?: RemediationArtifact;
  approved_at?: string;
  approved_by?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeoutMs = 5000) => {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (err: unknown) {
    clearTimeout(id);
    if (err instanceof Error && err.name === 'AbortError') {
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

export async function analyzeChange(
  beforeSchema: SchemaSnapshotInput,
  afterSchema: SchemaSnapshotInput,
  prUrl?: string,
): Promise<InvestigationDetail> {
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

export async function approveInvestigation(id: string, authToken: string): Promise<ApprovalResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/approve`, {
    method: 'POST',
    headers: authorizationHeaders(authToken),
  });
  if (!res.ok) throw new Error('Authenticated approval failed');
  return res.json();
}

export async function triggerWriteback(id: string, authToken: string): Promise<ExternalActionResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/writeback`, {
    method: 'POST',
    headers: authorizationHeaders(authToken),
  });
  if (!res.ok) throw new Error('Failed to writeback to DataHub');
  return res.json();
}

export async function triggerGitHubComment(id: string, authToken: string): Promise<ExternalActionResult> {
  const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/github/comment`, {
    method: 'POST',
    headers: authorizationHeaders(authToken),
  });
  if (!res.ok) throw new Error('Failed to trigger GitHub action');
  return res.json();
}

export async function fetchInvestigationEvents(id: string): Promise<InvestigationEvent[]> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/api/investigations/${id}/events`);
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}
