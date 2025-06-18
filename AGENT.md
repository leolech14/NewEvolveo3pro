# AGENT.md - AI Assistant Context

## Frequently Used Commands

### Development & Testing
```bash
# Activate virtual environment (required for all operations)
source venv/bin/activate

# Run smoke tests
PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src ./venv/bin/python3.13 smoke_test.py

# ML Training Pipeline
PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src ./venv/bin/python3.13 prepare_ml_training.py
PYTHONPATH=/Users/lech/Install/NewEvolveo3pro/src ./venv/bin/python3.13 train_ml_models.py

# Install dependencies
pip install -r requirements.txt

# Code quality
ruff check src/
black src/
mypy src/
```

### Docker Operations
```bash
# Build and run full stack
cd infra/
docker-compose up -d

# Individual services
docker-compose up newevolveo3pro  # Main application
docker-compose up streamlit       # UI for golden file editing
```

### Testing & Validation
```bash
# Run specific tests
pytest tests/test_core.py
pytest tests/test_extractors_against_golden.py

# CLI extraction test
python -m src.cli extract data/incoming/sample.pdf --output /tmp/result.csv
```

## Code Style & Preferences

### Python Standards
- **Type hints**: Always use type annotations
- **Error handling**: Prefer explicit exception handling over silent failures
- **Dataclasses**: Use for data models (see `src/core/models.py`)
- **Pathlib**: Use `Path` objects instead of string paths
- **f-strings**: Preferred for string formatting

### Project Conventions
- **Imports**: Group by standard/third-party/local with isort
- **Line length**: 88 characters (Black default)
- **Docstrings**: Google style for functions and classes
- **Variable naming**: Snake_case, descriptive names
- **Constants**: ALL_CAPS in regex_catalogue.py

## Codebase Structure

### Core Architecture
```
src/
├── core/               # Data models, confidence, patterns
│   ├── models.py      # Transaction, PipelineResult dataclasses
│   ├── confidence.py  # ML-based confidence calibration
│   ├── patterns.py    # Legacy pattern matching
│   ├── regex_catalogue.py  # Unified regex patterns
│   └── normalise.py   # Brazilian number/date utils
├── extractors/        # PDF processing engines
│   ├── pdfplumber_extractor.py  # Text-based extraction
│   ├── camelot_extractor.py     # Table extraction
│   ├── textract_extractor.py    # AWS OCR
│   └── azure_extractor.py       # Azure OCR
├── ml/                # Machine learning pipeline
│   ├── models/        # ML model implementations
│   └── training_data_prep.py    # Feature engineering
├── utils/             # Utilities
│   └── row_builder.py # Word clustering for parsing
├── validators/        # Quality assurance
│   ├── golden_validator.py      # Golden dataset validation
│   └── cell_level_diff.py       # Precision/recall metrics
├── merge/             # Transaction deduplication
│   └── cluster_fuzzy.py         # Fuzzy matching logic
└── classifiers/       # Transaction classification
    └── row_classifier.py        # Row type detection
```

### Data Flow
1. **Input**: PDF files in `data/incoming/`
2. **Extraction**: Multiple extractors process PDFs → raw JSON
3. **Normalization**: Brazilian formats converted to standard
4. **ML Enhancement**: Category prediction, merchant extraction
5. **Validation**: Against golden datasets in `data/golden/`
6. **Output**: Structured CSV with confidence scores

## Important Notes

### Python Environment
- **Python 3.13 required** - Use `./venv/bin/python3.13` specifically
- **PYTHONPATH must be set** to `/Users/lech/Install/NewEvolveo3pro/src`
- **Virtual env required** - Always `source venv/bin/activate` first

### Dependencies
- **scikit-learn + joblib**: For ML models
- **pandas + polars**: Data processing (both used)
- **pdfplumber + PyMuPDF**: PDF text extraction
- **rapidfuzz**: Fuzzy string matching
- **camelot-py[base]**: Table extraction (NOT [cv] - breaks on Python 3.13)

### Known Issues
- **Pattern normalization**: Minor test failure (non-blocking)
- **FX predictor**: Needs more training data
- **ydata-profiling**: Removed due to Python 3.13 incompatibility

### Testing Strategy
- **Smoke tests**: Basic functionality verification
- **Golden datasets**: Real-world validation with 253 samples
- **ML validation**: Cross-validation with stratified splits
- **Integration tests**: End-to-end PDF → CSV pipeline

## ML Models

### Current Models (models/ directory)
- **category_classifier.joblib**: Transaction categorization (70% accuracy)
- **merchant_patterns.json**: City/merchant extraction patterns
- **confidence_platt.joblib**: Confidence calibration (if available)

### Training Data
- **Golden datasets**: `data/golden/*.csv` (253 transactions)
- **Features**: Text, amounts, dates, categories
- **Classes**: 15 transaction categories (DIVERSOS, FX, FARMÁCIA, etc.)

## Production Deployment

### Docker Stack
- **newevolveo3pro**: Main extraction service
- **streamlit**: UI for golden file editing  
- **prometheus**: Metrics collection
- **grafana**: Monitoring dashboards
- **redis**: Caching layer

### Monitoring
- **Prometheus metrics**: `/metrics` endpoint
- **Grafana dashboard**: `infra/grafana-dashboard.json`
- **Logs**: Structured logging with loguru + structlog

## Troubleshooting

### Common Issues
1. **Import errors**: Check PYTHONPATH and virtual env
2. **ML model failures**: Ensure scikit-learn installed in venv
3. **PDF extraction fails**: Check cloud API credentials
4. **Docker issues**: Verify ports 8080, 3000, 9090 available

### Debug Commands
```bash
# Check environment
which python3.13
echo $PYTHONPATH
pip list | grep sklearn

# Validate models
ls -la models/
python -c "import joblib; print(joblib.load('models/category_classifier.joblib'))"

# Test extraction
python -m src.cli --help
```

This context should help future AI assistants work effectively with the NewEvolveo3pro codebase.
