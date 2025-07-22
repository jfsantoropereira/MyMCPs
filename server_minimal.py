"""
Minimal Brazilian Finance MCP Server
A simplified version that runs without heavy dependencies for demonstration.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample data to simulate the MCP resources
SAMPLE_DATA = {
    "fund_daily": [
        {
            "fund_cnpj": "12.345.678/0001-00",
            "date": "2023-12-01",
            "quota_value": 1.234567,
            "net_assets": 1000000.50,
            "total_assets": 1100000.50,
            "daily_inflow": 50000.00,
            "daily_outflow": 25000.00,
            "investors": 150
        },
        {
            "fund_cnpj": "98.765.432/0001-00", 
            "date": "2023-12-01",
            "quota_value": 2.345678,
            "net_assets": 2000000.75,
            "total_assets": 2100000.75,
            "daily_inflow": 75000.00,
            "daily_outflow": 35000.00,
            "investors": 200
        }
    ],
    "timeseries": [
        {"series_id": "IPCA", "date": "2023-12-01", "value": 10.50, "series_name": "IPCA Inflation"},
        {"series_id": "SELIC", "date": "2023-12-01", "value": 11.75, "series_name": "SELIC Rate"},
        {"series_id": "USD_BRL", "date": "2023-12-01", "value": 5.15, "series_name": "USD/BRL Exchange Rate"}
    ],
    "ibge_indicator": [
        {"indicator_id": 1736, "region_code": "BR", "date": "2023-11-01", "value": 10.2, "unit": "%", "indicator_name": "IPCA"},
        {"indicator_id": 1846, "region_code": "BR", "date": "2023-09-01", "value": 2.1, "unit": "%", "indicator_name": "GDP"}
    ],
    "bank_products": [
        {
            "bank_id": "banco_do_brasil",
            "product_type": "Personal Loan",
            "data_fetch_date": "2023-12-01",
            "json_details": '{"product_name": "Empréstimo Consignado", "min_rate": 0.8, "max_rate": 2.5}'
        }
    ]
}

if FASTAPI_AVAILABLE:
    # FastAPI app
    app = FastAPI(
        title="Brazilian Finance MCP Server (Minimal)",
        description="Minimal Model Context Protocol server for Brazilian financial data",
        version="1.0.0"
    )

    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "timestamp": datetime.now().isoformat()}

    @app.get("/mcp/resources/list")
    async def list_resources():
        """List all available MCP resources"""
        resources = [
            {
                "uri": "duckdb://finance/fund_daily",
                "name": "Investment Fund Daily Data",
                "description": f"Daily NAV and flow data ({len(SAMPLE_DATA['fund_daily'])} sample records)",
                "mimeType": "application/json"
            },
            {
                "uri": "duckdb://finance/timeseries",
                "name": "Economic Time Series",
                "description": f"Historical economic indicators ({len(SAMPLE_DATA['timeseries'])} sample series)",
                "mimeType": "application/json"
            },
            {
                "uri": "duckdb://finance/ibge_indicator",
                "name": "IBGE Statistical Indicators",
                "description": f"Official statistics from IBGE ({len(SAMPLE_DATA['ibge_indicator'])} sample indicators)",
                "mimeType": "application/json"
            },
            {
                "uri": "duckdb://finance/bank_products",
                "name": "Banking & Insurance Products", 
                "description": f"Open Finance product data ({len(SAMPLE_DATA['bank_products'])} sample products)",
                "mimeType": "application/json"
            }
        ]
        return JSONResponse({"resources": resources})

    @app.get("/mcp/resources/read")
    async def read_resource(uri: str):
        """Read a specific MCP resource"""
        try:
            if uri == "duckdb://finance/fund_daily":
                data = SAMPLE_DATA["fund_daily"]
            elif uri == "duckdb://finance/timeseries":
                data = SAMPLE_DATA["timeseries"]
            elif uri.startswith("duckdb://finance/timeseries/series="):
                series_id = uri.split("=")[1]
                data = [item for item in SAMPLE_DATA["timeseries"] if item["series_id"] == series_id]
            elif uri == "duckdb://finance/ibge_indicator":
                data = SAMPLE_DATA["ibge_indicator"]
            elif uri == "duckdb://finance/bank_products":
                data = SAMPLE_DATA["bank_products"]
            else:
                raise HTTPException(status_code=404, detail=f"Resource not found: {uri}")
            
            return JSONResponse({
                "contents": [{
                    "type": "text",
                    "text": f"Sample data from {uri}:\n{len(data)} records retrieved"
                }, {
                    "type": "resource",
                    "resource": {
                        "uri": uri,
                        "data": data
                    }
                }]
            })
            
        except Exception as e:
            logger.error(f"Error reading resource {uri}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/mcp/tools/list")
    async def list_tools():
        """List all available MCP tools"""
        tools = [
            {
                "name": "query_sample_data",
                "description": "Query sample Brazilian finance data",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "table": {
                            "type": "string",
                            "description": "Table to query",
                            "enum": ["fund_daily", "timeseries", "ibge_indicator", "bank_products"]
                        },
                        "filter": {
                            "type": "string", 
                            "description": "Optional filter criteria"
                        }
                    },
                    "required": ["table"]
                }
            }
        ]
        return JSONResponse({"tools": tools})

    @app.post("/mcp/tools/call")
    async def call_tool(request: dict):
        """Execute an MCP tool"""
        try:
            tool_name = request.get("name")
            arguments = request.get("arguments", {})
            
            if tool_name == "query_sample_data":
                table = arguments.get("table")
                filter_criteria = arguments.get("filter", "")
                
                if table not in SAMPLE_DATA:
                    return JSONResponse({
                        "content": [{
                            "type": "text",
                            "text": f"Error: Unknown table '{table}'"
                        }],
                        "isError": True
                    })
                
                data = SAMPLE_DATA[table]
                
                # Apply simple filtering if specified
                if filter_criteria:
                    # Simple string matching for demo
                    data = [item for item in data if filter_criteria.lower() in str(item).lower()]
                
                return JSONResponse({
                    "content": [{
                        "type": "text",
                        "text": f"Query executed successfully on {table}. {len(data)} records returned."
                    }, {
                        "type": "resource",
                        "resource": {
                            "data": data,
                            "table": table,
                            "filter": filter_criteria
                        }
                    }]
                })
            else:
                return JSONResponse({
                    "content": [{
                        "type": "text",
                        "text": f"Error: Unknown tool '{tool_name}'"
                    }],
                    "isError": True
                })
                
        except Exception as e:
            logger.error(f"Error executing tool: {e}")
            return JSONResponse({
                "content": [{
                    "type": "text",
                    "text": f"Error executing tool: {str(e)}"
                }],
                "isError": True
            })

    if __name__ == "__main__":
        import uvicorn
        print("🇧🇷 Starting Brazilian Finance MCP Server (Minimal Version)")
        print("📊 Server provides sample Brazilian financial data via MCP protocol")
        print("🔗 Available at: http://localhost:8000")
        print("📋 Resources: /mcp/resources/list")
        print("🛠️  Tools: /mcp/tools/list") 
        print("❤️  Health: /health")
        uvicorn.run(app, host="0.0.0.0", port=8000)

else:
    # Fallback HTTP server if FastAPI not available
    import http.server
    import socketserver
    from urllib.parse import urlparse, parse_qs
    
    class MCPHandler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query = parse_qs(parsed_path.query)
            
            if path == "/health":
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response = {"status": "healthy", "timestamp": datetime.now().isoformat()}
                self.wfile.write(json.dumps(response).encode())
                
            elif path == "/mcp/resources/list":
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                resources = [
                    {
                        "uri": "duckdb://finance/fund_daily",
                        "name": "Investment Fund Daily Data",
                        "description": f"Sample fund data ({len(SAMPLE_DATA['fund_daily'])} records)",
                        "mimeType": "application/json"
                    }
                ]
                response = {"resources": resources}
                self.wfile.write(json.dumps(response).encode())
                
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not Found")
    
    if __name__ == "__main__":
        PORT = 8000
        with socketserver.TCPServer(("", PORT), MCPHandler) as httpd:
            print(f"🇧🇷 Brazilian Finance MCP Server (Basic HTTP) running on port {PORT}")
            print(f"🔗 Available at: http://localhost:{PORT}")
            httpd.serve_forever()