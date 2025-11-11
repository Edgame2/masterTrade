#!/usr/bin/env python3
import sys

# Try importing api_endpoints and checking create_strategy_api
try:
    from api_endpoints import create_strategy_api
    print(f"✅ Import successful!")
    print(f"Type: {type(create_strategy_api)}")
    print(f"Is function: {callable(create_strategy_api)}")
    
    # Try creating a dummy app
    class DummyService:
        pass
    
    service = DummyService()
    app = create_strategy_api(service)
    print(f"App type: {type(app)}")
    print(f"App has routes: {hasattr(app, 'routes')}")
    if hasattr(app, 'routes'):
        print(f"Number of routes: {len(app.routes)}")
        for route in list(app.routes)[:5]:
            print(f"  - {route}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
