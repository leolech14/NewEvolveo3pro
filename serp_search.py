"""SerpAPI integration for merchant/company lookup."""

import os
from typing import List, Dict, Optional

try:
    from serpapi import GoogleSearch
    SERPAPI_AVAILABLE = True
except ImportError:
    SERPAPI_AVAILABLE = False
    print("⚠️  SerpAPI not installed. Run: pip install serpapi")


def search_company(company_name: str, country: str = "br") -> List[Dict]:
    """Search for company information using SerpAPI."""
    if not SERPAPI_AVAILABLE:
        return []
    
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        print("❌ SERPAPI_API_KEY not found in environment variables")
        return []
    
    params = {
        "engine": "google",
        "q": f"{company_name} site:linkedin.com OR site:bloomberg.com",
        "gl": country,  # Country (br for Brazil)
        "hl": "pt",     # Language (Portuguese)
        "api_key": api_key,
        "num": 5        # Limit results
    }
    
    try:
        search = GoogleSearch(params)
        results = search.get_dict()
        return results.get("organic_results", [])
    except Exception as e:
        print(f"❌ SerpAPI error: {e}")
        return []


def enhance_merchant_data(merchant_name: str) -> Optional[Dict]:
    """Enhance merchant data with web search results."""
    results = search_company(merchant_name)
    
    if not results:
        return None
    
    # Extract useful information from top result
    top_result = results[0]
    enhanced_data = {
        "merchant_name": merchant_name,
        "search_title": top_result.get("title", ""),
        "search_snippet": top_result.get("snippet", ""),
        "search_url": top_result.get("link", ""),
        "total_results": len(results)
    }
    
    return enhanced_data


def batch_enhance_merchants(merchant_list: List[str]) -> Dict[str, Dict]:
    """Enhance multiple merchants with rate limiting."""
    enhanced_merchants = {}
    
    for i, merchant in enumerate(merchant_list):
        print(f"🔍 Searching {i+1}/{len(merchant_list)}: {merchant}")
        enhanced_data = enhance_merchant_data(merchant)
        
        if enhanced_data:
            enhanced_merchants[merchant] = enhanced_data
            print(f"✅ Found: {enhanced_data['search_title']}")
        else:
            print(f"❌ No results for: {merchant}")
        
        # Rate limiting (SerpAPI allows 100 searches/month on free tier)
        if i < len(merchant_list) - 1:
            import time
            time.sleep(1)  # 1 second between requests
    
    return enhanced_merchants


def main():
    """Main function for standalone usage."""
    import sys
    
    if len(sys.argv) > 1:
        # Single company search from command line
        company = sys.argv[1]
        print(f"🔍 Searching for: {company}")
        
        results = search_company(company)
        if results:
            print(f"\n✅ Found {len(results)} results:")
            for i, result in enumerate(results[:3], 1):
                print(f"{i}. {result.get('title', 'No title')}")
                print(f"   🔗 {result.get('link', 'No link')}\n")
        else:
            print("❌ No results found")
    else:
        # Example usage with test merchants
        test_merchants = [
            "Banco Itaú",
            "Farmacia Sao Joao", 
            "Apple",
            "Google"
        ]
        
        print("🌐 Testing SerpAPI integration...")
        results = batch_enhance_merchants(test_merchants)
        
        print("\n📊 Results Summary:")
        for merchant, data in results.items():
            print(f"• {merchant}: {data.get('search_title', 'No title')}")


if __name__ == "__main__":
    main()
