// src/types/index.ts — Phase 14: バックエンドマニフェストの型定義

export type Reliability = 'high' | 'medium' | 'low' | 'unknown';

export interface ReliabilityInfo {
  label: string;
  description: string;
}

export interface VideoItem {
  key: string;
  label: string;
  description: string;
  filename: string | null;
  url: string | null;
  content_type: string;
  available: boolean;
}

export interface PhaseImage {
  phase_key: string;
  label: string;
  description: string;
  tip: string;
  filename: string | null;
  url: string | null;
  frame_num: number | null;
  frame_time_sec: number | null;
  available: boolean;
}

export interface KeyMetric {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  reliability: Reliability;
  reliability_label: string;
  reliability_description: string;
  caution: string;
  note: string;
}

export interface DetailMetric {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  reliability: Reliability;
  reliability_label: string;
}

export interface GraphItem {
  key: string;
  label: string;
  description: string;
  filename: string | null;
  url: string | null;
  available: boolean;
}

export interface DownloadItem {
  label: string;
  filename: string | null;
  url: string | null;
  available: boolean;
  is_research: boolean;
  category: string;
}

export interface DownloadCategories {
  intro: DownloadItem[];
  athlete: DownloadItem[];
  advanced: DownloadItem[];
  coach: DownloadItem[];
  packages: DownloadItem[];
  research: DownloadItem[];
  [key: string]: DownloadItem[];
}

export interface SectionFlags {
  videos: boolean;
  phase_images: boolean;
  metrics: boolean;
  graphs: boolean;
  downloads: boolean;
  research_data: boolean;
}

export interface InquiryInfo {
  job_id: string;
  delivered_at: string;
  plan_label: string;
}

export interface DashboardManifest {
  schema_version: string;
  dashboard_token: string;
  job_id: string;
  dashboard_type: 'single' | 'comparison';
  display_name: string;
  plan_label: string;
  delivered_at: string;
  generated_at: string;
  token_expires_at: string;
  url_expires_at: string;
  metrics_version: string;
  overall_quality: string;
  metrics_reliability: string;
  sections: SectionFlags;
  notices: string[];
  videos: VideoItem[];
  phase_images: PhaseImage[];
  key_metrics: KeyMetric[];
  detail_metrics: Record<string, DetailMetric[]>;
  graphs: GraphItem[];
  downloads: DownloadCategories;
  disclaimer: string;
  inquiry_info: InquiryInfo;
}

export type ApiError =
  | { type: 'not_found' }
  | { type: 'expired'; token_expires_at?: string }
  | { type: 'network' }
  | { type: 'unknown'; detail?: string };
