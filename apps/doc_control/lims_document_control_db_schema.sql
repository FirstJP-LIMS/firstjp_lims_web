I want us to work on the Document control system which is a critical component of a Laboratory Information Management System (LIMS) that is responsible. for the management of all controlled documents within the laboratory environment. 
my client also asked that it should be part of LIMS - the multi-tenant LIMS app.
We will consider some regulatory compliance (e.g., FDA 21 CFR Part 11, ISO 17025) in the development process
let's get into the development, please - the models etc...
-- LIMS Document Control System - Database Schema (PostgreSQL)
-- Author: ChatGPT (for developers)
-- Date: 2025-11-14 (updated 2025-11-14)
-- Purpose: Schema for managing documents, versions, change control, training, approvals
-- Extended features: Automated reminders (email/SMS), Digital signature workflow, Document lifecycle audit trail,
-- Approval routing matrix, Integration with LIMS SOP library, Auto-expiry alerts for controlled forms, Version comparison tool

/*
Design notes:
- Target DB: PostgreSQL (use SERIAL/UUID options as preferred)
- Use UUIDs for publicly-referencable IDs; integer PKs for internal joins are fine.
- Strong use of foreign keys, unique constraints, and indexes for performance.
- Audit logging table captures who changed what when.
- Approval/workflow modeled with states and history tables.
- Add-on features implemented as additional tables, triggers and helper functions / views.
- Adjust data types and indexes depending on scale.
*/

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =========
-- Lookup / ENUMS
-- =========

CREATE TYPE doc_status AS ENUM ('draft','active','under_review','obsolete','archived');
CREATE TYPE doc_type AS ENUM ('policy','sop','work_instruction','form','template','manual','guideline');
CREATE TYPE confidentiality_level AS ENUM ('public','internal','restricted','confidential');
CREATE TYPE review_outcome AS ENUM ('accepted','rejected','rework_required');
CREATE TYPE training_method AS ENUM ('on_job','classroom','e_learning','assessment');
CREATE TYPE approval_state AS ENUM ('pending','approved','rejected','escalated');
CREATE TYPE notification_type AS ENUM ('review_due','approval_requested','training_pending','expiry_alert');
CREATE TYPE contact_method AS ENUM ('email','sms','both');
CREATE TYPE risk_level AS ENUM ('low','medium','high');

-- =========
-- Core user / org tables
-- =========

CREATE TABLE departments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL UNIQUE,
  code TEXT,
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  username TEXT NOT NULL UNIQUE,
  email TEXT NOT NULL UNIQUE,
  phone TEXT,
  full_name TEXT NOT NULL,
  role TEXT,
  department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
  contact_preference contact_method DEFAULT 'email',
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE TABLE roles (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE user_roles (
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  role_id UUID REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

-- =========
-- Documents master register
-- =========

CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_code TEXT NOT NULL UNIQUE, -- e.g., SOP-CHM-001
  title TEXT NOT NULL,
  doc_type doc_type NOT NULL DEFAULT 'sop',
  department_id UUID REFERENCES departments(id),
  document_owner_id UUID REFERENCES users(id), -- owner for responsibility
  current_version_id UUID,
  status doc_status NOT NULL DEFAULT 'draft',
  confidentiality confidentiality_level NOT NULL DEFAULT 'internal',
  distribution_list JSONB, -- array of users/departments
  location_path TEXT, -- path to file storage or LIMS link
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  review_interval_days INTEGER DEFAULT 365, -- default 1 year
  last_review_date TIMESTAMP WITH TIME ZONE,
  notes TEXT
);

-- =========
-- Document versions
-- =========

CREATE TABLE document_versions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  version_label TEXT NOT NULL, -- e.g., V1.0, V2.1
  effective_date DATE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  created_by UUID REFERENCES users(id),
  change_summary TEXT,
  change_reason TEXT,
  file_path TEXT, -- link to stored copy
  file_checksum TEXT,
  is_locked BOOLEAN DEFAULT FALSE,
  is_current BOOLEAN DEFAULT FALSE,
  review_due_date DATE,
  meta JSONB
);

