export interface GitHubIssue {
  number: number;
  title: string;
  body: string;
  state: string;
  author: string;
  url: string;
  labels: string[];
}

export interface GitHubRepoInfo {
  name: string;
  owner: string;
  defaultBranch: string;
  cloneUrl: string;
  htmlUrl: string;
}

export interface CreatePRParams {
  owner: string;
  repo: string;
  title: string;
  body: string;
  head: string;
  base: string;
}

export interface PullRequestResult {
  number: number;
  url: string;
  title: string;
  state: string;
}
