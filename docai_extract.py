"""Google Document AI extraction module for NewEvolveo3pro."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from google.cloud import documentai
    DOCAI_AVAILABLE = True
except ImportError:
    DOCAI_AVAILABLE = False


def process_with_docai(pdf_path: str, processor_type: str = "form") -> Optional[Dict[str, Any]]:
    """
    Process PDF with Google Document AI.
    
    Args:
        pdf_path: Path to PDF file
        processor_type: Type of processor to use (ocr, form, layout, invoice, custom)
    
    Returns:
        Dictionary with extraction results or None if failed
    """
    if not DOCAI_AVAILABLE:
        raise ImportError("google-cloud-documentai not installed. Run: pip install google-cloud-documentai")
    
    # Map processor types to environment variables
    processor_map = {
        "ocr": "DOCAI_OCR_PROCESSOR",
        "form": "DOCAI_FORM_PARSER", 
        "layout": "DOCAI_LAYOUT_PARSER",
        "invoice": "DOCAI_INVOICE_PARSER",
        "custom": "DOCAI_CUSTOM_EXTRACTOR"
    }
    
    if processor_type not in processor_map:
        raise ValueError(f"Unknown processor type: {processor_type}. Available: {list(processor_map.keys())}")
    
    # Get configuration
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_DOCUMENTAI_LOCATION", "us")
    processor_id = os.getenv(processor_map[processor_type])
    
    if not all([project_id, processor_id]):
        missing = []
        if not project_id:
            missing.append("GOOGLE_CLOUD_PROJECT")
        if not processor_id:
            missing.append(processor_map[processor_type])
        raise ValueError(f"Missing environment variables: {missing}")
    
    # Initialize client
    client = documentai.DocumentProcessorServiceClient()
    name = client.processor_path(project_id, location, processor_id)
    
    # Read PDF
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    with open(pdf_path, "rb") as f:
        raw_document = documentai.RawDocument(
            content=f.read(),
            mime_type="application/pdf"
        )
    
    # Process document
    request = documentai.ProcessRequest(
        name=name,
        raw_document=raw_document
    )
    
    result = client.process_document(request=request)
    document = result.document
    
    # Extract structured data
    extraction_result = {
        "processor_type": processor_type,
        "processor_id": processor_id,
        "file": str(pdf_path),
        "text": document.text,
        "text_length": len(document.text),
        "pages": len(document.pages),
        "entities": [],
        "tables": [],
        "form_fields": []
    }
    
    # Extract entities
    for entity in document.entities:
        extraction_result["entities"].append({
            "type": entity.type_,
            "value": entity.text_anchor.content if entity.text_anchor else "",
            "confidence": entity.confidence
        })
    
    # Extract tables (if any)
    for page in document.pages:
        for table in page.tables:
            table_data = []
            for row in table.header_rows + table.body_rows:
                row_data = []
                for cell in row.cells:
                    cell_text = ""
                    if cell.layout and cell.layout.text_anchor:
                        cell_text = cell.layout.text_anchor.content
                    row_data.append(cell_text)
                table_data.append(row_data)
            
            if table_data:
                extraction_result["tables"].append(table_data)
    
    # Extract form fields (if any)
    for page in document.pages:
        for form_field in page.form_fields:
            field_name = ""
            field_value = ""
            
            if form_field.field_name and form_field.field_name.text_anchor:
                field_name = form_field.field_name.text_anchor.content
            
            if form_field.field_value and form_field.field_value.text_anchor:
                field_value = form_field.field_value.text_anchor.content
            
            if field_name or field_value:
                extraction_result["form_fields"].append({
                    "name": field_name,
                    "value": field_value,
                    "confidence": form_field.field_value.confidence if form_field.field_value else 0.0
                })
    
    return extraction_result


def list_available_processors() -> Dict[str, str]:
    """Return mapping of available processor types to their IDs."""
    processor_map = {
        "ocr": "DOCAI_OCR_PROCESSOR",
        "form": "DOCAI_FORM_PARSER", 
        "layout": "DOCAI_LAYOUT_PARSER",
        "invoice": "DOCAI_INVOICE_PARSER",
        "custom": "DOCAI_CUSTOM_EXTRACTOR"
    }
    
    available = {}
    for proc_type, env_var in processor_map.items():
        proc_id = os.getenv(env_var)
        if proc_id:
            available[proc_type] = proc_id
    
    return available


def main():
    """Standalone testing function."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python docai_extract.py <pdf_path> [processor_type]")
        print("Available processor types: ocr, form, layout, invoice, custom")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    processor_type = sys.argv[2] if len(sys.argv) > 2 else "form"
    
    try:
        result = process_with_docai(pdf_path, processor_type)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("No results returned")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
