export type RasterBox = [number, number, number, number];
export type PunctuationReader = 'raw' | 'locally_leveled';
export interface PunctuationAssessment {
  status: 'complete' | 'incomplete';
  reason: 'checked' | 'no_currency_scope' | 'page_budget' | 'reader_error' | 'reader_unavailable' | 'source_scope_unverified';
  stage: 'nomination_raw' | 'nomination_contrast' | 'currency_fields';
}
export interface PunctuationReading {
  reader: PunctuationReader;
  text: string;
  glyphs: [string, RasterBox][];
}
export interface PunctuationEvent {
  status: 'punctuation_disagreement' | 'field_unavailable' | 'raw_unavailable' | 'contrast_unavailable' | 'page_budget' | 'reader_error' | 'invalid_glyph_vector' | 'source_ink_unverified';
  field_bounds: RasterBox | null;
  crop_bounds: RasterBox | null;
  coordinate_frame: 'original_raster_top_left_half_open';
  readings: PunctuationReading[];
  missing_readers: PunctuationReader[];
  canonical_usable: false;
  region?: RasterBox;
}
export interface PunctuationObservation {
  id: string;
  created_at: string;
  analysis_id: string;
  version_id: string;
  evidence_id: string;
  content_sha256: string;
  quote_sha256: string;
  document_id: string;
  document_revision: number;
  document_sha256: string;
  page: number;
  page_count: number;
  raster_sha256: string;
  width: number;
  height: number;
  event: PunctuationEvent;
  event_sha256: string;
  producer_sha256: string;
  producer_recipe: string;
  assessment?: PunctuationAssessment;
  run_sha256: string;
  run_id: string;
  scope: 'source_page_context';
  status: 'review_required';
  canonical_usable: false;
  immutable: true;
  observation_sha256: string;
}
export interface PunctuationSourcePins {
  matterId: string;
  analysisId: string;
  versionId: string;
  evidenceId: string;
  contentSha256: string;
  quoteSha256: string;
  documentId: string;
  documentRevision: number;
  documentSha256: string;
  page: number;
  pageCount: number;
  quote: string;
}

export interface PunctuationCaptureRun extends Omit<PunctuationObservation, 'event' | 'event_sha256' | 'run_id' | 'observation_sha256' | 'status'> {
  event_count: number;
  status: 'captured_no_alternatives' | 'captured_review_observations' | 'captured_incomplete';
  receipt_sha256: string;
}
export interface PunctuationPage {
  items: PunctuationObservation[];
  has_more: boolean;
  runs: PunctuationCaptureRun[];
  runs_has_more: boolean;
}
