# Requirements: Agentic SDLC - Automated Documentation Sync

**Document ID:** REQ-001  
**Version:** 1.0  
**Status:** Draft – Pending Approval  
**Source:** Jira KAN-1  
**Owner:** TBD

## 1. Overview and objectives

The project will identify changes in registered project artefacts, determine
which related SDLC documents may be affected, and propose updates so that
documentation remains consistent and up to date throughout the software
development lifecycle.

The authoritative user story is [KAN-1: Automatically synchronize SDLC
documentation when project artefacts change.](https://demo-capstone-github-copilot.atlassian.net/browse/KAN-1)
Its description is:

> As a project team member, I want the system to identify changes in project
> artefacts and determine which related SDLC documents need updating, so that
> project documentation remains consistent and up to date throughout the
> software development lifecycle.

The story is a Story in Jira project KAN. The requirements below include its
original acceptance criteria and the subsequent clarification decisions.
Clarifications have not been added to the Jira issue.

## 2. Scope and source-of-truth rules

### 2.1 Initial systems and artefacts

- **Jira:** project KAN, including user stories, story descriptions,
  acceptance criteria, issue status and metadata, and related tasks and bugs
  when introduced. Jira is authoritative for user stories and their acceptance
  criteria and is the source of truth for business requirements.
- **GitHub:** the capstone repository, including Python source files, Python
  unit and integration tests, Markdown documentation including `README.md`,
  configuration files, Git commits and pull request information. GitHub contains
  the committed mandatory Markdown deliverables required by the capstone.
- **Confluence:** the ADS space, including project documentation, requirements,
  architecture and design, implementation planning, code review, testing and
  QA, and release and deployment documentation. ADS is the central
  documentation workspace for SDLC documents and supporting records.

Initially, only KAN, the capstone repository and ADS are in scope. Unrelated
projects, repositories and spaces are not integrated. For Confluence updates,
only registered project documentation pages in ADS are in scope.

Corresponding GitHub and Confluence versions must remain consistent. Controlled
bidirectional synchronization must use one authoritative source per artefact
type. The authoritative source for every remaining artefact type has not yet
been specified. Each document must have an identifiable owner, version and
relationship with other artefacts.

### 2.2 SDLC document types

Only documents relevant to the project and its eight SDLC steps should be
created. The agreed document categories are:

1. **Requirements:** `requirements.md`, functional and non-functional
   requirements, acceptance criteria, assumptions and constraints.
2. **Architecture:** `architecture.md`, architecture diagrams, component
   descriptions, technology and data-flow documentation.
3. **Design review:** `design-review.md`, design review findings and agreed
   design decisions.
4. **Implementation planning:** `impl-plan.md`, development task breakdown,
   task dependencies and priorities.
5. **Implementation:** technical and Python implementation documentation,
   API documentation where applicable, and developer setup instructions.
6. **Review:** code review checklist and findings, and security and dependency
   review results.
7. **Verification:** test strategy, test plan, test scenarios, test cases,
   test data documentation, test execution report, test summary report and
   requirements traceability matrix.
8. **Pull request:** PR description, `CHANGELOG.md`, test evidence, known
   limitations, reviewer checklist and release notes where applicable.

Configurable templates may support additional document types in the future;
this is not specified as an initial deliverable.

## 3. Functional requirements

Nested bullets are part of the requirement identified by their parent bullet.

### 3.1 Artefact registry

- **FR-001:** Maintain a centralized artefact registry managed by the Python application.
- **FR-002:** Initially register Jira project KAN, the capstone GitHub repository and
  Confluence space ADS. Register individual artefacts as they are discovered
  or created.
- **FR-003:** Support manual registration and assisted discovery through available APIs.
- **FR-004:** Each entry must contain a unique artefact ID, name and type, source system,
  source-system ID, URL or repository path, current version or last-modified
  timestamp, related document IDs and dependencies, last detected change
  timestamp, and last successful synchronization status.

### 3.2 Change detection and event processing

- **FR-005:** Use event-driven change detection as the primary mechanism:
  - Jira webhooks notify the Python backend of relevant issue creation,
    updates and deletion.
  - GitHub webhooks identify relevant pushes and pull request events.
  - Confluence Cloud Automation triggers detect page publication, editing,
    deletion, moves and archiving or restoration. Where supported, use its
    Send Web Request action to notify the Python backend.
- **FR-006:** Detect relevant Jira story creation, description, acceptance criteria and
  requirement-field updates, story deletion, and creation or deletion of
  relevant issue links. Issue status and metadata are in scope; irrelevant
  metadata-only changes must not automatically trigger synchronization.
- **FR-007:** Detect pushes to tracked branches affecting registered Python source,
  Markdown documentation, tests or configuration files; merged pull requests;
  and relevant file deletions or renames.
- **FR-008:** Detect new documentation page publication, edits, deletion, archiving,
  restoration and moves in Confluence.
- **FR-009:** Ignore page views, likes and reactions, unrelated comments, unrelated file
  changes and irrelevant metadata-only changes unless they affect a registered
  artefact or its dependencies.
- **FR-010:** Validate incoming webhook requests, identify the actual changed fields or
  files, prevent duplicate processing, safely handle simultaneous and repeated
  events, avoid repeatedly processing system-generated updates, and prevent
  infinite synchronization loops. Record processing outcomes and failures.
- **FR-011:** Provide an authorized user with a manual synchronization trigger for checks,
  testing and recovery.
- **FR-012:** Use periodic reconciliation as a secondary recovery mechanism to compare
  registered artefacts with their last known versions and identify changes
  missed during failed or unavailable webhook delivery. The initial interval
  is 15 minutes and must be configurable. Webhooks remain primary.

### 3.3 Dependencies and impact analysis

- **FR-013:** Maintain a centralized, persistent dependency registry managed by the
  Python application. Record the source artefact, dependent artefact,
  relationship type and metadata for each dependency.
- **FR-014:** Suggest dependencies using artefact analysis; authorized project members
  can review, approve and modify them. Record dependency changes for
  traceability.
- **FR-015:** Support direct and indirect, transitive dependencies and impact propagation.
  Detect and flag cycles and prevent infinite processing or synchronization
  loops.
- **FR-016:** Identify affected artefacts and documents before proposing updates, using
  recorded direct and indirect dependencies, artefact type and changed fields
  or files, requirement-to-design-to-code-to-test traceability, and
  AI-assisted analysis for additional potential impacts. Avoid flagging
  unrelated documents.
- **FR-017:** Generate an impact report containing:
  - Change ID and timestamp, changed source artefact and identifier, and a
    summary of the detected change.
  - Affected document IDs, titles and links; the reason for each impact;
    direct or indirect dependency information; and a recommended action.
  - High, Medium or Low severity with an explanation, confidence level and
    synchronization status. Severity is rule-based; numerical scoring is not
    initially required.
- **FR-018:** Store impact reports as pages under a dedicated Impact Analysis section in
  Confluence ADS. Link reports to the relevant Jira issue, GitHub commit or
  pull request. Generate the report before proposed document updates are
  published.

### 3.4 Proposed updates and review

- **FR-019:** Generate documentation update proposals using provider-independent
  AI-assisted analysis. The runtime AI provider is to be selected during
  Architecture; GitHub Copilot remains the SDLC development assistant.
- **FR-020:** Use only authorized, relevant project information: the changed artefact and
  its changes, current affected-document versions, relevant Jira requirements
  and acceptance criteria, related GitHub code, commits and pull requests,
  approved Confluence documentation, dependency relationships, and existing
  document templates and standards. Do not include secrets or sensitive
  information.
- **FR-021:** Store structured, review-friendly proposals as pending updates associated
  with the affected documents. Each proposal must include a summary, reason,
  affected document and link, specific sections to modify, before-and-after
  content, references to source changes, and assumptions or uncertainties.
- **FR-022:** Authorized document owners or designated project reviewers must be able to
  review, approve or reject each proposal. Review takes place in Confluence
  ADS; GitHub pull requests are used for repository changes.
- **FR-023:** All cross-system updates require authorized human approval. Approved changes
  may then be published; rejected proposals must not modify the original
  documents and the rejection reason must be recorded. An edited proposal
  requires another approval.
- **FR-024:** Detect stale proposals and version conflicts. Regenerate using the latest
  version and obtain reapproval before publishing. Record all review decisions.
- **FR-025:** Preserve unrelated document content. Do not blindly update unrelated
  documents or silently overwrite conflicting changes.

### 3.5 Publication and rollback

- **FR-026:** After approval, update the relevant registered Confluence ADS pages by
  modifying the specific affected sections rather than replacing entire pages.
  Preserve formatting, tables, links, unrelated content and Confluence page
  history.
- **FR-027:** Detect concurrent edits using page versions. On conflict, pause the affected
  update, regenerate the proposal using the latest version and require
  reapproval. Full-page replacement is permitted only with explicit approval.
- **FR-028:** Support rollback to the previous approved document version by an authorized
  user, subject to approval by an authorized document owner. Preserve previous
  versions and record every rollback in the audit history.

### 3.6 Synchronization records

**FR-029:** Persist audit records containing:

- Source artefact and version, detected change and timestamp.
- Generated proposal and affected documents.
- Reviewer identity and approval or rejection decision.
- Published document version and timestamp.
- Synchronization status, errors, retry history and final outcomes.
- Previous and updated document content.
- Dependency changes, privileged actions and rollback actions.

**FR-030:** Preserve Confluence page history. Audit retention must be configurable in
accordance with organizational policies; no fixed retention period is
specified.

### 3.7 Failure handling

- **FR-031:** Mark missing pages as **Not Found** and notify the document owner. Do not
  automatically create replacements.
- **FR-032:** Stop the affected update on permission failures and notify the authorized
  owner or administrator.
- **FR-033:** Retry temporary API failures with configurable exponential backoff and a
  maximum of three retries. Record each attempt.
- **FR-034:** Record permanent failures and escalate them to the responsible owner.
- **FR-035:** Process affected pages independently: failure of one page must not block
  updates to other eligible pages. Clearly report and record failures and
  final outcomes.

## 4. Non-functional requirements

- **NFR-001 — Reliability:** use idempotent event processing; duplicate events must not
  cause duplicate processing or repeated document updates. Reconciliation
  must identify missed events. Retry behavior must be configurable within the
  agreed maximum.
- **NFR-002 — Responsiveness:** aim for near-real-time detection-to-report using
  webhooks and prompt asynchronous publication after approval. Exact targets
  remain deferred.
- **NFR-003 — Availability:** best effort for the capstone, subject to external service
  availability. No numerical availability target has been agreed.
- **NFR-004 — Traceability:** retain the records in section 3.6 and explain impact
  classifications and affected-document relationships.
- **NFR-005 — Integrity:** preserve unrelated content and page history, detect concurrent
  changes and prevent silent overwrites.
- **NFR-006 — Security:** apply the requirements in section 6.

## 5. Business rules and technology constraints

- Jira is authoritative for user stories and acceptance criteria. GitHub
  contains the committed mandatory Markdown deliverables; ADS is the central
  documentation workspace. Controlled bidirectional synchronization requires
  one authoritative source per artefact type.
- A human authorized for the document must review and approve proposed
  cross-system updates before publication. Rejected or stale proposals must
  not be published; revised proposals require reapproval.
- Use Python for application logic, backend services, synchronization logic
  and automated tests. Do not introduce Node.js for application
  implementation or a Node.js or Forge application just for event handling.
- The original Jira constraint permits a Node.js runtime only if technically
  necessary and explicitly approved. The subsequent instruction prohibits
  Node.js for application implementation; no such exception is approved.
  GitHub Copilot configuration files and documentation may use their required
  native formats.

## 6. Security and access requirements

- **NFR-007:** Use role-based access control:
  - Administrators configure integrations and manage permissions.
  - Project members view registered artefacts and synchronization reports.
  - Document owners or designated reviewers approve or reject proposals.
  - An authorized service account publishes approved Confluence changes.
- **NFR-008:** Use secure OAuth-based authentication and least-privilege API permissions.
  Authenticate and audit all privileged actions. Exact authentication details
  and permission scopes are deferred to Architecture.
- **NFR-009:** Store credentials and secrets securely using environment variables or an
  approved secret manager. Do not read or expose secrets, credentials,
  environment files or sensitive configuration values as project artefacts.
- **NFR-010:** Never expose passwords, API tokens, credentials or sensitive personal
  information in generated documents, logs or reports. Only authorized and
  relevant information may be used for proposal generation.

## 7. Original Jira acceptance criteria

The following are reproduced from KAN-1:

**AC1:** The system should identify changes in registered project artefacts.

**AC2:** The system should identify related SDLC documents using their recorded dependencies.

**AC3:** The system should provide an impact report identifying potentially affected documents.

**AC4:** The system should generate proposed documentation updates based on the changes.

**AC5:** Proposed updates must be reviewed and approved by an authorized human before publishing.

**AC6:** Once approved, the system should update the relevant Confluence documentation.

**AC7:** The system should record synchronization results and handle missing documents, permission failures and API errors gracefully.

The clarified requirements in this document supplement these original criteria;
they have not changed the Jira issue.

## 8. Error and edge-case handling

The agreed handling includes:

- Missing, deleted or archived pages: detect relevant events; for missing pages,
  record Not Found, notify the owner and do not create a replacement.
- Permission failures and temporary or permanent API failures: stop the
  affected update, notify or escalate as appropriate, and record outcomes;
  retry temporary failures as specified in section 3.7.
- Duplicate, repeated or simultaneous events and system-generated changes:
  process safely and idempotently, avoiding repeated updates and loops.
- Cyclic dependencies: detect and flag them and prevent infinite propagation.
- Rejected, edited or stale proposals and concurrent page edits: follow the
  review, conflict and reapproval rules in sections 3.4 and 3.5.
- Unrelated content or documents: do not update them blindly; preserve unrelated
  page content.
- Partial failure: continue processing other eligible affected pages.
- Missed webhook deliveries: identify missed changes through periodic
  reconciliation; an authorized user can also trigger a manual check.

## 9. Confirmed planning assumptions

- Initial usage covers one Jira project, one GitHub repository and one
  Confluence space, with low to moderate event volumes.
- Availability is best effort and depends on external service availability.
- Only project-relevant documents from the eight SDLC steps will be created;
  API documentation and release notes apply where relevant.

## 10. Deferred decisions and unresolved questions

### Explicitly deferred

- Persistent storage technology for the artefact registry, dependency
  registry and audit records: Architecture.
- Runtime AI provider and exact OAuth authentication and permission scopes:
  Architecture.
- Audit retention periods: configurable according to organizational policy;
  the actual periods remain to be established.
- Measurable performance, event-volume and availability targets:
  Architecture and Verification based on practical measurements.

### Still unresolved

- The exact GitHub repository identifier and tracked branches.
- The authoritative source for each artefact type beyond the Jira rules
  stated above, and the detailed cross-system synchronization direction and
  conflict-resolution procedure for each type.
- The specific rule thresholds for High, Medium and Low impact severity and
  how confidence levels are determined.
- How approval of cross-system updates applies to creating impact report
  pages and how that interacts with report generation before publication.
- The exact retry backoff values, webhook validation method, reconciliation
  implementation, and mechanisms for notifications and escalation.
- How Confluence review decisions and GitHub pull request approvals are
  linked to individual proposals and how rollback approval is captured.

These items are not implied decisions or additional requirements.
