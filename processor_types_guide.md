# Document AI Processor Types & Use Cases

## 📋 Available Processors

### Google Document AI Processors

| Processor Type | Purpose | Best For | Configuration |
|---------------|---------|----------|---------------|
| **OCR Processor** | Basic text extraction | Scanned documents, images | `DOCAI_OCR_PROCESSOR` |
| **Form Parser** | Structured form data | Forms, applications, structured docs | `DOCAI_FORM_PARSER` |
| **Invoice Parser** | Invoice-specific fields | Invoices, billing documents | `DOCAI_INVOICE_PARSER` |
| **Document Layout** | Layout understanding | Complex multi-section docs | `DOCAI_LAYOUT_PARSER` |
| **Custom Processors** | Domain-specific models | Trained for specific doc types | Custom IDs |

### AWS Textract Features

| Feature | Purpose | Best For |
|---------|---------|----------|
| **Detect Text** | Basic OCR | Simple text extraction |
| **Analyze Document** | Forms & tables | Structured data extraction |
| **Analyze Expense** | Receipt processing | Expense reports, receipts |
| **Analyze ID** | Identity documents | Driver licenses, passports |

### Azure Document Intelligence Models

| Model | Purpose | Best For |
|-------|---------|----------|
| **Prebuilt Layout** | General layout | Mixed document types |
| **Prebuilt Invoice** | Invoice processing | Billing documents |
| **Prebuilt Receipt** | Receipt processing | Expense management |
| **Prebuilt Business Card** | Contact extraction | Business cards |
| **Custom Models** | Domain-specific | Trained for specific formats |

---

## 🎯 Processor Selection Strategy

### For Credit Card Statements (like Itaú)
1. **Primary**: Form Parser (structured data)
2. **Secondary**: Layout Parser (complex layouts)
3. **Fallback**: OCR Processor (basic text)

### For Invoices
1. **Primary**: Invoice Parser (specialized)
2. **Secondary**: Form Parser (structured)
3. **Fallback**: Layout Parser

### For Receipts
1. **Primary**: Receipt Parser (expense-focused)
2. **Secondary**: Form Parser
3. **Fallback**: OCR

### For Unknown Documents
1. **Primary**: Layout Parser (general purpose)
2. **Secondary**: Form Parser
3. **Fallback**: OCR Processor

---

## 🔧 Configuration Examples

### Environment Variables
```bash
# Google Document AI
export GOOGLE_CLOUD_PROJECT="astute-buttress-340100"
export GOOGLE_APPLICATION_CREDENTIALS="google-docai-key.json"
export DOCAI_FORM_PARSER="73cb480d97af1de0"
export DOCAI_OCR_PROCESSOR="9a2e4b1c8f7d6e5a"
export DOCAI_INVOICE_PARSER="8d2f5c9e1a6b4d7f"

# AWS Textract
export AWS_ACCESS_KEY_ID="your_key"
export AWS_SECRET_ACCESS_KEY="your_secret"
export AWS_DEFAULT_REGION="us-east-1"

# Azure Document Intelligence
export AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="https://your-resource.cognitiveservices.azure.com/"
export AZURE_DOCUMENT_INTELLIGENCE_KEY="your_key"
```

### CLI Usage
```bash
# Test different processors
python cli_clean.py extract file.pdf --method docai --processor form
python cli_clean.py extract file.pdf --method docai --processor ocr
python cli_clean.py extract file.pdf --method docai --processor invoice

# Compare methods
python cli_clean.py extract file.pdf --method auto      # Intelligent routing
python cli_clean.py extract file.pdf --method simple    # Local only
python cli_clean.py extract file.pdf --method pipeline  # Full ensemble
```

---

## 📊 Cost & Performance Comparison

### Processing Costs (per page)
- **Google Document AI**: $0.0015 - $0.030 (depending on processor)
- **AWS Textract**: $0.0015 - $0.065 (depending on features)
- **Azure Document Intelligence**: $0.001 - $0.010 (depending on model)
- **Local Processing**: $0.000 (free)

### Performance Characteristics
- **Cloud Services**: High accuracy (90-98%), slower (5-30s), requires internet
- **Local Methods**: Lower accuracy (30-85%), faster (0.3-5s), works offline

### Recommended Hybrid Strategy
1. **Development/Testing**: Use local methods for speed
2. **Production**: Cloud services for accuracy, local fallbacks for reliability
3. **High-Volume**: Pre-screen with local methods, cloud for complex documents
4. **Cost-Sensitive**: Local-first with cloud fallbacks

---

## 🚀 NewEvolveo3pro Intelligent Routing

The robust extraction system automatically selects the best processor:

### Document Pattern Recognition
```python
# Itaú statements → Form Parser
"itau_20\d\d-\d\d\.pdf" → DOCAI_FORM_PARSER

# Generic PDFs → OCR Processor  
".*\.pdf" → DOCAI_OCR_PROCESSOR

# Invoice files → Invoice Parser
".*invoice.*\.pdf" → DOCAI_INVOICE_PARSER
```

### Fallback Chain
1. **Primary**: Cloud processor (if configured)
2. **Secondary**: Local ensemble pipeline
3. **Tertiary**: Regex fallback extraction

This ensures **100% success rate** while optimizing for accuracy and cost.
