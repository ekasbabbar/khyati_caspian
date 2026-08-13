# AWS EC2 listener deployment

This deployment runs Khyati's persistent Caspian listener on an Ubuntu EC2
instance. The worker makes outbound HTTPS connections to Caspian, model
providers, PostgreSQL, and optional private knowledge storage. It does not host
the future portfolio API and does not require an inbound application port.

## 1. Launch the instance

Recommended starting configuration:

- Ubuntu Server 24.04 LTS
- `t3.micro` or `t3.small` while traffic is low
- 12–16 GB encrypted gp3 root volume
- Detailed monitoring optional
- No public HTTP/HTTPS ingress

Create a security group with:

- Inbound TCP 22 from your current public IP only, or use Session Manager/EC2
  Instance Connect instead of persistent public SSH.
- Outbound TCP 443 so the listener can reach its external services.
- PostgreSQL egress to the database endpoint/port if your database rules are
  restricted separately.

Attach an EC2 instance role containing AWS's
`AmazonSSMManagedInstanceCore` managed policy plus the restricted S3 policy in
`deploy/aws/iam/ec2-instance-policy.json`. Replace its bucket placeholder first.
No AWS access key belongs on the VM.

For an Ubuntu AMI, the initial SSH username is `ubuntu`:

```bash
ssh -i path/to/key.pem ubuntu@EC2_PUBLIC_DNS
```

## 2. Prepare the worker

Replace the repository URL before running:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip
sudo useradd --system --create-home --home-dir /opt/khyati --shell /usr/sbin/nologin khyati
sudo -u khyati git clone https://github.com/YOUR_USER/YOUR_REPOSITORY.git /opt/khyati/app
sudo -u khyati python3 -m venv /opt/khyati/app/.venv
sudo -u khyati /opt/khyati/app/.venv/bin/pip install --upgrade pip
sudo -u khyati /opt/khyati/app/.venv/bin/pip install -r /opt/khyati/app/requirements.txt
sudo -u khyati mkdir -p /opt/khyati/app/.khyati
```

Confirm the instance appears as a managed node in Systems Manager before
enabling GitHub deployment. Ubuntu AWS images normally include SSM Agent; its
service may be installed through Snap.

## 3. Install secrets outside Git

```bash
sudo install -d -m 700 /etc/khyati
sudo install -m 600 /opt/khyati/app/deploy/aws/khyati.env.example /etc/khyati/khyati.env
sudoedit /etc/khyati/khyati.env
```

Configure Caspian, Telegram, one LLM provider, and
`KHYATI_OWNER_TELEGRAM_USERNAME`. Set `DATABASE_URL` for durable state. Prefer
`KHYATI_KNOWLEDGE_S3_BUCKET` and the EC2 instance role for private knowledge, or securely copy the ignored
`knowledge/` directory to `/opt/khyati/app/knowledge`.

The environment file is outside the checkout. Never commit it, place secrets in
EC2 user data, or print it into CI logs.

## 4. Install and start systemd

```bash
sudo install -m 644 /opt/khyati/app/deploy/aws/khyati.service /etc/systemd/system/khyati.service
sudo systemctl daemon-reload
sudo systemctl enable --now khyati
sudo systemctl status khyati --no-pager
```

Watch logs:

```bash
sudo journalctl -u khyati -f
```

The service uses `SIGINT` for a clean Caspian/PostgreSQL shutdown, restarts after
failures, and starts automatically when EC2 reboots.

## 5. Deploy an update manually

```bash
git_sha=$(sudo -u khyati git -C /opt/khyati/app ls-remote origin refs/heads/main | cut -f1)
sudo bash /opt/khyati/app/deploy/aws/update.sh "$git_sha"
sudo systemctl status khyati --no-pager
```

The updater deploys an exact commit, runs tests, refreshes dependencies and the
systemd unit, and rolls back to the previous commit if deployment fails.

## 6. Enable GitHub code deployment

Create an AWS IAM OIDC role restricted to this repository's `main` branch and
attach the policy template in `deploy/aws/iam/github-code-deploy-policy.json`.
Use `deploy/aws/iam/github-oidc-trust-policy.json` as the role trust-policy
template, replacing every placeholder. Create a separately restricted copy for
the private knowledge repository.
In the public GitHub repository, configure these **Repository variables**:

```text
AWS_DEPLOY_ROLE_ARN
AWS_REGION
EC2_INSTANCE_ID
```

`.github/workflows/deploy-ec2.yml` then deploys each successful push to `main`
through SSM. The job is skipped until the variables exist.

## 7. Enable private knowledge delivery

1. Create a private, version-enabled S3 bucket.
2. Create a separate private repository containing a `knowledge/` directory.
3. Copy `deploy/aws/publish-knowledge.workflow.yml` into that repository as
   `.github/workflows/publish-knowledge.yml`.
4. Create a second OIDC role and attach the restricted template in
   `deploy/aws/iam/github-knowledge-policy.json`.
5. Configure these variables in the private repository:

```text
AWS_KNOWLEDGE_ROLE_ARN
AWS_REGION
EC2_INSTANCE_ID
KHYATI_APP_REPOSITORY=OWNER/PUBLIC_REPOSITORY
KHYATI_KNOWLEDGE_BUCKET
```

Each knowledge push validates metadata, publishes files under the immutable
commit SHA, replaces `current/manifest.json` last, and reloads Khyati through
SSM. If startup fails, the workflow restores the prior versioned manifest.

For recovery, configure an EC2 status-check alarm and optionally an EBS snapshot
policy. The PostgreSQL database and private knowledge store should remain outside
the instance so replacing the VM does not lose production state.

## Manual knowledge save button from Windows

For a direct local-to-EC2 workflow, copy
`scripts/save-knowledge.example.cmd` to the repository root as
`save-knowledge.local.cmd`, fill in the PEM path and EC2 hostname, and
double-click it after editing the local `knowledge/` directory. Files ending in
`.local.cmd` are ignored so machine-specific infrastructure details are not
published.

The button validates metadata before upload, copies into a staging directory,
validates again on EC2, mirrors additions/changes/deletions into
`/opt/khyati/app/knowledge`, restarts the systemd service, checks that it remains
active, and restores the previous knowledge folder if the restart fails.

The EC2 image needs `rsync` for this workflow:

```bash
sudo apt install -y rsync
```

## Local on/off switch

Copy `scripts/toggle-khyati.example.cmd` to the repository root as
`toggle-khyati.local.cmd`, configure the PEM path and hostname, then
double-click it to toggle the listener. Turning Khyati off runs
`systemctl disable --now khyati`; turning it on runs
`systemctl enable --now khyati`. This stops API polling and message handling but
does not stop the EC2 instance itself.

The PowerShell controller can also be used directly with `-Action on`, `off`,
`status`, or `toggle`.
