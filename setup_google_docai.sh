#!/bin/bash
# Google Document AI setup script

echo "🔧 Setting up Google Document AI environment..."

# Check if key file exists
if [ ! -f "google-docai-key.json" ]; then
    echo "❌ google-docai-key.json not found!"
    echo "💡 Run this first:"
    echo "   gcloud iam service-accounts keys create google-docai-key.json \\"
    echo "     --iam-account=docai-extractor@YOUR-PROJECT-ID.iam.gserviceaccount.com"
    exit 1
fi

# Set environment variables
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/google-docai-key.json"

# Your Google Cloud project settings:
export GOOGLE_CLOUD_PROJECT="astute-buttress-340100"
export GOOGLE_DOCUMENTAI_PROCESSOR_ID="YOUR-PROCESSOR-ID"  # You'll get this from the console

echo "✅ Environment variables set:"
echo "   GOOGLE_APPLICATION_CREDENTIALS: $GOOGLE_APPLICATION_CREDENTIALS"
echo "   GOOGLE_CLOUD_PROJECT: $GOOGLE_CLOUD_PROJECT"  
echo "   GOOGLE_DOCUMENTAI_PROCESSOR_ID: $GOOGLE_DOCUMENTAI_PROCESSOR_ID"

# Test if credentials work
echo "🧪 Testing Google Cloud authentication..."
python3 -c "
try:
    from google.cloud import documentai
    from google.oauth2 import service_account
    print('✅ Google Cloud libraries imported successfully')
    
    # Try to create client
    client = documentai.DocumentProcessorServiceClient()
    print('✅ Document AI client created successfully')
    print('🎉 Google Document AI is ready to use!')
except ImportError as e:
    print(f'❌ Missing library: {e}')
    print('💡 Run: pip install google-cloud-documentai')
except Exception as e:
    print(f'❌ Authentication error: {e}')
    print('💡 Check your credentials and project settings')
"

echo ""
echo "🚀 To use Google Document AI:"
echo "   source setup_google_docai.sh"
echo "   python test_extractors.py"
