# DataNexus Architecture Comparison and Implementation Plan

## Reference Sources

- Old wired dashboard
- Execution guide
- Current React MVP
- Current Docker/FastAPI/PostgreSQL implementation

## Old Wired Dashboard Strengths

- Three operating modes:
  - API online + signed in
  - API online + not signed in
  - API offline fallback
- Settings panel for API URL
- Fabric tab
- Compliance simulator
- Query samples
- Intent builder
- Founder/CTO demo script

## Current React MVP Strengths

- React dashboard on localhost:13001
- FastAPI backend on localhost:18000
- PostgreSQL persistence on localhost:15432
- Live pipeline registry
- Pipeline creation
- Pipeline run action
- Compliance check action
- AI Query Assistant
- Intent-to-Pipeline Builder
- JSON exports
- PDF exports
- Demo validation tab
- Health check
- 100% MVP validation script

## Missing Items to Port from Old UI

1. Fabric tab
2. Settings/API URL panel
3. Offline fallback banner and fallback data
4. Multilingual query sample buttons
5. Run all compliance checks
6. Demo script as downloadable artifact
7. Authentication/sign-in simulation
8. API URL persistence in localStorage UI

## Final Target

DataNexus should combine:

- Old UI polish and demo flow
- New React maintainability
- Live FastAPI backend
- PostgreSQL persistence
- Audit and compliance proof exports
- AI query and intent pipeline creation

## Next Build Stages

| Stage | Feature | Priority |
|---|---|---|
| 3O.1 | Fabric tab | High |
| 3O.2 | Settings/API URL panel | High |
| 3O.3 | Offline fallback | High |
| 3O.4 | Multilingual query samples | Medium |
| 3O.5 | Run all compliance checks | Medium |
| 3O.6 | GitHub/package cleanup | High |
