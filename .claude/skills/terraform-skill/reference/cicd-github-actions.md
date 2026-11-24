# Terraform CI/CD — GitHub Actions

> GitHub Actions ONLY — never generate `cloudbuild.yaml` (workspace rule).

## Full Pipeline

```yaml
# .github/workflows/terraform.yml
name: Terraform

on:
  pull_request:
    paths: ['terraform/**']
  push:
    branches: [main]
    paths: ['terraform/**']

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
        with:
          terraform_version: "~> 1.9.0"
      - name: Format check
        run: terraform fmt -check -recursive terraform/
      - name: Validate modules
        run: |
          for dir in terraform/modules/*/; do
            echo "Validating $dir"
            terraform -chdir="$dir" init -backend=false
            terraform -chdir="$dir" validate
          done
      - name: tflint
        uses: terraform-linters/setup-tflint@6ffdbaa3be476b3431f7275c26966ef32ff60337 # v6.3.2
      - name: IaC misconfiguration scan (Trivy; tfsec's scanning moved into Trivy)
        uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0
        with:
          scan-type: config
          scan-ref: terraform/
          hide-progress: true
          exit-code: '1'
          severity: CRITICAL,HIGH

  test:
    needs: validate
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
        with:
          terraform_version: "~> 1.9.0"
      - name: Native terraform test (mock providers — no GCP auth required)
        run: |
          for dir in terraform/modules/*/; do
            echo "Testing $dir"
            terraform -chdir="$dir" init -backend=false
            terraform -chdir="$dir" test
          done

  plan:
    needs: test
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093 # v3.0.0
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.TERRAFORM_SA }}
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
      - name: Terraform Plan (staging)
        run: |
          cd terraform/environments/staging
          terraform init
          terraform plan -out=tfplan

  apply:
    needs: plan
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093 # v3.0.0
        with:
          workload_identity_provider: ${{ vars.WIF_PROVIDER }}
          service_account: ${{ vars.TERRAFORM_SA }}
      - uses: hashicorp/setup-terraform@dfe3c3f87815947d99a8997f908cb6525fc44e9e # v4.0.1
      - name: Terraform Apply (staging)
        run: |
          cd terraform/environments/staging
          terraform init
          terraform apply -auto-approve
```

**Stage order enforced:** `validate -> test -> plan -> apply`. Never skip test stage.
