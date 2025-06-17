"""Streamlit-based golden CSV editor with confidence highlighting."""

import streamlit as st
import pandas as pd
import asyncio
from pathlib import Path
from typing import List, Optional, Dict, Any
from decimal import Decimal

# Add src to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent / "src"))

from src.merger.ensemble_merger import EnsembleMerger
from src.validators.golden_validator import GoldenValidator
from src.validators.semantic_compare import create_default_comparator
from src.core.models import Transaction


st.set_page_config(
    page_title="NewEvolveo3pro Golden Editor",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)


def init_session_state():
    """Initialize session state variables."""
    if 'extraction_result' not in st.session_state:
        st.session_state.extraction_result = None
    if 'transactions_df' not in st.session_state:
        st.session_state.transactions_df = None
    if 'validation_result' not in st.session_state:
        st.session_state.validation_result = None
    if 'selected_pdf' not in st.session_state:
        st.session_state.selected_pdf = None


def load_available_pdfs() -> List[Path]:
    """Load available PDF files."""
    pdf_dir = Path("data/incoming")
    if not pdf_dir.exists():
        return []
    return list(pdf_dir.glob("*.pdf"))


def transactions_to_dataframe(transactions: List[Transaction]) -> pd.DataFrame:
    """Convert transactions to DataFrame for editing."""
    data = []
    for i, t in enumerate(transactions):
        data.append({
            'row_id': i,
            'date': t.date.strftime('%d/%m/%Y'),
            'description': t.description,
            'amount_brl': f"{t.amount_brl:.2f}".replace('.', ','),
            'category': t.category or '',
            'confidence': t.confidence_score,
            'source': t.source_extractor.value if t.source_extractor else 'ensemble',
        })
    return pd.DataFrame(data)


def dataframe_to_transactions(df: pd.DataFrame) -> List[Transaction]:
    """Convert edited DataFrame back to transactions."""
    from datetime import datetime
    from src.core.patterns import normalize_amount
    from src.core.models import TransactionType
    
    transactions = []
    for _, row in df.iterrows():
        try:
            # Parse date
            date_str = str(row['date'])
            parsed_date = datetime.strptime(date_str, '%d/%m/%Y').date()
            
            # Parse amount
            amount_str = str(row['amount_brl'])
            amount = normalize_amount(amount_str)
            
            transaction = Transaction(
                date=parsed_date,
                description=str(row['description']),
                amount_brl=amount,
                category=str(row['category']) if row['category'] else None,
                transaction_type=TransactionType.DOMESTIC,
                confidence_score=float(row.get('confidence', 0.8)),
            )
            transactions.append(transaction)
        except Exception as e:
            st.error(f"Error parsing row {row.get('row_id', '?')}: {e}")
            continue
    
    return transactions


def style_dataframe_by_confidence(df: pd.DataFrame) -> pd.DataFrame:
    """Apply styling based on confidence scores."""
    def highlight_low_confidence(val, confidence_threshold=0.85):
        """Highlight cells with low confidence."""
        try:
            confidence = float(df.loc[val.name, 'confidence'])
            if confidence < confidence_threshold:
                return 'background-color: #ffcccc; border: 2px solid red'
        except:
            pass
        return ''
    
    # Apply styling to all columns except confidence
    styled_cols = ['date', 'description', 'amount_brl', 'category']
    styler = df.style
    
    for col in styled_cols:
        if col in df.columns:
            styler = styler.applymap(
                highlight_low_confidence,
                subset=[col]
            )
    
    return styler


@st.cache_data(ttl=300)  # Cache for 5 minutes
def run_extraction(pdf_path: str) -> Dict[str, Any]:
    """Run extraction and cache results."""
    try:
        merger = EnsembleMerger()
        result = asyncio.run(merger.extract_with_ensemble(Path(pdf_path)))
        
        return {
            'success': True,
            'transactions': result.final_transactions,
            'confidence_score': result.confidence_score,
            'contributing_pipelines': [p.value for p in result.contributing_pipelines],
            'merge_strategy': result.merge_strategy,
            'conflicts_resolved': result.conflicts_resolved,
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
        }


