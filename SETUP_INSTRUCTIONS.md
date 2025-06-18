# NewEvolveo3pro Setup Instructions

## 1. Configure Credentials

Edit `/Users/lech/Install/NewEvolveo3pro/.env` with your credentials:

Copy from `.env.example` and add your actual credentials:

```bash
# AWS Textract
AWS_ACCESS_KEY_ID=[your-redacted-aws-key]
AWS_SECRET_ACCESS_KEY=p5hRQPwfItzHd/gjysmtSb99HPc4zSXOODx8KuOo
AWS_REGION=us-east-1

# Azure Document Intelligence
AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=https://azurelbl.cognitiveservices.azure.com/
AZURE_DOCUMENT_INTELLIGENCE_KEY=E36dAzBzvECIs3a01Fchw4tM0Jv8ctMaH615srjARl1ZqDgjL7UUJQQJ99BFACYeBjFXJ3w3AAALACOGW6Yb

# GitHub (for auto-golden bot)
GITHUB_TOKEN=[your-redacted-github-token]
```

## 2. Connect to GitHub Repository

Initialize and connect to your GitHub repo:

```bash
cd /Users/lech/Install/NewEvolveo3pro
git init
git add .
git commit -m "Initial commit: Production-ready bank statement extraction pipeline"
git branch -M main
git remote add origin https://github.com/leolech14/NewEvolveo3pro.git
git push -u origin main
```

## 3. Install Dependencies

```bash
# Install cloud extractors
pip install -e ".[cloud]"

# Install all dependencies
pip install -r requirements.txt
```

## 4. Test the Pipeline

```bash
# Run smoke tests
python smoke_test.py

# Test with your PDFs
python -m src.cli extract data/test_pdfs/your_statement.pdf --output results.csv

# Validate against golden files
python -m src.cli validate results.csv data/golden/your_golden.csv
```

## 5. Set up GitHub Secrets (for CI/CD)

In your GitHub repo settings, add these secrets:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY` 
- `AZURE_DOCUMENT_INTELLIGENCE_KEY`
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`

## 6. Monitor and Iterate

- Use Streamlit golden editor: `streamlit run tools/golden_editor.py`
- Check logs in `logs/` directory
- Review auto-generated PRs from the golden bot
- Monitor costs via AWS/Azure dashboards

## Next Steps

1. Create GitHub repo `NewEvolveo3pro`
2. Set up credentials in `.env`
3. Push code to GitHub
4. Test extraction pipeline
5. Set up monitoring dashboard
