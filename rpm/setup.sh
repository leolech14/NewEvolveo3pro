#!/bin/bash
echo "🚀 Installing NewEvolveo3pro dependencies..."
echo "Setting up Python 3.13 environment..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment..."
    source venv/bin/activate
fi

echo "📦 Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo "✅ Setup complete! Run smoke tests with:"
echo "PYTHONPATH=/path/to/NewEvolveo3pro/src ./venv/bin/python3.13 smoke_test.py"
