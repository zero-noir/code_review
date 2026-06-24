const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8004').replace(/\/$/, '');

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> | undefined) };
  if (!(init?.body instanceof FormData)) headers['content-type'] = 'application/json';
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
  return res.json();
}

export type Health = { ok: boolean; app_name: string; uploads: number; reviews: number; ai_enabled: boolean; provider: string; agents: string[] };
export type UploadedRepository = { session_id: string; repo_name: string; uploaded_filename: string; file_count: number; default_targets: string[]; detected_stack: string[]; warnings: string[] };
export type RepoFile = { path: string; size: number; kind: string; selected: boolean };
export type FileListResponse = { session_id: string; files: RepoFile[]; default_targets: string[] };
export type Finding = { id: string; severity: 'blocker'|'warning'|'suggestion'|'nit'|'praise'; agent: string; title: string; file?: string | null; line?: number | null; evidence: string; why_it_matters: string; recommendation: string; patch_hint?: string | null; confidence: number };
export type AgentTrace = { agent: string; status: 'complete'|'skipped'|'error'; summary: string; findings: number };
export type ReviewResponse = { review_id: string; session_id: string; repo_name: string; ai_mode: string; summary: string; score: number; findings: Finding[]; traces: AgentTrace[]; patch_checklist: string[]; markdown_report: string; json_export: any };
export type SessionSummary = { session_id: string; repo_name: string; created_at: string; file_count: number; review_count: number };
export type SkillCard = { name: string; role: string; incorporated_as: string; source_file: string };

export const api = {
  health: () => request<Health>('/api/v1/review/health'),
  upload: (file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<UploadedRepository>('/api/v1/review/upload', { method: 'POST', body });
  },
  files: (sessionId: string) => request<FileListResponse>(`/api/v1/review/files/${sessionId}`),
  run: (payload: { session_id: string; objective: string; target_files: string[]; focus_areas: string[]; use_llm: boolean }) => request<ReviewResponse>('/api/v1/review/run', { method: 'POST', body: JSON.stringify(payload) }),
  sessions: () => request<SessionSummary[]>('/api/v1/review/sessions'),
  skills: () => request<SkillCard[]>('/api/v1/review/skills')
};