CREATE UNIQUE INDEX uq_document_version_per_label ON document_versions(document_id, version_label);
CREATE INDEX idx_doc_versions_document_id ON document_versions(document_id);

ALTER TABLE documents ADD CONSTRAINT fk_documents_current_version FOREIGN KEY (current_version_id) REFERENCES document_versions(id) ON DELETE SET NULL;

-- =========
-- Change Requests / Change Control
-- =========

CREATE TABLE change_requests (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  change_request_number TEXT NOT NULL UNIQUE,
  document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
  requested_by UUID REFERENCES users(id),
  requested_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  summary TEXT NOT NULL,
  details TEXT,
  impact_assessment TEXT,
  priority TEXT,
  status TEXT DEFAULT 'requested',
  review_outcome review_outcome,
  reviewer_id UUID REFERENCES users(id),
  reviewed_at TIMESTAMP WITH TIME ZONE,
  approved_by UUID REFERENCES users(id),
  approved_at TIMESTAMP WITH TIME ZONE,
  implemented BOOLEAN DEFAULT FALSE,
  implemented_at TIMESTAMP WITH TIME ZONE,
  linked_version_id UUID REFERENCES document_versions(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX idx_cr_document_id ON change_requests(document_id);

-- =========
-- Approval workflow & signatures (enhanced)
-- =========

CREATE TABLE approval_workflows (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  step_order INTEGER NOT NULL,
  approver_role_id UUID REFERENCES roles(id),
  approver_user_id UUID REFERENCES users(id),
  state approval_state DEFAULT 'pending',
  comments TEXT,
  acted_at TIMESTAMP WITH TIME ZONE,
  acted_by UUID REFERENCES users(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  UNIQUE (document_id, version_id, step_order)
);

-- Digital signatures table (full workflow)
CREATE TABLE digital_signatures (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  workflow_step_id UUID REFERENCES approval_workflows(id) ON DELETE SET NULL,
  user_id UUID REFERENCES users(id),
  signed_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  signature_hash TEXT,
  signature_certificate TEXT, -- optional cert details
  ip_address TEXT,
  signature_method TEXT, -- e.g., x509, otp
  signature_metadata JSONB
);

-- =========
-- Approval routing matrix
-- =========

CREATE TABLE approval_routing_matrix (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  doc_type doc_type NOT NULL,
  department_id UUID REFERENCES departments(id),
  min_role_id UUID REFERENCES roles(id), -- minimum role required to approve
  max_role_id UUID REFERENCES roles(id),
  route_json JSONB, -- ordered list of roles/users defining route, e.g. [{"step":1,"role":"supervisor"}, ...]
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- =========
-- Training & Acknowledgement
-- =========

CREATE TABLE document_training (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id) ON DELETE CASCADE,
  trainer_id UUID REFERENCES users(id),
  training_method training_method,
  date_trained DATE,
  competency_score NUMERIC(5,2),
  pass_fail BOOLEAN,
  acknowledgement BOOLEAN DEFAULT FALSE,
  evidence_file TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE INDEX idx_training_user_doc ON document_training(user_id, document_id);

-- =========
-- Distribution log
-- =========

CREATE TABLE document_distribution (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  distributed_to_user_id UUID REFERENCES users(id),
  distributed_to_department_id UUID REFERENCES departments(id),
  distributed_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  method TEXT,
  acknowledged BOOLEAN DEFAULT FALSE,
  acknowledged_at TIMESTAMP WITH TIME ZONE,
  notes TEXT
);

-- =========
-- Archive register
-- =========

CREATE TABLE document_archive (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  archived_by UUID REFERENCES users(id),
  archived_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  reason TEXT,
  archive_location TEXT
);

-- =========
-- Risk Assessment
-- =========

CREATE TABLE document_risks (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  associated_process TEXT,
  identified_risk TEXT,
  risk_level risk_level DEFAULT 'medium',
  mitigation_plan TEXT,
  responsible_person_id UUID REFERENCES users(id),
  status TEXT DEFAULT 'open',
  reviewed_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- =========
-- Notifications / Reminders (Automated reminder system)
-- =========

CREATE TABLE notifications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  document_id UUID REFERENCES documents(id),
  version_id UUID REFERENCES document_versions(id),
  type notification_type,
  payload JSONB,
  is_read BOOLEAN DEFAULT FALSE,
  sent_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Notification delivery log (records attempts to send email/SMS)
CREATE TABLE notification_deliveries (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  notification_id UUID REFERENCES notifications(id) ON DELETE CASCADE,
  provider TEXT, -- e.g., twilio, sendgrid
  provider_message_id TEXT,
  method contact_method,
  status TEXT, -- sent/failed/pending
  response_code TEXT,
  response_body TEXT,
  attempted_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Scheduled reminders config (cron-like)
CREATE TABLE reminder_rules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  description TEXT,
  document_filter JSONB, -- e.g., {"days_before":30, "status":["active"]}
  days_before INTEGER DEFAULT 30, -- days before review_due_date to trigger
  recipients JSONB, -- e.g., {"roles":["qa_manager"], "users":["<uuid>"]}
  method contact_method DEFAULT 'email',
  enabled BOOLEAN DEFAULT TRUE,
  last_run TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- =========
-- Auto-expiry alerts for controlled forms
-- =========

CREATE TABLE controlled_forms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  expiry_date DATE,
  auto_expire BOOLEAN DEFAULT TRUE,
  expiry_alert_sent BOOLEAN DEFAULT FALSE,
  expiry_action JSONB, -- e.g., {"action":"disable_form","notify_roles":["supervisor"]}
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- =========
-- Integration with LIMS SOP library
-- =========

CREATE TABLE sop_library (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
  external_ref TEXT, -- unique id in SOP library
  canonical_path TEXT, -- path/url to SOP content
  format TEXT, -- pdf, html, markdown
  indexed BOOLEAN DEFAULT FALSE,
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Link table to allow multiple sop library entries per document
CREATE TABLE document_sop_links (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  sop_library_id UUID REFERENCES sop_library(id) ON DELETE CASCADE,
  linked_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- =========
-- Version comparison tool (store diffs or JSON patches)
-- =========

-- Store computed diffs (textual or JSON patch) between versions for quick access
CREATE TABLE version_diffs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  base_version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  new_version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  diff_format TEXT, -- text, json_patch
  diff TEXT, -- the actual diff content (could be compressed)
  generated_by UUID REFERENCES users(id),
  generated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

CREATE UNIQUE INDEX uq_version_diff_pair ON version_diffs(base_version_id, new_version_id);

-- Optional: helper function to compute diff can be implemented at application layer or with DB extensions.

-- =========
-- Document lifecycle audit trail (detailed)
-- =========

CREATE TABLE document_lifecycle_events (
  id BIGSERIAL PRIMARY KEY,
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  version_id UUID REFERENCES document_versions(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL, -- created, reviewed, approved, published, archived, training, distributed
  event_by UUID REFERENCES users(id),
  event_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  event_data JSONB
);

CREATE INDEX idx_lifecycle_doc ON document_lifecycle_events(document_id);

-- =========
-- Audit log (generic change tracking)
-- =========

CREATE TABLE audit_logs (
  id BIGSERIAL PRIMARY KEY,
  entity_type TEXT NOT NULL,
  entity_id UUID,
  action TEXT NOT NULL,
  changed_by UUID REFERENCES users(id),
  changed_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  change_summary TEXT,
  change_details JSONB
);

CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);

-- =========
-- Triggers & helper functions (examples)
-- =========

-- 1) Update updated_at
CREATE OR REPLACE FUNCTION fn_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_updated_at
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE PROCEDURE fn_update_timestamp();

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE PROCEDURE fn_update_timestamp();

-- 2) Ensure single current version
CREATE OR REPLACE FUNCTION fn_set_current_version()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.is_current THEN
    UPDATE document_versions
    SET is_current = FALSE
    WHERE document_id = NEW.document_id AND id <> NEW.id;

    UPDATE documents SET current_version_id = NEW.id WHERE id = NEW.document_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_document_versions_current
AFTER INSERT OR UPDATE ON document_versions
FOR EACH ROW
EXECUTE PROCEDURE fn_set_current_version();

-- 3) Log lifecycle events automatically when versions inserted/updated
CREATE OR REPLACE FUNCTION fn_log_version_lifecycle()
RETURNS TRIGGER AS $$
DECLARE
  actor UUID := NEW.created_by;
  evt JSONB := jsonb_build_object('version_label', NEW.version_label, 'change_summary', NEW.change_summary);
BEGIN
  INSERT INTO document_lifecycle_events(document_id, version_id, event_type, event_by, event_data)
  VALUES (NEW.document_id, NEW.id, 'version_created', actor, evt);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_log_version_lifecycle
AFTER INSERT ON document_versions
FOR EACH ROW
EXECUTE PROCEDURE fn_log_version_lifecycle();

-- 4) Generate notification when review_due_date approaches (example: mark notification row)
-- Note: actual scheduling (cron) should run application-side job that queries reminder_rules and inserts notifications.

-- Example view for documents due soon
CREATE VIEW v_documents_due_soon AS
SELECT d.id as document_id, d.document_code, d.title, dv.id as version_id, dv.version_label, dv.review_due_date,
       (dv.review_due_date - CURRENT_DATE) as days_to_review
FROM documents d
LEFT JOIN document_versions dv ON dv.id = d.current_version_id
WHERE dv.review_due_date IS NOT NULL
  AND (dv.review_due_date - CURRENT_DATE) <= 30
ORDER BY dv.review_due_date ASC;

-- =========
-- Sample procedural notes for implementers (how to wire features)
-- =========
-- Automated reminder system:
-- - A scheduled worker (cron, Celery, Sidekiq) should run daily. It will:
--   1) Query reminder_rules to determine rules.
--   2) Query v_documents_due_soon or controlled_forms for expiry.
--   3) Generate rows in notifications for targeted users/roles.
--   4) Push notification to providers and write notification_deliveries records.

