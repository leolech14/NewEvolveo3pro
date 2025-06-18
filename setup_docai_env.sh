#!/bin/bash
# Setup script for Google Document AI environment

echo "🚀 Setting up Google Document AI environment for NewEvolveo3pro..."

# Export environment variables
export GOOGLE_CLOUD_PROJECT=astute-buttress-340100
export GOOGLE_DOCUMENTAI_LOCATION=us
export GOOGLE_APPLICATION_CREDENTIALS=google-docai-key.json

# Document AI Processor IDs (from your processors)
export DOCAI_OCR_PROCESSOR=b6aa561c7373e958
export DOCAI_FORM_PARSER=73cb480d97af1de0
export DOCAI_LAYOUT_PARSER=91d90f62e4cd4e91
export DOCAI_INVOICE_PARSER=1987dc93c7f83b35
export DOCAI_CUSTOM_EXTRACTOR=cbe752b341a1423c

echo "✅ Environment variables set:"
echo "   GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT"
echo "   GOOGLE_DOCUMENTAI_LOCATION=$GOOGLE_DOCUMENTAI_LOCATION"
echo "   GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS"
echo ""
echo "📋 Available processors:"
echo "   OCR Processor: $DOCAI_OCR_PROCESSOR"
echo "   Form Parser: $DOCAI_FORM_PARSER"
echo "   Layout Parser: $DOCAI_LAYOUT_PARSER"
echo "   Invoice Parser: $DOCAI_INVOICE_PARSER"
echo "   Custom Extractor: $DOCAI_CUSTOM_EXTRACTOR"
echo ""
echo "🔧 Test commands:"
echo "   python cli.py extract data/incoming/Itau_2024-10.pdf --method docai --processor form"
echo "   python cli.py extract data/incoming/Itau_2024-10.pdf --method docai --processor invoice"
echo "   python cli.py extract data/incoming/Itau_2024-10.pdf --method docai --processor layout"
echo ""
echo "💡 To persist these variables, add them to your ~/.bashrc or ~/.zshrc"
