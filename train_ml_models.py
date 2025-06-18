#!/usr/bin/env python3
"""Train all ML models on the 253 golden transaction dataset."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.ml.models.category_classifier import CategoryClassifier
from src.ml.models.merchant_extractor import MerchantCityExtractor
from src.ml.models.fx_predictor import FXRatePredictor
import pandas as pd


def load_training_data() -> pd.DataFrame:
    """Load the prepared ML training data."""
    training_file = Path("data/ml_training_data.csv")
    
    if not training_file.exists():
        print("❌ Training data not found. Run prepare_ml_training.py first.")
        sys.exit(1)
    
    print(f"📊 Loading training data from {training_file}")
    df = pd.read_csv(training_file)
    print(f"   • Loaded {len(df)} training samples")
    print(f"   • Columns: {list(df.columns)}")
    
    return df


def train_category_classifier(training_data: pd.DataFrame) -> CategoryClassifier:
    """Train the category classification model."""
    print("\n🎯 Training Category Classifier")
    print("=" * 50)
    
    classifier = CategoryClassifier()
    
    try:
        # Clean training data
        clean_data = training_data.copy()
        clean_data['target_category'] = clean_data['target_category'].fillna('').astype(str)
        clean_data['description_text'] = clean_data['description_text'].fillna('').astype(str)
        
        results = classifier.train(clean_data)
        
        print(f"\n📊 Training Results:")
        print(f"   • Samples: {results['num_samples']}")
        print(f"   • Categories: {results['num_categories']}")
        print(f"   • Test Accuracy: {results['test_accuracy']:.3f}")
        print(f"   • CV Score: {results['cv_score_mean']:.3f} ± {results['cv_score_std']:.3f}")
        
        # Feature importance analysis
        print(f"\n🔍 Feature Analysis:")
        importance = classifier.analyze_feature_importance()
        print(f"   • Total features: {importance['total_features']}")
        print(f"   • Top features:")
        for feature, score in importance['top_features'][:5]:
            print(f"     - {feature}: {score:.3f}")
        
        # Save model
        model_path = Path("models/category_classifier.joblib")
        model_path.parent.mkdir(exist_ok=True)
        classifier.save_model(model_path)
        
        return classifier
        
    except Exception as e:
        print(f"❌ Category classifier training failed: {e}")
        return None


def train_merchant_extractor(training_data: pd.DataFrame) -> MerchantCityExtractor:
    """Train the merchant city extraction model."""
    print("\n🏪 Training Merchant City Extractor")
    print("=" * 50)
    
    extractor = MerchantCityExtractor()
    
    try:
        # Clean training data
        clean_data = training_data.copy()
        clean_data['target_merchant_city'] = clean_data['target_merchant_city'].fillna('').astype(str)
        clean_data['description_text'] = clean_data['description_text'].fillna('').astype(str)
        
        results = extractor.train(clean_data)
        
        print(f"\n📊 Training Results:")
        print(f"   • Cities learned: {results['cities_learned']}")
        print(f"   • Merchants learned: {results['merchants_learned']}")
        print(f"   • Sample cities: {results['sample_cities']}")
        
        # Test extraction on sample data
        print(f"\n🧪 Testing Extraction:")
        sample_descriptions = training_data['description_text'].head(10).tolist()
        analysis = extractor.analyze_patterns(sample_descriptions)
        
        print(f"   • City extraction rate: {analysis['city_extraction_rate']:.2%}")
        print(f"   • Merchant extraction rate: {analysis['merchant_extraction_rate']:.2%}")
        print(f"   • Online transactions: {analysis['online_transactions']}")
        
        # Save patterns
        patterns_path = Path("models/merchant_patterns.json")
        patterns_path.parent.mkdir(exist_ok=True)
        extractor.save_patterns(patterns_path)
        
        return extractor
        
    except Exception as e:
        print(f"❌ Merchant extractor training failed: {e}")
        return None


def train_fx_predictor(training_data: pd.DataFrame) -> FXRatePredictor:
    """Train the FX rate prediction model."""
    print("\n💱 Training FX Rate Predictor")
    print("=" * 50)
    
    predictor = FXRatePredictor()
    
    try:
        # Prepare data with proper column names for FX training
        fx_training_data = training_data.copy()
        
        # Map to expected column names using real data
        fx_training_data['fx_rate'] = pd.to_numeric(fx_training_data.get('target_fx_rate', 0), errors='coerce') / 100  # Convert from hundredths
        fx_training_data['currency_orig'] = fx_training_data.get('target_currency', 'BRL').fillna('BRL')
        fx_training_data['amount_brl'] = pd.to_numeric(fx_training_data.get('amount_magnitude', 0), errors='coerce') / 100  # Convert to decimal
        fx_training_data['amount_orig'] = pd.to_numeric(fx_training_data.get('target_amount_orig', 0), errors='coerce') / 100  # Convert to decimal
        
        # Only use valid FX rate data (rate > 0) for training
        fx_training_data = fx_training_data[
            (fx_training_data['fx_rate'] > 0) & 
            (fx_training_data['currency_orig'] != 'BRL') &
            (fx_training_data['amount_orig'] > 0)
        ]
        
        results = predictor.train(fx_training_data)
        
        if 'error' in results:
            print(f"   ⚠️  {results['error']}")
            print(f"   • Using fallback prediction with currency averages")
        else:
            print(f"\n📊 Training Results:")
            print(f"   • Training samples: {results['training_samples']}")
            print(f"   • Test MAE: {results['test_mae']:.3f}")
            print(f"   • Test R²: {results['test_r2']:.3f}")
            print(f"   • FX range: {results['fx_range'][0]:.3f} - {results['fx_range'][1]:.3f}")
            
            # Feature importance
            importance = predictor.analyze_feature_importance()
            if 'error' not in importance:
                print(f"\n🔍 Feature Importance:")
                for feature, score in importance['feature_importance'][:5]:
                    print(f"     - {feature}: {score:.3f}")
        
        print(f"   • Currency averages: {predictor.currency_averages}")
        
        # Save model
        model_path = Path("models/fx_predictor.joblib")
        model_path.parent.mkdir(exist_ok=True)
        predictor.save_model(model_path)
        
        return predictor
        
    except Exception as e:
        print(f"❌ FX predictor training failed: {e}")
        return None


def test_models(training_data: pd.DataFrame, classifier: CategoryClassifier, 
                extractor: MerchantCityExtractor, fx_predictor: FXRatePredictor):
    """Test all trained models on sample data."""
    print("\n🧪 Testing Trained Models")
    print("=" * 50)
    
    # Test on first 5 samples
    test_samples = training_data.head(5)
    
    for i, row in test_samples.iterrows():
        description = row['description_text']
        print(f"\n📋 Sample {i+1}: {description}")
        
        # Test category classification
        if classifier:
            category, confidence = classifier.predict_single(description)
            print(f"   🎯 Category: {category} (confidence: {confidence:.3f})")
        
        # Test merchant extraction
        if extractor:
            merchant, city = extractor.extract_merchant_and_city(description)
            print(f"   🏪 Merchant: {merchant or 'N/A'}")
            print(f"   🌍 City: {city or 'N/A'}")
        
        # Test FX prediction
        if fx_predictor:
            amount_brl = row.get('amount_magnitude', 0)
            amount_orig = row.get('target_amount_orig', 0)
            currency = row.get('target_currency', 'BRL')
            
            if currency != 'BRL':
                fx_rate, fx_confidence = fx_predictor.predict_single(
                    amount_brl, amount_orig, currency, description
                )
                print(f"   💱 FX Rate: {fx_rate:.3f} {currency}/BRL (confidence: {fx_confidence:.3f})")


def main():
    """Main training pipeline."""
    print("🚀 ML Model Training Pipeline")
    print("=" * 60)
    
    # Load training data
    training_data = load_training_data()
    
    # Train all models
    classifier = train_category_classifier(training_data)
    extractor = train_merchant_extractor(training_data)
    fx_predictor = train_fx_predictor(training_data)
    
    # Test models
    test_models(training_data, classifier, extractor, fx_predictor)
    
    # Summary
    print("\n🎉 ML Training Pipeline Complete!")
    print("=" * 60)
    
    models_trained = sum([
        classifier is not None,
        extractor is not None,
        fx_predictor is not None
    ])
    
    print(f"📊 Summary:")
    print(f"   • Models trained: {models_trained}/3")
    print(f"   • Training data: {len(training_data)} transactions")
    print(f"   • Models saved to: models/ directory")
    
    if models_trained == 3:
        print(f"\n✅ All models ready for Phase 3 integration!")
    else:
        print(f"\n⚠️  Some models failed to train. Check logs above.")
    
    print(f"\n🔄 Next Steps:")
    print(f"   1. Integrate ML models into enrichment pipeline")
    print(f"   2. Test end-to-end accuracy on validation set")
    print(f"   3. Deploy enhanced pipeline to production")


if __name__ == "__main__":
    main()
