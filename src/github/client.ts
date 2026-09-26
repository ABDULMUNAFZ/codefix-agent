import { GitHubIssue, GitHubRepoInfo, CreatePRParams, PullRequestResult } from './types.js';

export class RealGitHubClient {
  private readonly token: string;
  private readonly baseUrl = 'https://api.github.com';

  constructor(token: string) {
    if (!token || token.trim().length === 0) {
      throw new Error('GitHub token is required for RealGitHubClient operations');
    }
    this.token = token.trim();
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = path.startsWith('http') ? path : `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      'Accept': 'application/vnd.github+json',
      'Authorization': `Bearer ${this.token}`,
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'CodeFix-Autonomous-Agent',
      ...(options.headers as Record<string, string> || {}),
    };

    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      const errBody = await res.text();
      throw new Error(`GitHub API Error [${res.status} ${res.statusText}] at ${path}: ${errBody}`);
    }
    return (await res.json()) as T;
  }

  // ================= READ OPERATIONS =================

  async getIssue(owner: string, repo: string, issueNumber: number): Promise<GitHubIssue> {
    interface ApiIssue {
      number: number;
      title: string;
      body: string | null;
      state: string;
      html_url: string;
      user: { login: string } | null;
      labels: Array<{ name: string }>;
    }
    const data = await this.request<ApiIssue>(`/repos/${owner}/${repo}/issues/${issueNumber}`);
    return {
      number: data.number,
      title: data.title,
      body: data.body || '',
      state: data.state,
      author: data.user?.login || 'unknown',
      url: data.html_url,
      labels: data.labels.map(l => l.name),
    };
  }

  async getRepoInfo(owner: string, repo: string): Promise<GitHubRepoInfo> {
    interface ApiRepo {
      name: string;
      owner: { login: string };
      default_branch: string;
      clone_url: string;
      html_url: string;
    }
    const data = await this.request<ApiRepo>(`/repos/${owner}/${repo}`);
    return {
      name: data.name,
      owner: data.owner.login,
      defaultBranch: data.default_branch,
      cloneUrl: data.clone_url,
      htmlUrl: data.html_url,
    };
  }

  async getLatestCommitSha(owner: string, repo: string, branch: string): Promise<string> {
    interface ApiRef {
      object: { sha: string };
    }
    const data = await this.request<ApiRef>(`/repos/${owner}/${repo}/git/ref/heads/${branch}`);
    return data.object.sha;
  }

  // ================= HIGH-RISK WRITE OPERATIONS =================

  async createRemoteBranch(owner: string, repo: string, newBranch: string, fromSha: string): Promise<void> {
    await this.request(`/repos/${owner}/${repo}/git/refs`, {
      method: 'POST',
      body: JSON.stringify({
        ref: `refs/heads/${newBranch}`,
        sha: fromSha,
      }),
    });
  }

  async createPullRequest(params: CreatePRParams): Promise<PullRequestResult> {
    interface ApiPr {
      number: number;
      html_url: string;
      title: string;
      state: string;
    }
    const data = await this.request<ApiPr>(`/repos/${params.owner}/${params.repo}/pulls`, {
      method: 'POST',
      body: JSON.stringify({
        title: params.title,
        body: params.body,
        head: params.head,
        base: params.base,
      }),
    });
    return {
      number: data.number,
      url: data.html_url,
      title: data.title,
      state: data.state,
    };
  }
}
