export type Status =
  | "IDLE"
  | "QUEUED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED_RECOVERABLE"
  | "FAILED";

export type Stage = { sequence: number; stage: string; status: string };

export type Evidence = {
  evidence_id: string;
  source_name: string;
  source_host?: string | null;
  published_at: string;
  retrieved_at: string;
  authority: string;
  title: string;
  role: string;
  content_hash: string;
  locator?: string | null;
  page?: number | null;
  content_endpoint: string;
};

export type Hypothesis = {
  hypothesis_id: string;
  rank: number;
  status: string;
  driver_label: string;
  statement: string;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
};

export type Validation = {
  validation_id: string;
  kind: string;
  status: string;
  evidence_ids: string[];
};

export type Gap = {
  gap_id: string;
  capability: string;
  provider: string;
  retryable: boolean;
};

export type Conflict = {
  conflict_id: string;
  field: string;
  primary_source: string;
  primary_value: string;
  secondary_source: string;
  secondary_value: string;
  resolution: string;
};

export type Assertion = {
  assertion_id: string;
  evidence_id: string;
  span_hash: string;
  artifact_hash: string;
  locator?: string | null;
  role: string;
  causal_eligible: boolean;
  mechanism_hint: string;
  content_endpoint: string;
};

export type MechanismTest = {
  test_id: string;
  mechanism: string;
  status: string;
  summary: string;
  policy_version: string;
  supporting_assertion_ids: string[];
  contradicting_assertion_ids: string[];
};

export type LedgerEntry = {
  sequence: number;
  stage: string;
  status: string;
  input_hashes: string[];
  output_hashes: string[];
  policy_version: string;
  created_at: string;
  schema_version?: string;
  validation_status?: string;
};

export type CalibrationBand = {
  eligible_cases: number;
  material_errors: number;
  status: string;
};

export type CalibrationMetadata = {
  label: string;
  status: string;
  corpus_version?: string;
  confidence_rule_version?: string;
  bands: Record<string, CalibrationBand>;
};

export type ReleaseGate = {
  name: string;
  status: "PASS" | "FAIL" | "NOT_RUN";
  detail: string;
};

export type RetrievalLane = {
  lane: string;
  status: "PLANNED" | "COMPLETE" | "PARTIAL" | "FAILED" | "SKIPPED";
  evidence_ids: string[];
  source_count: number;
  reason_code?: string | null;
};

export type RetrievalPlan = {
  policy_version: string;
  plan_hash: string;
  follow_up_used: boolean;
  lanes: RetrievalLane[];
};

export type Report = {
  case_id: string;
  run_id: string;
  case_version: number;
  parent_version_id?: string;
  status: Status;
  outcome: string;
  ticker: string;
  trade_date: string;
  timezone_label: string;
  instrument: {
    asx_code: string;
    company_name: string;
    exchange: string;
    currency: string;
    sector?: string | null;
  };
  market_move?: {
    close_return_pct: number;
    open_gap_pct: number;
    open_to_close_pct: number;
    turnover_aud: number;
    volume_zscore?: number | null;
    return_zscore?: number | null;
    market_relative_return_pct?: number | null;
    is_unusual: boolean;
    resolution: string;
  } | null;
  assessment: { primary_claim_id?: string; summary: string };
  claims: Array<{
    claim_id: string;
    claim_type: string;
    text: string;
    supporting_evidence_ids: string[];
    contradicting_evidence_ids: string[];
  }>;
  evidence: Evidence[];
  hypotheses: Hypothesis[];
  validation_results: Validation[];
  coverage_gaps: Gap[];
  conflicts: Conflict[];
  confidence: {
    band: string;
    calibration_status: string;
    positive_factors: string[];
    negative_factors: string[];
    applied_caps: string[];
    rule_version: string;
  };
  completeness: {
    status: string;
    required_capabilities: string[];
    missing_capabilities: string[];
  };
  coverage_status: string;
  source_policy_version: string;
  retrieval_plan?: RetrievalPlan | null;
  assertions: Assertion[];
  mechanism_tests: MechanismTest[];
  ledger: LedgerEntry[];
  calibration_metadata: CalibrationMetadata;
  release_gates?: ReleaseGate[];
};

export type ArchiveItem = {
  case_id: string;
  version_id: string;
  version_number: number;
  parent_version_id?: string | null;
  ticker: string;
  trade_date: string;
  mode: string;
  status: string;
  outcome?: string | null;
  active_stage?: string | null;
  confidence_band?: string;
  evidence_count?: number;
  completeness_status?: string;
};
