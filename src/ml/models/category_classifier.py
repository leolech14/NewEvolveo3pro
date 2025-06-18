"""ML-based category classification for transaction descriptions."""

from __future__ import annotations

import joblib
import pandas as pd
from pathlib import Path
from typing import Optional

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder


class CategoryClassifier:
    """ML-based transaction category classifier."""

    def __init__(self):
        self.pipeline: Optional[Pipeline] = None
        self.label_encoder: Optional[LabelEncoder] = None
        self.categories: list[str] = []
        self.is_trained = False

    def prepare_features(self, descriptions: list[str]) -> list[str]:
        """Prepare text features for classification."""
        # Clean and normalize descriptions
        cleaned = []
        for desc in descriptions:
            if not desc:
                cleaned.append("")
                continue
            
            # Remove extra whitespace and normalize
            desc_clean = " ".join(desc.split()).upper()
            
            # Remove common noise patterns
            noise_patterns = ["FINAL", "CARTAO", "CART.", "*"]
            for pattern in noise_patterns:
                desc_clean = desc_clean.replace(pattern, "")
            
            cleaned.append(desc_clean.strip())
        
        return cleaned

    def train(self, training_data: pd.DataFrame) -> dict:
        """Train the category classifier."""
        print("🔧 Training Category Classifier...")
        
        # Prepare data
        descriptions = self.prepare_features(training_data['description_text'].tolist())
        categories = training_data['target_category'].tolist()
        
        # Remove empty categories
        valid_data = [(desc, cat) for desc, cat in zip(descriptions, categories) if cat and cat.strip()]
        descriptions, categories = zip(*valid_data) if valid_data else ([], [])
        
        if len(descriptions) < 10:
            raise ValueError("Insufficient training data for category classification")
        
        print(f"   • Training on {len(descriptions)} transactions")
        
        # Encode labels
        self.label_encoder = LabelEncoder()
        y_encoded = self.label_encoder.fit_transform(categories)
        self.categories = list(self.label_encoder.classes_)
        
        print(f"   • Found {len(self.categories)} categories: {self.categories}")
        
        # Create pipeline
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                max_features=1000,
                ngram_range=(1, 2),
                stop_words=None,  # Portuguese stop words would be better
                min_df=2,
                max_df=0.95
            )),
            ('classifier', RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                min_samples_leaf=2,
                random_state=42,
                class_weight='balanced'  # Handle class imbalance
            ))
        ])
        
        # Train-test split with stratification handling for small classes
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                descriptions, y_encoded, test_size=0.2, stratify=y_encoded, random_state=42
            )
        except ValueError:
            # If stratification fails due to small classes, use simple split
            print("   ⚠️  Using simple split due to small class sizes")
            X_train, X_test, y_train, y_test = train_test_split(
                descriptions, y_encoded, test_size=0.2, random_state=42
            )
        
        # Train the model
        self.pipeline.fit(X_train, y_train)
        self.is_trained = True
        
        # Evaluate
        train_score = self.pipeline.score(X_train, y_train)
        test_score = self.pipeline.score(X_test, y_test)
        
        print(f"   • Training accuracy: {train_score:.3f}")
        print(f"   • Test accuracy: {test_score:.3f}")
        
        # Cross-validation with handling for small datasets
        try:
            cv_folds = min(5, len(set(y_encoded)))  # Don't use more folds than classes
            cv_scores = cross_val_score(self.pipeline, descriptions, y_encoded, cv=cv_folds)
            print(f"   • Cross-validation: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
        except Exception as e:
            print(f"   ⚠️  Cross-validation failed: {e}")
            cv_scores = [test_score]  # Fallback to test score
        
        # Detailed evaluation
        y_pred = self.pipeline.predict(X_test)
        y_test_labels = self.label_encoder.inverse_transform(y_test)
        y_pred_labels = self.label_encoder.inverse_transform(y_pred)
        
        # Class distribution
        class_counts = pd.Series(categories).value_counts()
        print(f"   • Class distribution: {dict(class_counts.head())}")
        
        return {
            'training_accuracy': train_score,
            'test_accuracy': test_score,
            'cv_score_mean': cv_scores.mean(),
            'cv_score_std': cv_scores.std(),
            'num_categories': len(self.categories),
            'num_samples': len(descriptions),
            'class_distribution': dict(class_counts),
            'classification_report': classification_report(y_test_labels, y_pred_labels, output_dict=True)
        }

    def predict(self, descriptions: list[str]) -> list[str]:
        """Predict categories for descriptions."""
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        cleaned_descriptions = self.prepare_features(descriptions)
        predictions = self.pipeline.predict(cleaned_descriptions)
        return self.label_encoder.inverse_transform(predictions).tolist()

    def predict_proba(self, descriptions: list[str]) -> list[dict[str, float]]:
        """Predict category probabilities."""
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        cleaned_descriptions = self.prepare_features(descriptions)
        probabilities = self.pipeline.predict_proba(cleaned_descriptions)
        
        results = []
        for probs in probabilities:
            prob_dict = {
                category: float(prob) 
                for category, prob in zip(self.categories, probs)
            }
            results.append(prob_dict)
        
        return results

    def get_confidence(self, descriptions: list[str]) -> list[float]:
        """Get prediction confidence scores."""
        probabilities = self.predict_proba(descriptions)
        return [max(prob_dict.values()) for prob_dict in probabilities]

    def save_model(self, model_path: Path):
        """Save trained model to disk."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")
        
        model_data = {
            'pipeline': self.pipeline,
            'label_encoder': self.label_encoder,
            'categories': self.categories,
            'is_trained': self.is_trained
        }
        
        joblib.dump(model_data, model_path)
        print(f"   • Model saved to {model_path}")

    def load_model(self, model_path: Path):
        """Load trained model from disk."""
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        model_data = joblib.load(model_path)
        self.pipeline = model_data['pipeline']
        self.label_encoder = model_data['label_encoder']
        self.categories = model_data['categories']
        self.is_trained = model_data['is_trained']
        
        print(f"   • Model loaded from {model_path}")
        print(f"   • Categories: {len(self.categories)}")

    def analyze_feature_importance(self, top_n: int = 10) -> dict:
        """Analyze which features are most important for classification."""
        if not self.is_trained:
            raise ValueError("Model must be trained before feature analysis")
        
        # Get feature names from TF-IDF vectorizer
        vectorizer = self.pipeline.named_steps['tfidf']
        classifier = self.pipeline.named_steps['classifier']
        
        feature_names = vectorizer.get_feature_names_out()
        importances = classifier.feature_importances_
        
        # Get top features
        feature_importance = list(zip(feature_names, importances))
        feature_importance.sort(key=lambda x: x[1], reverse=True)
        
        top_features = feature_importance[:top_n]
        
        return {
            'top_features': top_features,
            'total_features': len(feature_names),
            'feature_importance_std': importances.std()
        }

    def predict_single(self, description: str) -> tuple[str, float]:
        """Predict category for a single description with confidence."""
        predictions = self.predict([description])
        confidences = self.get_confidence([description])
        
        return predictions[0], confidences[0]
