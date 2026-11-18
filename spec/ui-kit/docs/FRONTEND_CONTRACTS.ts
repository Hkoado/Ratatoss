/** RATATOSS PROPOSED frontend view models.
 * NOT an agreed backend API specification. Must be reconciled with API Contracts.
 */
export type PeerId = string;
export type JobId = string;
export type ISODateTime = string;
export type LinkClass = 'LAN_VERIFIED' | 'WAN' | 'RELAY' | 'UNKNOWN';
export type PeerPresence = 'ONLINE' | 'OFFLINE' | 'STALE' | 'UNKNOWN';
export type JobState = 'QUEUED' | 'RUNNING' | 'VERIFYING' | 'COMPLETED_VERIFIED' | 'PARTIAL' | 'PAUSED' | 'FAILED' | 'CANCELLED' | 'UNKNOWN';
export type BatchState = 'MISSING' | 'ASSIGNED' | 'TRANSFERRING' | 'RECEIVED' | 'VERIFIED' | 'AVAILABLE' | 'RETRY_PENDING' | 'CORRUPT';
export type Strategy = 'FIXED_PIPELINE' | 'DIRECT' | 'GATEWAY' | 'ADAPTIVE_PLARS';
export type SafeExitPolicy = 'DISABLED' | 'SOURCE_CAN_LEAVE' | 'SOURCE_CAN_LEAVE_ONE_PEER_FAULT';

export interface PeerView {
  id: PeerId;
  displayName: string;
  isSource: boolean;
  presence: PeerPresence;
  lastHeartbeatAt: ISODateTime | null;
  canReceiveJob: boolean;
  canForward: boolean;
  rxGoodputBps: number | null;
  txGoodputBps: number | null;
  maxRxSessions: number | null;
  maxTxSessions: number | null;
  linkClass: LinkClass;
  linkMeasuredAt: ISODateTime | null;
}
export interface RecipientView {
  peerId: PeerId;
  totalBytes: number;
  receivedBytes: number;
  verifiedBytes: number;
  verifiedBatchCount: number;
  totalBatchCount: number;
  fileVerified: boolean;
  fileSha256VerifiedAt: ISODateTime | null;
  state: JobState;
  errorCode: string | null;
}
export interface LinkView {
  from: PeerId;
  to: PeerId;
  linkClass: LinkClass;
  activeAssignmentIds: string[];
  measuredGoodputBps: number | null;
  lastMeasuredAt: ISODateTime | null;
  state: 'ACTIVE' | 'IDLE' | 'FAILED' | 'UNKNOWN';
  sharedBottleneckGroupId: string | null;
}
export interface JobView {
  id: JobId;
  fileName: string;
  totalBytes: number;
  sha256: string | null;
  state: JobState;
  strategy: Strategy;
  sourcePeerId: PeerId;
  recipients: RecipientView[];
  links: LinkView[];
  makespanActualMs: number | null;
  makespanEstimatedMs: number | null;
  sourceUploadedPayloadBytes: number | null;
  wanBytes: number | null;
  startedAt: ISODateTime | null;
  completedAt: ISODateTime | null;
  lastTelemetryAt: ISODateTime | null;
}

export interface FrontendFeatureFlags {
  authIntegrated: boolean;
  transportIntegrated: boolean;
  adaptiveSchedulerAvailable: boolean;
  safeExitAvailable: boolean;
  encryptedPayloadAvailable: boolean;
}

/** Strict defaults for Phase 1 MVP UI until validated backend support. */
export const DEFAULT_FEATURE_FLAGS: FrontendFeatureFlags = {
  authIntegrated: false,
  transportIntegrated: false,
  adaptiveSchedulerAvailable: false,
  safeExitAvailable: false,
  encryptedPayloadAvailable: false,
};

export interface UiDataAdapter {
  /** Must not return simulated data when production mode is configured. */
  getJobStatus(jobId: JobId, signal?: AbortSignal): Promise<JobView>;
  /** Adapter endpoint is TBD; requires approval before implementation. */
  listPeers(signal?: AbortSignal): Promise<PeerView[]>;
}