def run_validation(transactions: List[Transaction], pdf_name: str) -> Optional[Dict[str, Any]]:
    """Run validation against golden files."""
    try:
        validator = GoldenValidator(Path("data/golden"))
        result = validator.validate_against_golden(pdf_name, transactions)
        
        if result:
            return {
                'cell_accuracy': result.cell_accuracy,
                'transaction_count_match': result.transaction_count_match,
                'total_amount_match': result.total_amount_match,
                'amount_difference_brl': float(result.amount_difference_brl),
                'precision': result.precision,
                'recall': result.recall,
                'f1_score': result.f1_score,
                'is_valid': result.is_valid,
                'mismatched_cells': result.mismatched_cells[:10],  # Limit for display
            }
    except Exception as e:
        st.error(f"Validation error: {e}")
    
    return None


def main():
    """Main Streamlit app."""
    init_session_state()
    
    st.title("🎯 NewEvolveo3pro Golden Editor")
    st.markdown("*Interactive editor for creating and validating golden CSV files*")
    
    # Sidebar controls
    st.sidebar.header("📁 File Selection")
    
    available_pdfs = load_available_pdfs()
    if not available_pdfs:
        st.sidebar.error("No PDFs found in data/incoming/")
        st.stop()
    
    pdf_names = [pdf.name for pdf in available_pdfs]
    selected_pdf_name = st.sidebar.selectbox(
        "Select PDF to process:",
        pdf_names,
        index=0
    )
    
    selected_pdf_path = next(
        pdf for pdf in available_pdfs 
        if pdf.name == selected_pdf_name
    )
    
    # Extract button
    if st.sidebar.button("🚀 Extract Transactions", type="primary"):
        with st.spinner("Extracting transactions..."):
            result = run_extraction(str(selected_pdf_path))
            st.session_state.extraction_result = result
            
            if result['success']:
                st.session_state.transactions_df = transactions_to_dataframe(
                    result['transactions']
                )
                st.session_state.selected_pdf = selected_pdf_name
                st.success("✅ Extraction completed!")
            else:
                st.error(f"❌ Extraction failed: {result['error']}")
    
    # Main content
    if st.session_state.extraction_result is None:
        st.info("👆 Select a PDF and click 'Extract Transactions' to begin")
        return
    
    result = st.session_state.extraction_result
    
    if not result['success']:
        st.error(f"Extraction failed: {result['error']}")
        return
    
    # Display extraction summary
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Transactions", len(result['transactions']))
    
    with col2:
        st.metric("Confidence", f"{result['confidence_score']:.1%}")
    
    with col3:
        st.metric("Pipelines", len(result['contributing_pipelines']))
    
    with col4:
        st.metric("Conflicts", result['conflicts_resolved'])
    
    st.markdown("**Contributing Pipelines:** " + ", ".join(result['contributing_pipelines']))
    st.markdown("**Merge Strategy:** " + result['merge_strategy'])
    
    # Editable transactions table
    st.header("📝 Edit Transactions")
    st.markdown("""
    **Red-bordered cells** have low confidence (<85%). Review and edit as needed.
    
    - **Date**: DD/MM/YYYY format
    - **Amount**: Brazilian format (use comma for decimals)
    - **Category**: Optional classification
    """)
    
    if st.session_state.transactions_df is not None:
        # Configuration options
        col1, col2 = st.columns([3, 1])
        
        with col2:
            confidence_threshold = st.slider(
                "Confidence Threshold",
                min_value=0.0,
                max_value=1.0,
                value=0.85,
                step=0.05,
                help="Cells below this confidence will be highlighted in red"
            )
            
            show_source = st.checkbox("Show Source Column", value=True)
            show_confidence = st.checkbox("Show Confidence Column", value=True)
        
        with col1:
            # Prepare display DataFrame
            display_df = st.session_state.transactions_df.copy()
            
            if not show_source:
                display_df = display_df.drop('source', axis=1, errors='ignore')
            if not show_confidence:
                display_df = display_df.drop('confidence', axis=1, errors='ignore')
            
            # Style the DataFrame
            styled_df = style_dataframe_by_confidence(display_df)
            
            # Editable data editor
            edited_df = st.data_editor(
                display_df,
                hide_index=True,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "date": st.column_config.TextColumn(
                        "Date",
                        help="Format: DD/MM/YYYY",
                        max_chars=10,
                    ),
                    "description": st.column_config.TextColumn(
                        "Description",
                        help="Transaction description",
                        max_chars=100,
                    ),
                    "amount_brl": st.column_config.TextColumn(
                        "Amount (BRL)",
                        help="Use comma for decimals: 1.234,56",
                        max_chars=20,
                    ),
                    "category": st.column_config.TextColumn(
                        "Category",
                        help="Optional category",
                        max_chars=30,
                    ),
                    "confidence": st.column_config.NumberColumn(
                        "Confidence",
                        help="Extraction confidence score",
                        min_value=0.0,
                        max_value=1.0,
                        format="%.2f",
                        disabled=True,
                    ),
                    "source": st.column_config.TextColumn(
                        "Source",
                        help="Extraction source",
                        disabled=True,
                    ),
                }
            )
            
            # Update session state
            st.session_state.transactions_df = edited_df
    
    # Validation section
    st.header("✅ Validation")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        if st.button("🔍 Validate Against Golden", type="secondary"):
            transactions = dataframe_to_transactions(st.session_state.transactions_df)
            with st.spinner("Running validation..."):
                validation_result = run_validation(
                    transactions, 
                    st.session_state.selected_pdf
                )
                st.session_state.validation_result = validation_result
    
    with col2:
        if st.button("💾 Save as Golden", type="primary"):
            transactions = dataframe_to_transactions(st.session_state.transactions_df)
            
            try:
                validator = GoldenValidator(Path("data/golden"))
                golden_path = validator.create_golden_from_transactions(
                    st.session_state.selected_pdf,
                    transactions
                )
                st.success(f"✅ Golden file saved: {golden_path.name}")
                
                # Also run validation
                validation_result = run_validation(
                    transactions, 
                    st.session_state.selected_pdf
                )
                st.session_state.validation_result = validation_result
                
            except Exception as e:
                st.error(f"❌ Failed to save golden file: {e}")
    
    # Display validation results
    if st.session_state.validation_result:
        result = st.session_state.validation_result
        
        st.subheader("Validation Results")
        
        # Status indicator
        if result['is_valid']:
            st.success("🎉 Validation PASSED!")
        else:
            st.error("❌ Validation FAILED")
        
        # Metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Cell Accuracy", f"{result['cell_accuracy']:.1%}")
        
        with col2:
            st.metric("Precision", f"{result['precision']:.1%}")
        
        with col3:
            st.metric("Recall", f"{result['recall']:.1%}")
        
        with col4:
            st.metric("F1 Score", f"{result['f1_score']:.1%}")
        
        # Additional details
        col1, col2 = st.columns(2)
        
        with col1:
            count_match = "✅" if result['transaction_count_match'] else "❌"
            st.markdown(f"**Transaction Count Match:** {count_match}")
            
            total_match = "✅" if result['total_amount_match'] else "❌"
            st.markdown(f"**Total Amount Match:** {total_match}")
        
        with col2:
            st.markdown(f"**Amount Difference:** R$ {result['amount_difference_brl']:.2f}")
        
        # Mismatches
        if result['mismatched_cells']:
            st.subheader("Mismatches")
            for mismatch in result['mismatched_cells']:
                st.text(f"• {mismatch}")
    
    # Footer
    st.markdown("---")
    st.markdown(
        "💡 **Tip:** Low-confidence cells are highlighted in red. "
        "Review and edit them before saving as golden files."
    )


if __name__ == "__main__":
    main()
