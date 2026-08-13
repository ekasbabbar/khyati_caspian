# Local maintenance shortcuts

This directory holds developer-operated EC2 shortcuts. Files ending in
`.local.ps1` are ignored because they contain machine-specific PEM paths and
hostnames.

- `save-knowledge.local.ps1` validates and deploys the private `knowledge/`
  directory, restarts Khyati, and rolls back if the service does not recover.
- `deploy-code.local.ps1` resolves the latest `main` commit from GitHub and runs
  the transactional EC2 updater.

Run either file from the repository root:

```powershell
.\dev-scripts\save-knowledge.local.ps1
.\dev-scripts\deploy-code.local.ps1
```

The code deployment requires the desired changes to have already been committed
and pushed to the public repository.
