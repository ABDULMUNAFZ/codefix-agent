export interface ExecResult {
  command: string;
  exitCode: number;
  stdout: string;
  stderr: string;
  durationMs: number;
}

export interface TestResult {
  passed: boolean;
  total: number;
  failures: number;
  output: string;
  durationMs: number;
}

export interface ReproductionResult {
  reproduced: boolean;
  exitCode: number;
  output: string;
  expectedBehavior?: string;
  actualBehavior?: string;
}

export interface SandboxSession {
  jobId: string;
  dir: string;
  repoDir: string;
  createdAt: Date;
}
