<script lang="ts">
  import { api, type Finding, type Health, type RepoFile, type ReviewResponse, type SkillCard, type UploadedRepository } from '$lib/api/client';

  type Stage = 'upload' | 'scope' | 'review' | 'report';

  const focusOptions = [
    { id: 'api_contract', label: 'API contract' },
    { id: 'frontend', label: 'Frontend' },
    { id: 'backend', label: 'Backend' },
    { id: 'security', label: 'Security' },
    { id: 'database', label: 'Database' },
    { id: 'devops', label: 'DevOps' },
    { id: 'ui', label: 'UI' },
    { id: 'git', label: 'Git' },
    { id: 'mcp', label: 'MCP' }
  ];

  let stage = $state<Stage>('upload');
  let health = $state<Health | null>(null);
  let skills = $state<SkillCard[]>([]);
  let upload = $state<UploadedRepository | null>(null);
  let files = $state<RepoFile[]>([]);
  let selected = $state<string[]>([]);
  let query = $state('');
  let objective = $state('Review this repository for production readiness. Prioritize route mismatches, install failures, security risks, and exact file-level fixes.');
  let focusAreas = $state<string[]>(['api_contract', 'frontend', 'backend', 'security', 'devops']);
  let useLlm = $state(true);
  let result = $state<ReviewResponse | null>(null);
  let loading = $state(false);
  let error = $state('');
  let copied = $state('');

  const visibleFiles = $derived(files.filter((file) => {
    const q = query.toLowerCase();
    return !q || `${file.path} ${file.kind}`.toLowerCase().includes(q);
  }));

  const severityCounts = $derived({
    blocker: result?.findings.filter((f) => f.severity === 'blocker').length ?? 0,
    warning: result?.findings.filter((f) => f.severity === 'warning').length ?? 0,
    suggestion: result?.findings.filter((f) => f.severity === 'suggestion').length ?? 0,
    nit: result?.findings.filter((f) => f.severity === 'nit').length ?? 0
  });

  async function uploadRepo(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    loading = true;
    error = '';
    try {
      upload = await api.upload(file);
      const fileData = await api.files(upload.session_id);
      files = fileData.files;
      selected = fileData.default_targets;
      stage = 'scope';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Upload failed';
    } finally {
      loading = false;
    }
  }

  function toggleFile(path: string) {
    selected = selected.includes(path) ? selected.filter((x) => x !== path) : [...selected, path];
  }

  function toggleFocus(id: string) {
    focusAreas = focusAreas.includes(id) ? focusAreas.filter((x) => x !== id) : [...focusAreas, id];
  }

  async function runReview() {
    if (!upload) return;
    loading = true;
    error = '';
    stage = 'review';
    try {
      result = await api.run({ session_id: upload.session_id, objective, target_files: selected, focus_areas: focusAreas, use_llm: useLlm });
      stage = 'report';
    } catch (e) {
      error = e instanceof Error ? e.message : 'Review failed';
      stage = 'scope';
    } finally {
      loading = false;
    }
  }

  async function copyText(label: string, text: string) {
    await navigator.clipboard.writeText(text);
    copied = label;
    setTimeout(() => copied = '', 1400);
  }

  function severityLabel(severity: Finding['severity']) {
    if (severity === 'blocker') return 'Blocker';
    if (severity === 'warning') return 'Warning';
    if (severity === 'suggestion') return 'Suggestion';
    if (severity === 'nit') return 'Nit';
    return 'Praise';
  }

  $effect(() => {
    api.health().then((data) => health = data).catch(() => {});
    api.skills().then((data) => skills = data).catch(() => {});
  });
</script>

<svelte:head><title>Code Review Console</title></svelte:head>