-- Digital signature workflow:
-- - The approval_workflows table defines ordered steps.
-- - When a workflow step is acted on, create a digital_signatures row (if signed).
-- - Enforce state transitions at application layer; store cryptographic signature_hash and certificate metadata.

-- Document lifecycle audit trail:
-- - document_lifecycle_events stores each meaningful event for an immutable history (version created, approved, published, archived, training conducted, distribution).
-- - Audit logs capture low-level CRUD changes.

-- Approval routing matrix:
-- - approval_routing_matrix contains templates per doc type/department; when a new version is created the application populates approval_workflows using the active routing matrix.

-- Integration with LIMS SOP library:
-- - sop_library stores canonical references; link to documents via document_sop_links. The application can pull full text or render HTML stored at canonical_path.

-- Auto-expiry alerts for controlled forms:
-- - controlled_forms table holds expiry_date and expiry_action; scheduled worker should generate expiry notifications and optionally set document status to 'archived' or deactivate forms.

-- Version comparison tool:
-- - Compute diffs in the application (preferred) using libraries (diff-match-patch or unix diff) or store JSON patches in version_diffs. Expose API to render human-friendly comparison.

-- Security & Implementation considerations:
-- 1) Signing: signature_hash and signature_certificate must be stored securely; consider encrypting these columns.
-- 2) Notifications: do retries, exponential backoff; log provider responses in notification_deliveries.
-- 3) Access control: enforce role-based and document-level permissions in application; consider PostgreSQL row-level security.
-- 4) Compliance: retain audit logs and lifecycle events for the required retention period for accreditation.
-- 5) Scalability: consider partitioning audit and lifecycle tables by date.

-- =========
-- Sample helper queries (to be used by developers)
-- =========
-- 1) Documents due for review soon: SELECT * FROM v_documents_due_soon;
-- 2) Get pending approvals for a user: SELECT * FROM approval_workflows WHERE approver_user_id = '<uuid>' AND state = 'pending' ORDER BY step_order;
-- 3) Get notification deliveries for a notification: SELECT * FROM notification_deliveries WHERE notification_id = '<uuid>';
-- 4) Get lifecycle events for a document: SELECT * FROM document_lifecycle_events WHERE document_id = '<uuid>' ORDER BY event_at DESC;

-- End of extended schema
