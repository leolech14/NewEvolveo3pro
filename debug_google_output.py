#!/usr/bin/env python3.13
"""Debug Google Document AI raw output to see what we're actually getting."""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from google.cloud import documentai


def debug_google_processor(processor_id: str, processor_name: str):
    """Debug a single Google processor to see raw output."""
    print(f"\n🔍 Debugging {processor_name} (ID: {processor_id})")
    print("=" * 60)
    
    try:
        # Initialize client
        client = documentai.DocumentProcessorServiceClient()
        name = f"projects/astute-buttress-340100/locations/us/processors/{processor_id}"
        
        # Read PDF
        with open("data/incoming/Itau_2024-10.pdf", "rb") as f:
            file_content = f.read()
        
        # Process document
        raw_document = documentai.RawDocument(
            content=file_content,
            mime_type="application/pdf"
        )
        
        request = documentai.ProcessRequest(
            name=name,
            raw_document=raw_document
        )
        
        result = client.process_document(request=request)
        document = result.document
        
        # Basic stats
        print(f"📄 Text length: {len(document.text):,} characters")
        print(f"📄 Pages: {len(document.pages)}")
        print(f"🏷️ Entities: {len(document.entities)}")
        
        # Show sample text
        print(f"\n📝 Sample text (first 500 chars):")
        print(document.text[:500] + "..." if len(document.text) > 500 else document.text)
        
        # Show entities
        if document.entities:
            print(f"\n🏷️ Entities found:")
            for i, entity in enumerate(document.entities[:10]):  # Show first 10
                print(f"  {i+1}. Type: {entity.type_}, Text: '{entity.mention_text}', Confidence: {entity.confidence:.2f}")
            if len(document.entities) > 10:
                print(f"  ... and {len(document.entities) - 10} more entities")
        else:
            print("\n❌ No entities found")
        
        # Check tables
        table_count = 0
        for page in document.pages:
            table_count += len(page.tables)
        print(f"\n📋 Tables found: {table_count}")
        
        if table_count > 0:
            print(f"📋 Table details:")
            for page_idx, page in enumerate(document.pages):
                for table_idx, table in enumerate(page.tables):
                    print(f"  Page {page_idx+1}, Table {table_idx+1}: {len(table.header_rows)} header rows, {len(table.body_rows)} body rows")
                    
                    # Show sample table data
                    if table.body_rows:
                        print(f"    Sample row:")
                        row = table.body_rows[0]
                        for cell_idx, cell in enumerate(row.cells[:3]):  # First 3 cells
                            cell_text = ""
                            for segment in cell.layout.text_anchor.text_segments:
                                start = segment.start_index
                                end = segment.end_index
                                cell_text += document.text[start:end]
                            print(f"      Cell {cell_idx+1}: '{cell_text.strip()}'")
        
        # Check paragraphs
        paragraph_count = 0
        for page in document.pages:
            paragraph_count += len(page.paragraphs)
        print(f"\n📄 Paragraphs found: {paragraph_count}")
        
        if paragraph_count > 0 and paragraph_count <= 20:  # Show if reasonable number
            print(f"📄 Paragraph sample:")
            for page_idx, page in enumerate(document.pages):
                for para_idx, paragraph in enumerate(page.paragraphs[:5]):  # First 5
                    para_text = ""
                    for segment in paragraph.layout.text_anchor.text_segments:
                        start = segment.start_index
                        end = segment.end_index
                        para_text += document.text[start:end]
                    print(f"  Para {para_idx+1}: '{para_text.strip()[:100]}...'")
        
        print(f"\n✅ {processor_name} debugging complete")
        return True
        
    except Exception as e:
        print(f"❌ Error debugging {processor_name}: {e}")
        return False


def main():
    """Debug all Google processors to understand their output."""
    
    processors = {
        "Layout Parser": "ea82aadd432354bb",
        "Form Parser": "bc355294420e2170", 
        "Bank Statement": "bea9ee5b01ed7757",
        "Invoice Parser": "12285df95374de04",
        "Document OCR": "4d60398122b91702",
    }
    
    print("🔍 Google Document AI Debug Session")
    print("📄 File: data/incoming/Itau_2024-10.pdf")
    print("🎯 Goal: Understand what each processor returns")
    
    for name, processor_id in processors.items():
        success = debug_google_processor(processor_id, name)
        if not success:
            print(f"⚠️ Skipping {name} due to error")
    
    print(f"\n🏁 Debug session complete!")


if __name__ == "__main__":
    main()
