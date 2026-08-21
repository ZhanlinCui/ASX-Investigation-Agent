# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through [GitHub Security Advisories](https://github.com/ZhanlinCui/ASX-Investigation-Agent/security/advisories/new). Do not open a public issue for a vulnerability, leaked credential or evidence-access bypass.

Include the affected commit or version, reproduction steps, expected impact and any suggested mitigation. Do not include real API keys, private provider responses, holdout labels or sensitive source documents.

## Supported version

Security fixes currently target the latest release-candidate branch and tag. This repository is not yet a stable, authenticated or multi-tenant service.

## Credential handling

Credentials belong only in the ignored `.env` or an equivalent backend secret store. They must never be committed, sent to the browser, embedded in evaluation bundles or included in reports. Any credential pasted into chat, issue text or logs must be considered exposed and rotated before use.

The public report boundary intentionally excludes provider bodies, search queries, memory values, prompts and private model output. Exact evidence passages require a case-version-scoped request.