<main class="shell">
  <aside class="rail">
    <div class="brand">
      <svg viewBox="0 0 36 36" aria-hidden="true"><path d="M7 9.5h22v17H7z"/><path d="M13 15h10M13 19h7M10 29h16"/></svg>
      <span>ReviewLab</span>
    </div>

    <nav aria-label="Review stages">
      <button type="button" class:active={stage === 'upload'} onclick={() => stage = 'upload'}>Upload</button>
      <button type="button" class:active={stage === 'scope'} disabled={!upload} onclick={() => stage = 'scope'}>Scope</button>
      <button type="button" class:active={stage === 'review'} disabled={!upload} onclick={() => stage = 'review'}>Run</button>
      <button type="button" class:active={stage === 'report'} disabled={!result} onclick={() => stage = 'report'}>Report</button>
    </nav>

    <section class="status-card">
      <span class:online={health?.ai_enabled}></span>
      <strong>{health?.ai_enabled ? 'LLM review enabled' : 'Offline review mode'}</strong>
      <p>{health?.provider ?? 'offline'} · {health?.reviews ?? 0} stored reviews</p>
    </section>

    <section class="skill-list">
      <h2>Review agents</h2>
      {#each skills.slice(0, 6) as skill}
        <div><strong>{skill.name}</strong><span>{skill.incorporated_as}</span></div>
      {/each}
    </section>
  </aside>

  <section class="workspace">
    <header class="topbar">
      <div>
        <p class="eyebrow">Production code review platform</p>
        <h1>Upload a repository. Get a file-level review with contract checks and patch guidance.</h1>
      </div>
      {#if upload}
        <button type="button" onclick={runReview} disabled={loading || !selected.length}>{loading ? 'Reviewing…' : 'Run review'}</button>
      {/if}
    </header>

    {#if error}<p class="error">{error}</p>{/if}

    {#if stage === 'upload'}
      <section class="upload-grid">
        <div class="upload-card">
          <label for="repo-upload">Repository ZIP</label>
          <input id="repo-upload" type="file" accept=".zip" onchange={uploadRepo} />
          <p>Upload a GitHub repository ZIP. The reviewer defaults to README, manifests, SvelteKit/FastAPI config, API clients, routers, schemas, and services.</p>
        </div>
        <div class="empty-illustration" aria-hidden="true">
  <svg viewBox="0 0 640 420" class="review-illustration">
    <defs>
      <linearGradient id="panelBg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#ffffff" />
        <stop offset="100%" stop-color="#f3edf9" />
      </linearGradient>
      <linearGradient id="accentStroke" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#7a5ad8" />
        <stop offset="100%" stop-color="#17151c" />
      </linearGradient>
    </defs>

    <rect class="frame" x="72" y="46" width="496" height="328" rx="32" fill="url(#panelBg)" />

    <!-- repo card -->
    <rect class="card" x="112" y="92" width="184" height="132" rx="22" />
    <path class="folder" d="M138 128h42l12 13h78v54H138z" />
    <path class="folder-line" d="M138 141h132" />
    <path class="text-line" d="M146 185h92" />
    <path class="text-line faint" d="M146 202h72" />

    <!-- routing arrow -->
    <path class="route" d="M314 158h74" />
    <path class="route-head" d="M370 142l22 16-22 16" />

    <!-- findings/report card -->
    <rect class="card" x="412" y="88" width="120" height="144" rx="22" />
    <path class="text-line" d="M436 124h60" />
    <path class="text-line faint" d="M436 147h48" />
    <path class="text-line faint" d="M436 170h54" />
    <circle class="badge" cx="496" cy="198" r="18" />
    <path class="check" d="M488 198l7 7 13-16" />

    <!-- bottom insight strip -->
    <rect class="card soft" x="116" y="262" width="416" height="70" rx="20" />
    <circle class="mini-dot" cx="146" cy="297" r="8" />
    <path class="text-line" d="M166 286h118" />
    <path class="text-line faint" d="M166 306h92" />
    <circle class="mini-dot alt" cx="334" cy="297" r="8" />
    <path class="text-line" d="M354 286h90" />
    <path class="text-line faint" d="M354 306h70" />
    <circle class="mini-dot" cx="478" cy="297" r="8" />
  </svg>
</div>
      </section>
    {/if}

    {#if stage === 'scope' && upload}
      <section class="scope-grid">
        <div class="panel">
          <div class="panel-head">
            <div><h2>{upload.repo_name}</h2><p>{upload.file_count} files · {upload.detected_stack.join(' · ')}</p></div>
            <input aria-label="Filter files" placeholder="Filter files" bind:value={query} />
          </div>

          <div class="file-list">
            {#each visibleFiles as file}
              <button type="button" class:selected={selected.includes(file.path)} onclick={() => toggleFile(file.path)}>
                <span>{file.path}</span>
                <small>{file.kind} · {(file.size / 1024).toFixed(1)} KB</small>
              </button>
            {/each}
          </div>
        </div>

        <aside class="panel config-panel">
          <h2>Review configuration</h2>
          <label for="objective-input">Review objective</label>
          <textarea id="objective-input" bind:value={objective}></textarea>

          <h3>Focus areas</h3>
          <div class="focus-grid">
            {#each focusOptions as option}
              <button type="button" class:active={focusAreas.includes(option.id)} onclick={() => toggleFocus(option.id)}>{option.label}</button>
            {/each}
          </div>

          <label class="check-row" for="llm-toggle">
            <input id="llm-toggle" type="checkbox" bind:checked={useLlm} />
            <span>Use LLM synthesis when configured</span>
          </label>

          <button type="button" class="wide" onclick={runReview} disabled={loading || !selected.length}>Run review on {selected.length} files</button>
        </aside>
      </section>
    {/if}

    {#if stage === 'review'}
      <section class="running-card">
        <div class="pulse"></div>
        <h2>Review agents are scanning the repository</h2>
        <p>Mapping files, comparing API routes, checking frontend accessibility, dependency traps, security patterns, and patch priorities.</p>
      </section>
    {/if}

    {#if stage === 'report' && result}
      <section class="report-grid">
        <div class="report-main">
          <div class="score-card">
            <span>Score</span>
            <strong>{result.score}</strong>
            <p>{result.summary}</p>
          </div>

          <div class="counts">
            <div><strong>{severityCounts.blocker}</strong><span>Blockers</span></div>
            <div><strong>{severityCounts.warning}</strong><span>Warnings</span></div>
            <div><strong>{severityCounts.suggestion}</strong><span>Suggestions</span></div>
            <div><strong>{severityCounts.nit}</strong><span>Nits</span></div>
          </div>

          <section class="findings">
            <h2>Findings</h2>
            {#each result.findings as finding}
              <article class={`finding ${finding.severity}`}>
                <div class="finding-top"><span>{severityLabel(finding.severity)}</span><small>{finding.agent}</small></div>
                <h3>{finding.title}</h3>
                {#if finding.file}<p class="file-ref">{finding.file}{finding.line ? `:${finding.line}` : ''}</p>{/if}
                <p>{finding.evidence}</p>
                <div class="why"><strong>Why</strong><span>{finding.why_it_matters}</span></div>
                <div class="why"><strong>Fix</strong><span>{finding.recommendation}</span></div>
              </article>
            {/each}
          </section>
        </div>

        <aside class="report-side">
          <section>
            <div class="side-head"><h2>Patch checklist</h2><button type="button" onclick={() => copyText('checklist', result.patch_checklist.join('\n'))}>{copied === 'checklist' ? 'Copied' : 'Copy'}</button></div>
            <ol>{#each result.patch_checklist as item}<li>{item}</li>{/each}</ol>
          </section>

          <section>
            <div class="side-head"><h2>Agent trace</h2></div>
            {#each result.traces as trace}
              <div class="trace"><strong>{trace.agent}</strong><span>{trace.status} · {trace.findings} findings</span><p>{trace.summary}</p></div>
            {/each}
          </section>

          <section>
            <div class="side-head"><h2>Markdown report</h2><button type="button" onclick={() => copyText('markdown', result.markdown_report)}>{copied === 'markdown' ? 'Copied' : 'Copy'}</button></div>
            <pre>{result.markdown_report}</pre>
          </section>
        </aside>
      </section>
    {/if}
  </section>
</main>

<style>
  :global(body){margin:0;background:#f4f1f8;color:#17151c;font-family:Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;font-size:14px}.shell{min-height:100vh;display:grid;grid-template-columns:248px minmax(0,1fr)}.rail{background:#17151c;color:#f8f5ff;padding:22px 18px;display:flex;flex-direction:column;gap:22px;position:sticky;top:0;height:100vh;box-sizing:border-box}.brand{display:flex;align-items:center;gap:10px;font-weight:700}.brand svg{width:32px;height:32px}.brand svg path:first-child{fill:#d8c7ff}.brand svg path:not(:first-child){fill:none;stroke:#17151c;stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round}.brand svg circle{fill:none;stroke:#17151c;stroke-width:2}.brand span{font-size:15px}nav{display:grid;gap:7px}nav button{text-align:left;border:0;background:transparent;color:#bfb6d0;border-radius:12px;padding:10px 11px;cursor:pointer;font-size:13px}nav button.active,nav button:hover{background:#262230;color:white}nav button:disabled{opacity:.35}.status-card,.skill-list{border:1px solid #302a3d;background:#201c28;border-radius:18px;padding:14px}.status-card span{display:inline-block;width:8px;height:8px;background:#91879f;border-radius:50%;margin-right:8px}.status-card span.online{background:#75d6a3}.status-card strong{font-size:13px}.status-card p,.skill-list span{display:block;color:#bfb6d0;font-size:12px;line-height:1.45}.skill-list{margin-top:auto;max-height:340px;overflow:auto}.skill-list h2{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#a996d9;margin:0 0 10px}.skill-list div{border-top:1px solid #302a3d;padding:10px 0}.skill-list strong{display:block;font-size:12px}.workspace{padding:24px 30px 38px}.topbar{display:flex;justify-content:space-between;gap:22px;align-items:flex-start;margin-bottom:22px}.eyebrow{margin:0 0 8px;text-transform:uppercase;letter-spacing:.13em;color:#6e55b3;font-size:11px}.topbar h1{font-size:29px;line-height:1.08;letter-spacing:-.045em;max-width:860px;margin:0;font-weight:680}button{border:0;background:#17151c;color:white;border-radius:999px;padding:10px 14px;font-size:13px;cursor:pointer}button:disabled{opacity:.45;cursor:not-allowed}.error{background:#fff2f0;color:#9b2f28;border:1px solid #f2c9c4;padding:10px 12px;border-radius:14px}.upload-grid{display:grid;grid-template-columns:minmax(360px,.8fr) minmax(0,1.2fr);gap:16px}.upload-card,.panel,.running-card,.report-side section,.score-card,.findings{background:#fff;border:1px solid #dfd7eb;border-radius:24px;padding:18px;box-shadow:0 22px 70px rgba(58,40,94,.055)}label{display:block;color:#5f566d;font-size:12px;margin:0 0 8px}input,textarea{box-sizing:border-box;width:100%;border:1px solid #dcd3ea;background:#fff;border-radius:14px;padding:11px 12px;font:inherit;color:#17151c}input[type=file]{padding:14px}textarea{min-height:128px;resize:vertical;line-height:1.5}.upload-card p{font-size:13px;color:#625a6e;line-height:1.55}
  .empty-illustration{display:grid;place-items:center;background:#ebe5f4;border:1px solid #ded4ee;border-radius:24px}
  .empty-illustration svg{width:min(560px,96%)}.empty-illustration rect{fill:#fff;stroke:#d2c4e7}
  .empty-illustration path{fill:none;stroke:#17151c;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}
  .empty-illustration circle{fill:#d8c7ff;stroke:#17151c;stroke-width:3}
  .review-illustration {
  width: min(600px, 96%);
}

.review-illustration .frame {
  stroke: #d7cceb;
  stroke-width: 1.5;
}

.review-illustration .card {
  fill: #fffdfd;
  stroke: #d8cfea;
  stroke-width: 1.5;
}

.review-illustration .card.soft {
  fill: #faf7ff;
}

.review-illustration .folder {
  fill: #d8c7ff;
  stroke: #17151c;
  stroke-width: 2.5;
  stroke-linejoin: round;
}

.review-illustration .folder-line,
.review-illustration .text-line,
.review-illustration .route,
.review-illustration .route-head,
.review-illustration .check {
  fill: none;
  stroke: #17151c;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.review-illustration .text-line.faint {
  stroke: #9a90aa;
  stroke-width: 3.2;
}

.review-illustration .badge {
  fill: #d8c7ff;
  stroke: #17151c;
  stroke-width: 2.5;
}

.review-illustration .mini-dot {
  fill: #17151c;
}

.review-illustration .mini-dot.alt {
  fill: #7a5ad8;
}
  .scope-grid,.report-grid{display:grid;grid-template-columns:minmax(0,1fr) 430px;gap:16px}.panel-head{display:flex;justify-content:space-between;gap:14px;align-items:center;margin-bottom:12px}.panel-head h2,.config-panel h2,.findings h2,.side-head h2{margin:0;font-size:16px;letter-spacing:-.02em}.panel-head p{font-size:12px;color:#71677e;margin:3px 0 0}.panel-head input{max-width:260px}.file-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:9px;max-height:66vh;overflow:auto}.file-list button{text-align:left;background:#fbf9ff;color:#17151c;border:1px solid #e4ddef;border-radius:14px;padding:11px}.file-list button.selected{background:#17151c;color:white;border-color:#17151c}.file-list span{display:block;font-size:12px;line-height:1.25;overflow:hidden;text-overflow:ellipsis}.file-list small{display:block;margin-top:6px;color:#847991;font-size:11px}.file-list button.selected small{color:#cfc5de}.config-panel h3{font-size:13px;margin:18px 0 9px}.focus-grid{display:flex;gap:7px;flex-wrap:wrap}.focus-grid button{background:#f6f2fb;color:#514661;border:1px solid #dfd6eb;padding:8px 10px;font-size:12px}.focus-grid button.active{background:#6e55b3;color:white}.check-row{display:flex;gap:9px;align-items:center;margin:18px 0}.check-row input{width:auto}.wide{width:100%;margin-top:4px}.running-card{text-align:center;padding:60px}.pulse{width:42px;height:42px;border-radius:50%;background:#d8c7ff;margin:0 auto 16px;box-shadow:0 0 0 0 rgba(110,85,179,.5);animation:pulse 1.5s infinite}@keyframes pulse{to{box-shadow:0 0 0 28px rgba(110,85,179,0)}}.running-card p{color:#6b6178}.report-main{display:grid;gap:14px}.score-card span{font-size:12px;color:#6e55b3;text-transform:uppercase;letter-spacing:.12em}.score-card strong{display:block;font-size:52px;letter-spacing:-.06em}.score-card p{color:#5e566a;line-height:1.5}.counts{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.counts div{background:#fff;border:1px solid #dfd7eb;border-radius:18px;padding:14px}.counts strong{font-size:24px;display:block}.counts span{font-size:12px;color:#71677e}.finding{border:1px solid #e1d9ec;border-radius:18px;padding:14px;margin-top:10px;background:#fff}.finding.blocker{border-color:#e9aaa4;background:#fff7f6}.finding.warning{border-color:#e5c37a;background:#fffaf0}.finding.suggestion{border-color:#cfc2ed;background:#fbf9ff}.finding-top{display:flex;justify-content:space-between;gap:8px}.finding-top span{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#6e55b3}.finding h3{font-size:15px;margin:9px 0}.finding p,.why span,.report-side li,.trace p{font-size:12px;color:#5f566d;line-height:1.5}.file-ref{font-family:ui-monospace, SFMono-Regular, Menlo, monospace;color:#6e55b3!important}.why{display:grid;grid-template-columns:58px 1fr;gap:10px;border-top:1px solid #ece6f3;padding-top:9px;margin-top:9px}.why strong{font-size:12px}.report-side{display:grid;gap:14px;align-self:start}.side-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}.side-head button{background:#fff;color:#17151c;border:1px solid #d9d0e8;padding:7px 11px;font-size:12px}.trace{border:1px solid #eee8f5;background:#fbf9ff;border-radius:14px;padding:10px;margin-bottom:8px}.trace strong{font-size:12px;display:block}.trace span{font-size:11px;color:#6e55b3}pre{max-height:360px;overflow:auto;background:#17151c;color:#f7f2ff;border-radius:16px;padding:12px;font-size:11px;line-height:1.45}@media(max-width:1120px){.shell{grid-template-columns:1fr}.rail{position:static;height:auto}.upload-grid,.scope-grid,.report-grid{grid-template-columns:1fr}.counts{grid-template-columns:repeat(2,1fr)}.topbar{display:grid}}
</style>
