import dotenv from 'dotenv';
import { execSync } from 'node:child_process';
import path from 'node:path';

dotenv.config();

function resolveGitHubToken(): string {
  if (process.env.GITHUB_TOKEN && process.env.GITHUB_TOKEN.trim().length > 0) {
    return process.env.GITHUB_TOKEN.trim();
  }
  try {
    const token = execSync('gh auth token', { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] }).trim();
    if (token.length > 0) {
      return token;
    }
  } catch {
    // gh auth token not available or not logged in
  }
  return '';
}

export interface CodeFixConfig {
  githubToken: string;
  githubOwner: string;
  githubRepo: string;
  githubIssueNumber: number;
  trueforgeUrl: string;
  modelProvider: string;
  modelName: string;
  sandboxBaseDir: string;
  execTimeoutMs: number;
  autoApprove: boolean;
}

export function loadConfig(): CodeFixConfig {
  const githubToken = resolveGitHubToken();
  const githubOwner = process.env.GITHUB_OWNER || 'ABDULMUNAFZ';
  const githubRepo = process.env.GITHUB_REPO || 'codefix-demo';
  const githubIssueNumber = parseInt(process.env.GITHUB_ISSUE_NUMBER || '2', 10);
  const trueforgeUrl = process.env.TRUEFORGE_URL || 'http://127.0.0.1:8790';
  const modelProvider = process.env.MODEL_PROVIDER || 'openai';
  const modelName = process.env.MODEL_NAME || 'openai/gpt-5-4-mini';
  const sandboxBaseDir = process.env.SANDBOX_BASE_DIR || '/tmp/codefix-sandboxes';
  const execTimeoutMs = parseInt(process.env.EXEC_TIMEOUT_MS || '60000', 10);
  const autoApprove = process.env.CODEFIX_AUTO_APPROVE === 'true';

  return {
    githubToken,
    githubOwner,
    githubRepo,
    githubIssueNumber,
    trueforgeUrl,
    modelProvider,
    modelName,
    sandboxBaseDir,
    execTimeoutMs,
    autoApprove,
  };
}
