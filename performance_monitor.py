#!/usr/bin/env python3
"""
Performance monitoring script for RMIT Connect
Monitors response times and database performance
"""

import requests
import time
import json
from datetime import datetime

def check_performance(url):
    """Check performance metrics for the application"""
    results = {
        'timestamp': datetime.now().isoformat(),
        'url': url,
        'metrics': {}
    }
    
    # Test main endpoints
    endpoints = [
        ('/', 'Homepage'),
        ('/login', 'Login Page'),
        ('/health', 'Health Check'),
        ('/robots.txt', 'Robots.txt')
    ]
    
    for endpoint, name in endpoints:
        try:
            start_time = time.time()
            response = requests.get(f"{url}{endpoint}", timeout=30)
            end_time = time.time()
            
            response_time = (end_time - start_time) * 1000  # in milliseconds
            
            results['metrics'][endpoint] = {
                'name': name,
                'status_code': response.status_code,
                'response_time_ms': round(response_time, 2),
                'content_length': len(response.content),
                'content_type': response.headers.get('content-type', 'unknown')
            }
            
            print(f"✅ {name}: {response.status_code} - {response_time:.2f}ms")
            
        except requests.exceptions.RequestException as e:
            results['metrics'][endpoint] = {
                'name': name,
                'error': str(e),
                'response_time_ms': None
            }
            print(f"❌ {name}: Error - {str(e)}")
    
    # Calculate average response time
    response_times = [m['response_time_ms'] for m in results['metrics'].values() 
                     if m.get('response_time_ms') is not None]
    
    if response_times:
        results['average_response_time_ms'] = round(sum(response_times) / len(response_times), 2)
        print(f"\n📊 Average response time: {results['average_response_time_ms']:.2f}ms")
    
    return results

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Default to Render URL
        url = "https://rmit-connect.onrender.com"
    
    print(f"🔍 Testing performance for: {url}")
    print("=" * 50)
    
    results = check_performance(url)
    
    # Save results to file
    with open('performance_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to performance_results.json")
