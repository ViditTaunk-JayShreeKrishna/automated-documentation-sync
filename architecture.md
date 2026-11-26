# Architecture: Agentic SDLC - Automated Documentation Sync

**Status:** Proposed - Pending Design Review  
**Source:** [Approved requirements](requirements.md), [Jira KAN-1](https://demo-capstone-github-copilot.atlassian.net/browse/KAN-1)

## 1. Purpose and scope

This proposal describes a high-level architecture for detecting changes in
registered artefacts, analyzing their impact, generating reviewable proposals
and synchronizing approved changes. It is based on the approved requirements;
recommendations in this document are not additional approved requirements.

The initial integration boundary is Jira project KAN, one capstone GitHub
repository and Confluence space ADS. The GitHub repository identifier and
tracked branches must be configured once confirmed. No unrelated projects,
repositories or spaces are included.

Jira is authoritative for business requirements, user stories and acceptance
criteria. GitHub holds mandatory committed Markdown deliverables; ADS is the
central documentation workspace. Controlled bidirectional synchronization
requires an authoritative source per artefact type. Where authority is not
yet defined, the system must not guess or silently overwrite either side.

## 2. Architecture overview and recommended system architecture

Use a **Python modular monolith**: one application codebase with explicit
component interfaces, deployed as an API process and a background worker
process. The worker also runs the reconciliation scheduler. Both processes
use a shared PostgreSQL database for durable state and work coordination.
They communicate through database-backed work records, not an external
message broker. External systems are accessed through separate adapters.

This keeps deployment small while isolating responsibilities and allowing
the webhook receiver to acknowledge requests without waiting for analysis,
AI generation, human review or publication.

### Component architecture diagram

This view shows the proposed Python application's logical components, its
database, external integrations and human actors. Arrows trace events and
work from the receiver through analysis, review, synchronization and audit;
two-way arrows denote data exchange. The external-source arrows summarize
both inbound events and application-initiated REST reads: REST reads are
requests from the application to the external system, with responses in the
opposite direction. The view matters because it exposes the approval boundary
and shared durable state without implying separate services for each component.

<details>
<summary>Original component diagram source (preserved)</summary>

```mermaid
flowchart LR
    Jira["Jira KAN"] -->|webhooks and REST reads| Receiver
    GitHub["GitHub repository"] -->|webhooks and REST reads| Receiver
    Conf["Confluence ADS"] -->|Automation web requests and REST reads| Receiver
    Users["Authorized users"] -->|HTTPS| API

    subgraph App["Python application"]
        Receiver["Webhook Receiver"] --> Change["Change Detection Service"]
        API["API and review interface"] --> Change
        Scheduler["Reconciliation Scheduler"] --> Change
        Change --> Jobs["Durable work records"]
        Jobs --> Impact["Impact Analysis Engine"]
        Registry["Artefact Registry"] <--> Impact
        Deps["Dependency Registry"] <--> Impact
        Impact --> Reports["Impact reports"]
        Impact --> Generator["AI Proposal Generator"]
        Generator --> Approval["Approval Management"]
        Approval --> Sync["Synchronization Engine"]
        Sync --> Audit["Audit and Rollback Manager"]
        Change --> Audit
        Impact --> Audit
        Approval --> Audit
    end

    Jobs <--> DB[("PostgreSQL")]
    Registry <--> DB
    Deps <--> DB
    Reports <--> DB
    Approval <--> DB
    Audit <--> DB
    Generator -->|provider adapter| AI["Runtime AI provider"]
    Impact -->|approved report publication policy| Conf
    Approval <-->|review evidence| Conf
    Sync -->|approved page updates| Conf
    Sync -->|approved repository workflow| GitHub
    Audit -->|authorized, approved rollback| Conf
```

</details>

The grouped view below depicts the same components and relationships. Repeated
labels in different groups represent the same logical component or external
system, not additional services, databases or integrations. The groups
separate processing, external communication, storage and auditing to make
individual connections easier to follow.

```mermaid
flowchart TB
    subgraph Flow["Python application: processing and approval"]
        direction TB
        Receiver["Webhook Receiver"] --> Change["Change Detection Service"]
        API["API and review interface"] --> Change
        Scheduler["Reconciliation Scheduler"] --> Change
        Change --> Jobs["Durable work records"]
        Jobs --> Impact["Impact Analysis Engine"]
        Registry["Artefact Registry"] <--> Impact
        Deps["Dependency Registry"] <--> Impact
        Impact --> Reports["Impact reports"]
        Impact --> Generator["AI Proposal Generator"]
        Generator --> Approval["Approval Management"]
        Approval --> Sync["Synchronization Engine"]
    end

    subgraph Inbound["External inputs"]
        direction LR
        JiraIn["Jira KAN"] -->|webhooks and REST reads| ReceiverIn["Webhook Receiver"]
        GitHubIn["GitHub repository"] -->|webhooks and REST reads| ReceiverIn
        ConfIn["Confluence ADS"] -->|Automation web requests and REST reads| ReceiverIn
        Users["Authorized users"] -->|HTTPS| APIIn["API and review interface"]
    end

    subgraph Outbound["External interactions"]
        direction LR
        GeneratorOut["AI Proposal Generator"] -->|provider adapter| AI["Runtime AI provider"]
        ImpactOut["Impact Analysis Engine"] -->|approved report publication policy| ConfReport["Confluence ADS"]
        ApprovalOut["Approval Management"] <-->|review evidence| ConfReview["Confluence ADS"]
        SyncOut["Synchronization Engine"] -->|approved page updates| ConfUpdate["Confluence ADS"]
        SyncRepo["Synchronization Engine"] -->|approved repository workflow| GitHubOut["GitHub repository"]
        AuditOut["Audit and Rollback Manager"] -->|authorized, approved rollback| ConfRollback["Confluence ADS"]
    end

    subgraph State["Shared durable state"]
        direction LR
        JobsDB["Durable work records"] <--> DB[("PostgreSQL")]
        RegistryDB["Artefact Registry"] <--> DB
        DepsDB["Dependency Registry"] <--> DB
        ReportsDB["Impact reports"] <--> DB
        ApprovalDB["Approval Management"] <--> DB
        AuditDB["Audit and Rollback Manager"] <--> DB
    end

    subgraph AuditFlow["Audit connections"]
        direction LR
        ChangeAudit["Change Detection Service"] --> Audit["Audit and Rollback Manager"]
        ImpactAudit["Impact Analysis Engine"] --> Audit
        ApprovalAudit["Approval Management"] --> Audit
        SyncAudit["Synchronization Engine"] --> Audit
    end

    Flow ~~~ Inbound
    Inbound ~~~ Outbound
    Outbound ~~~ State
    State ~~~ AuditFlow
```

![Component architecture diagram](component-architecture.png)

Arrows show logical communication, not independent deployable services. All
external writes, including report and review artefact creation, remain subject
to the approved cross-system authorization policy; the unresolved
report-publication question in section 12 must be settled before those writes
are automated.

## 3. Technology recommendations

| Area | Recommendation | Reason |
| --- | --- | --- |
| Application and tests | Python for all application logic, backend services, synchronization and automated tests | Meets the language constraint and supports the integrations in one ecosystem. No Node.js application runtime is introduced. |
| HTTP API | FastAPI with Pydantic validation and an ASGI server such as Uvicorn | Supports typed request validation, webhook endpoints and an authenticated review interface without a separate frontend runtime. |
| External HTTP | HTTPX through Jira, GitHub, Confluence and AI provider adapters | Provides a consistent Python HTTP client, timeouts and testable integration boundaries. |
| Database | PostgreSQL, accessed through SQLAlchemy and managed migrations such as Alembic | Provides persistent relational records, transactions, constraints and row-level locking for registries, approvals, audit and durable jobs without a separate queue. |
| Scheduling | A Python scheduler such as APScheduler in the worker, with database-backed coordination | Supports configurable periodic reconciliation while avoiding an additional scheduler service. Execution ownership must be coordinated if more than one worker is deployed. |
| Automated verification | pytest and Python HTTP mocks or fakes | Supports unit and integration testing of workflow, adapters, error paths and approval boundaries without external calls in unit tests. |
| Packaging and deployment | Python containers, or equivalent managed Python processes, with a persistent PostgreSQL service | Provides reproducible deployment while keeping API and worker in the same codebase. Containerization is a deployment option, not a Node.js dependency. |
| Operations | Structured Python logging, health checks and the chosen hosting platform's monitoring | Provides basic observability without assuming a separate monitoring stack. Logs must not expose secrets or sensitive personal information. |

These are recommendations for review. Exact versions, hosting provider, OAuth
scopes, runtime AI provider and retention periods remain to be decided.

## 4. Component responsibilities and communication

| Component | Responsibility and communication |
| --- | --- |
| **Artefact Registry** | Stores registered sources and artefacts, their identifiers, type, location, owner where applicable, versions, related documents, last detected change and last successful synchronization status. Supports authorized manual registration and assisted API discovery. Other components query it through an internal repository interface. |
| **Dependency Registry** | Stores directed source-to-dependent relationships, relationship types and metadata. Authorized members review, approve and modify suggested dependencies. Traversal supports direct and transitive impacts, detects cycles and records changes for audit. |
| **Webhook Receiver** | Exposes HTTPS endpoints for configured sources. Authenticates and validates requests, limits processing to configured scope and durably records accepted events before acknowledging them. It hands work to the Change Detection Service; it does not publish documents. |
| **Change Detection Service** | Normalizes accepted events and manual or reconciliation discoveries; compares source versions and relevant fields or files; filters irrelevant activity; deduplicates changes and prevents self-triggered loops. It creates durable impact-analysis work and records outcomes. |
| **Reconciliation Scheduler** | Starts a comparison of registered artefacts with known versions every 15 minutes by default, configurable. It submits missed changes to the same detection path. An authorized manual check uses that path too. |
| **Impact Analysis Engine** | Traverses approved dependency records, including transitive paths, combines changed-field or file information with requirement-to-design-to-code-to-test traceability, and considers AI-suggested additional impacts. It records reasons, direct or indirect paths, severity, confidence, recommended action and synchronization status for the report. Unknown severity or confidence rules remain unresolved rather than silently invented. |
| **AI Documentation Proposal Generator** | Uses a provider adapter and authorized, relevant context to produce structured, reviewable before-and-after proposals with source references and uncertainties. It cannot approve or publish changes. |
| **Approval Management** | Associates each proposal with the document owner or designated reviewer, a specific proposed change and relevant source and target versions. It records authenticated approval, rejection and reason, invalidates approval after edits or staleness, and exposes review information in ADS with GitHub pull requests for repository changes. |
| **Synchronization Engine** | Processes each approved target independently, rechecks authorization, approval and versions, and applies approved changes through the relevant adapter. It preserves unrelated content and formatting, detects conflicts and records each outcome. It does not publish a rejected, stale or unapproved update. |
| **Audit and Rollback Manager** | Persists required change, proposal, decision, version, failure, retry and privileged-action records; coordinates restoration of a previous approved version after authorized document-owner approval; and records the rollback. |
| **Integration adapters** | Encapsulate source-specific authentication, API calls, pagination, version checks and error classification. They return normalized results to the application and do not decide approval or authority policy. |
| **API and review interface** | Authenticates users, enforces RBAC, offers manual registration, discovery and synchronization controls, and presents status and review links. The precise ADS review and GitHub approval integration is unresolved. |

## 5. Integrations and source boundaries

### 5.1 Jira KAN

Use Jira Cloud REST APIs to discover and read permitted KAN issues, relevant
fields, descriptions, acceptance criteria, issue links and versions or
timestamps. Jira webhooks notify the receiver of relevant creates, updates and
deletes. Fetch and compare the relevant state to determine what changed; do
not assume every issue update changes requirements.

Treat Jira requirements and acceptance criteria as authoritative. Other issue
types, status and metadata are in scope when relevant. Jira write behavior for
other artefact types must not be assumed from this authority rule.

### 5.2 GitHub

Use GitHub APIs to read permitted repository files, commits, pull requests and
relevant change details. GitHub webhooks notify the receiver of pushes and
pull request events; process only configured branches and registered relevant
paths. Track renames and deletions. Repository changes use GitHub pull
requests and require the approved human workflow.

The precise authoritative-source mapping and the relationship between
cross-system approval, pull request creation and pull request approval remain
open. Do not write to a repository or treat an unmerged change as
authoritative until the applicable policy is established.

### 5.3 Confluence ADS

Use Confluence Cloud APIs to discover and read registered ADS pages, their
content and versions, and to update approved affected sections while
preserving supported rich content and page history. Confluence Cloud
Automation is the proposed event source for publication, edits, deletion,
moves, archiving and restoration; where supported, Send Web Request notifies
the Python receiver. Confirm available triggers, authentication and payload
capabilities for the actual site. Reconciliation is the recovery path for
missed events, not a substitute for an unconfigured primary mechanism.

Impact reports belong under a dedicated ADS Impact Analysis section. Review
also takes place in ADS. Their precise creation and approval mechanics are
unresolved; no automatic report or review-page write should bypass the
cross-system approval rule. The mechanism for capturing and validating
Confluence review decisions must be confirmed.

## 6. End-to-end data flow

### End-to-end data-flow diagram

This view follows a change from a webhook, manual check or reconciliation
through impact analysis, proposal, human review, publication and audit.
Arrows show the progression; the rejection branch stops publication, while
edits, staleness and conflicts return to review. It matters because every
path to a document update passes the approval and version-check boundary.

```mermaid
flowchart TD
    A["Webhook, manual check or 15-minute reconciliation"] --> B["Validate, scope and record event"]
    B --> C["Compare versions and relevant changed fields or files"]
    C --> D["Deduplicate; record change and durable work"]
    D --> E["Traverse dependencies and assess potential impacts"]
    E --> F["Prepare impact report with reasons and links"]
    F --> G["Generate section-level proposal with source and target versions"]
    G --> H["Authorized human review"]
    H -->|reject| I["Record reason; do not change document"]
    H -->|edit or stale| J["Regenerate or revise; request reapproval"]
    J --> H
    H -->|approve| K["Recheck authority, permissions, versions and approval"]
    K -->|conflict| J
    K -->|valid| L["Publish approved update per target"]
    L --> M["Record result, versions and audit history"]
    M --> N["Reconcile later and suppress self-generated loops"]
```

![End-to-end data-flow diagram](end-to-end-data-flow.png)

1. A validated event, authorized manual check or reconciliation identifies a
   change. The receiver persists accepted event identity before acknowledgment;
   the worker retrieves the relevant permitted source state.
2. The change detector filters non-relevant activity, compares versions and
   deduplicates the work. The registries provide the artefact, owner and
   approved dependency information.
3. The impact engine traverses direct and transitive relationships with cycle
   detection, adds explainable potential impacts and prepares the required
   report. Report creation in ADS follows the policy to be resolved in
   section 12. The report must be generated before proposed document updates
   are published.
4. The proposal generator uses authorized relevant context and the current
   target version to produce a structured comparison. It stores the proposal
   as pending, not as an edit to the source document.
5. An authorized owner or designated reviewer reviews each proposal in the
   agreed ADS workflow; repository changes use a GitHub pull request. Approval
   is tied to the exact proposal and versions. Rejection records the reason;
   edits or staleness require a revised proposal and fresh approval.
6. Before publishing, the synchronization engine checks authority, the
   reviewer decision, source and target versions and permissions. It updates
   only approved sections of registered ADS pages, or follows the approved
   repository workflow. A conflict pauses the affected target and returns it
   for regeneration and reapproval.
7. The audit manager records the source, proposal, decision, before-and-after
   content, versions, outcome and errors. Other eligible targets continue if
   one fails. Reconciliation and loop suppression prevent missed or repeated
   work from becoming silent inconsistencies.

### Jira, GitHub and Confluence interaction sequence

This illustrative sequence shows the three external systems, the Python
application, the provider-independent AI interface and an authorized reviewer.
Messages run from sender to receiver in time order. Events initiate processing;
application-initiated reads provide context; review evidence and version checks
precede any approved update. The optional report and review publication step
is conditional on the unresolved authorization policy, and the precise review
mechanism is not assumed. This view matters because it distinguishes source
events, contextual reads and controlled writes across system boundaries.

```mermaid
sequenceDiagram
    participant Jira as Jira KAN
    participant GitHub as GitHub repository
    participant ADS as Confluence ADS
    participant App as Python application
    participant AI as Runtime AI provider
    actor Reviewer as Authorized reviewer

    alt Relevant Jira change
        Jira->>App: Webhook event
    else Relevant GitHub change
        GitHub->>App: Webhook event
    else Relevant Confluence change
        ADS->>App: Automation web request, where supported
    end
    App->>Jira: Read relevant requirements and versions
    Jira-->>App: Authorized issue context
    App->>GitHub: Read relevant files, commits or PRs
    GitHub-->>App: Authorized repository context
    App->>ADS: Read registered pages and versions
    ADS-->>App: Authorized document context
    App->>App: Detect change, analyze dependencies and prepare report
    App->>AI: Request impact assistance and proposal
    AI-->>App: Advisory output
    App->>App: Store pending proposal
    opt Report or review publication is authorized under the resolved policy
        App->>ADS: Make report or proposal available for review
    end
    Reviewer->>ADS: Review proposal
    ADS-->>App: Review evidence, mechanism to be confirmed
    alt Rejected, edited or stale
        App->>App: Record decision or regenerate and request reapproval
    else Approved and versions still match
        App->>ADS: Publish approved affected sections
        opt Repository update authorized under resolved policy
            App->>GitHub: Follow approved pull request workflow
        end
        App->>App: Record versions and synchronization outcome
    end
```

![Jira, GitHub and Confluence interaction sequence](integration-sequence.png)

## 7. Data storage and state

PostgreSQL is the recommended persistent store for:

- Registered systems and artefacts, source identifiers, paths or URLs, owner,
  versions, change timestamps and last successful synchronization status.
- Directed dependency edges, relationship metadata, review status and
  dependency-change history.
- Received event identities, normalized changes, durable jobs, leases,
  attempts and reconciliation checkpoints.
- Impact reports and their publication references, proposals with before-and-
  after content and source references, review decisions and target versions.
- Synchronization outcomes, errors, prior and published versions, rollback
  approvals and actions, and audit records.

Use database uniqueness constraints for stable event and job identities,
transactions for local state transitions, and row locks or leases to coordinate
workers. Store only authorized, relevant content; protect persisted proposal
and audit data as well as credentials. Retention is configurable according to
organizational policy. Back up the database and preserve Confluence page
history; backup and restore operational details require confirmation.

Confluence remains the workspace for reports and documentation; GitHub
remains the repository for committed deliverables. Database records support
coordination and audit and do not by themselves change source authority.
No separate object store, graph database or message broker is proposed
initially.

## 8. Security and access

- Use OAuth-based authentication for external integrations and authenticated
  application users. An authorized service identity publishes approved
  Confluence changes. Select actual OAuth flows, product capabilities and
  least-privilege scopes during design; do not assume permissions from access
  to a space or repository.
- Enforce RBAC at the application boundary and again at privileged workflow
  transitions: administrators manage integrations and permissions; project
  members view registry and reports; document owners or designated reviewers
  approve or reject; the authorized service account publishes. Verify the
  reviewer is authorized for the target document.
- Use HTTPS for incoming and outgoing traffic. Validate GitHub webhook
  signatures and use supported authentication and verification for Jira
  webhooks and Confluence Automation requests. Confirm each sender's actual
  capabilities, including replay protection; reject unauthenticated or
  unverifiable requests. Do not assume all senders use GitHub's signature
  scheme.
- Keep credentials in environment variables or an approved secret manager;
  limit access and never include secrets in artefact discovery, AI context,
  logs, reports or generated documents. Exclude environment files and
  sensitive configuration values. Protect audit data and reviewer identities
  against unauthorized disclosure while recording required actions.
- Limit AI context to authorized, relevant project information. Treat source
  content and model responses as untrusted; validate structured output and
  never let model text authorize an action or override human approval.

## 9. Reliability and failure handling

- Persist accepted event and work records before acknowledgment; use stable
  event identities, unique constraints and idempotent handlers to avoid
  duplicate work. Deduplicate reconciliation findings against already
  processed source versions as well as webhook deliveries.
- Handle simultaneous events with transactional state changes and per-target
  coordination. Before publication compare the approved source and target
  versions with current versions; use the external system's supported
  version or conditional-write mechanism. A mismatch pauses that target and
  requires regeneration and reapproval.
- Recognize system-originated writes by recorded operation and version
  information to avoid loops. Do not suppress later independent human edits.
- Retry transient API failures with configurable exponential backoff and at
  most three retries. Record each attempt and final outcome. Permanent
  failures are recorded and escalated to the responsible owner.
- For an ambiguous timeout after an external write, check the target and
  recorded operation before retrying; if the outcome cannot be established
  safely, stop and surface it rather than risk a duplicate or overwrite.
  Database transactions alone cannot guarantee exactly-once external writes.
- Missing pages are marked Not Found and the document owner is notified; do
  not create replacements automatically. Permission failures stop the
  affected update and notify the owner or administrator. Process other
  eligible pages independently.
- Reconcile registered artefacts every 15 minutes by default, with a
  configurable interval; record checkpoints and failures. Manual checks use
  the same safe, idempotent processing path. Availability is best effort;
  quantitative targets remain deferred.

### Failure handling and recovery flow

This view shows the synchronization engine's per-target failure paths and the
audit record. Arrows separate missing pages, permission failures, transient
API failures, uncertain write outcomes and version conflicts. Safe retries
return to the affected target; conflicts require a revised proposal and fresh
approval. Other eligible targets continue independently. This view matters
because recovery must not turn a failure into an unapproved or duplicate write.

```mermaid
flowchart TD
    A["Process one approved target"] --> B{"Outcome"}
    B -->|success| C["Record version and success"]
    B -->|missing page| D["Mark Not Found and notify owner"]
    B -->|permission failure| E["Stop target and notify owner or administrator"]
    B -->|temporary API failure| F{"Retries available?"}
    F --> G["Retries available: record attempt and back off"]
    G --> A
    F --> R["No retries available"]
    R --> H["Record failure and escalate"]
    B -->|permanent failure| H
    B -->|uncertain write outcome| I["Check target and recorded operation"]
    I -->|confirmed applied| C
    I -->|confirmed not applied and retry safe| F
    I -->|cannot establish safely| H
    B -->|version conflict| J["Pause target and regenerate proposal"]
    J --> K["Request fresh human approval"]
    C --> L["Record audit outcome"]
    D --> L
    E --> L
    H --> L
    K --> L
    L --> M["Continue other eligible targets independently"]
```

![Failure handling and recovery flow](failure-recovery-flow.png)

## 10. AI integration and development tools

The runtime application calls a **provider-independent AI interface** for
potential impact suggestions and documentation proposals. A provider adapter
maps authorized, minimized context to the selected provider and validates
the response into the application's structured proposal and impact formats.
The runtime provider, data-handling terms and detailed confidence method remain
to be selected. Rule-based severity is High, Medium or Low with an
explanation; exact classification rules are unresolved and numerical scoring
is not initially required.

AI output is advisory. Dependency records, source authority, access checks,
version checks and human approval remain application-controlled; the model
cannot publish or approve. If AI generation fails or produces unusable output,
record and surface the failure rather than publish an unreviewed substitute.

GitHub Copilot is the development assistant used during the SDLC. Atlassian
Rovo MCP is a development-workflow tool for interacting with Atlassian
resources. Neither is assumed to be the deployed application's runtime AI
provider or integration transport.

## 11. Deployment and operations

Deploy one Python API instance and one Python worker/scheduler instance from
the same application codebase, alongside a persistent PostgreSQL service.
Expose only the HTTPS API endpoints needed for authenticated users and
webhooks. Provide outbound access only to the configured Jira, GitHub,
Confluence and selected AI provider endpoints.

Configure the project and space boundaries, repository and tracked branches,
credentials, reconciliation interval and retry backoff through protected
configuration. Use a persistent database volume or managed database with
backup and recovery. Health checks and operational alerts should surface
failed jobs, reconciliation failures and unavailable dependencies without
logging secrets or sensitive personal information.

The initial deployment assumes low to moderate volume and best-effort
availability. Separate queues, multiple workers or additional infrastructure
are not required by this proposal; scaling or high-availability choices depend
on measured needs. If multiple workers are later used, scheduler ownership
and job leases must prevent duplicate execution.

### Deployment architecture diagram

This proposed deployment view separates the public HTTPS entry point, Python
API process, Python worker and scheduler, and persistent PostgreSQL service
from external users and integrations. Inbound arrows represent authenticated
user requests or validated events; outbound arrows represent API or AI calls;
database arrows represent shared durable state. The diagram matters because
background work and recovery remain separate from request handling without
requiring a separate message broker. The hosting environment and specific
authentication mechanisms remain unresolved.

```mermaid
flowchart LR
    Users["Authorized users"] -->|HTTPS| API["Python API process"]
    Sources["Jira, GitHub and Confluence events"] -->|HTTPS| API
    API <--> DB[("Persistent PostgreSQL")]
    Worker["Python worker and scheduler"] <--> DB
    Worker -->|authorized API calls and provider adapter| External["Jira KAN, GitHub, Confluence ADS and runtime AI provider"]
```

![Deployment architecture diagram](deployment-architecture.png)

## 12. Assumptions, decisions and open questions

### Planning assumptions

- The initial scope and low-to-moderate event volume are as stated in the
  approved requirements. External service availability affects the system.
- PostgreSQL, FastAPI, the scheduler, deployment model and provider adapter
  are recommendations, not already-approved technology decisions.
- The target integrations can provide the necessary access and event
  mechanisms; actual permissions, API behavior and Automation capabilities
  must be verified before implementation.

### Decisions requiring confirmation

- Exact repository identity, tracked branches and the authoritative source
  and permitted synchronization direction for every artefact type.
- Rules for High, Medium and Low impact severity, confidence levels and
  handling uncertain or AI-suggested impacts.
- Whether and how impact report and review artefact creation in ADS is
  authorized under the rule requiring human approval for all cross-system
  updates, while still generating reports before document publication.
- How ADS review decisions and GitHub pull request approvals are captured,
  authenticated and linked to proposals; when PR creation itself is
  permitted; and how document-owner rollback approval is captured.
- Supported OAuth flows and exact scopes, webhook authentication and replay
  controls for each sender, Confluence Automation trigger coverage and
  service-account permissions.
- Runtime AI provider, permitted data handling and operational controls.
- Exact retry backoff values, notification and escalation mechanisms,
  reconciliation implementation and deployment environment.
- Audit retention periods, backup and recovery details, and measurable
  performance, volume and availability targets. The requirements defer
  measurable targets to Architecture and Verification based on measurements.

Until these decisions are resolved, the architecture does not authorize
guessing source authority, bypassing approval or silently overwriting changes.

### Structured architectural decision summary

The approved requirements constrain the design, but the technology choices
below remain **recommendations**, not finalized decisions. Alternatives are
included for comparison; choosing one does not authorize additional scope.

| Topic | Approved constraint or need | Proposed approach and alternatives | Trade-off and status |
| --- | --- | --- | --- |
| Application organization | Python for application logic, backend services, synchronization and tests; no Node.js application implementation. | A Python modular monolith; separately deployed Python services are an alternative. | The monolith reduces deployment and coordination overhead at initial volume; separate services add operational complexity. **Proposed.** |
| Durable state and work | Registries and audit need persistent storage; work must be idempotent and recoverable. | PostgreSQL with database-backed work records; a relational database plus a separate queue is an alternative. | PostgreSQL supports transactions and coordination without an additional broker; a dedicated queue adds infrastructure and independent scaling. Storage technology was deferred to Architecture and remains **proposed**. |
| Change detection | Events are primary, with manual checks and configurable 15-minute reconciliation. | Webhooks and Confluence Automation where supported, backed by reconciliation; polling alone is an alternative recovery mechanism, not the approved primary approach. | Event delivery is prompt but depends on sender capabilities; reconciliation helps recover missed events. Integration details are **unresolved**. |
| Review and publication | Authorized human approval is required before cross-system updates; conflicts must not be silently overwritten. | Version-bound proposals with ADS review and GitHub pull requests; the exact approval and evidence mechanism remains to be determined. | Version checks protect against stale approvals, but report creation and review integration still need authorization rules. **Workflow details unresolved.** |
| Runtime AI | AI-assisted proposals must be provider-independent and use authorized, relevant data. | A provider adapter; a provider-specific integration is an alternative. | An adapter reduces coupling but does not settle provider choice, data handling or confidence rules. **Proposed; provider unresolved.** |
| Deployment | Initial scope is one project, repository and space, with best-effort availability. | One Python API and one worker/scheduler with persistent PostgreSQL; multiple workers or additional infrastructure are alternatives for measured needs. | The smaller deployment is easier to operate; scaling requires coordinated scheduling and job ownership. **Proposed.** |

## 13. Requirements alignment

| Requirements | Architectural response |
| --- | --- |
| FR-001–FR-004 | Central artefact registry and registration interfaces. |
| FR-005–FR-012 | Validated event receiver, change detector, manual checks and periodic reconciliation. |
| FR-013–FR-018 | Persistent dependency registry, impact engine and ADS report workflow. |
| FR-019–FR-025 | Provider-independent proposals, authorized review, version-bound approval and conflict handling. |
| FR-026–FR-030 | Section-level publication, version checks, audit and approved rollback. |
| FR-031–FR-035 | Explicit error reporting, bounded retries and independent target processing. |
| NFR-001–NFR-010 | Idempotency, best-effort operation, traceability, integrity, RBAC, OAuth, secret protection and safe logging. |

This is an architecture proposal for human review. It is not a design review,
implementation plan or production implementation.
