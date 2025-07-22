"""
Brazilian Finance MCP Server
FastAPI server implementing the Model Context Protocol for Brazilian financial data.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import duckdb
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pydantic import BaseModel

# Import connectors
from connectors import cvm, bcb, ibge, tesouro, anbima, susep, open_finance

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Brazilian Finance MCP Server",
    description="Model Context Protocol server for Brazilian financial data",
    version="1.0.0"
)

# Global database path
DB_PATH = "finance.duckdb"

# Scheduler for background tasks
scheduler = AsyncIOScheduler()


# MCP Protocol Models
class MCPResource(BaseModel):
    uri: str
    name: str
    description: str
    mimeType: str


class MCPTool(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]


class MCPToolCall(BaseModel):
    name: str
    arguments: Dict[str, Any]


class MCPToolResponse(BaseModel):
    content: List[Dict[str, Any]]
    isError: Optional[bool] = False


# Database initialization
async def init_database():
    """Initialize DuckDB database with schema"""
    conn = duckdb.connect(DB_PATH)
    try:
        # Create schema
        conn.execute("CREATE SCHEMA IF NOT EXISTS finance;")
        
        # Create tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finance.fund_daily (
                fund_cnpj VARCHAR,
                date DATE,
                quota_value DECIMAL(16,6),
                net_assets DECIMAL(20,2),
                total_assets DECIMAL(20,2),
                daily_inflow DECIMAL(16,2),
                daily_outflow DECIMAL(16,2),
                investors INT,
                PRIMARY KEY(fund_cnpj, date)
            );
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finance.timeseries (
                series_id VARCHAR,
                date DATE,
                value DOUBLE,
                series_name TEXT,
                PRIMARY KEY(series_id, date)
            );
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finance.ibge_indicator (
                indicator_id INT,
                region_code VARCHAR,
                date DATE,
                value DOUBLE,
                unit TEXT,
                indicator_name TEXT,
                PRIMARY KEY(indicator_id, region_code, date)
            );
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS finance.bank_products (
                bank_id VARCHAR,
                product_type TEXT,
                data_fetch_date DATE,
                json_details JSON
            );
        """)
        
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
    finally:
        conn.close()


# Connector scheduling
async def run_all_connectors():
    """Run all data connectors"""
    logger.info("Starting full data update")
    
    tasks = [
        cvm.run(),
        bcb.run(),
        ibge.run(),
        tesouro.run(),
        anbima.run(),
        susep.run(),
        open_finance.run()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for i, result in enumerate(results):
        connector_name = ['CVM', 'BCB', 'IBGE', 'Tesouro', 'ANBIMA', 'SUSEP', 'Open Finance'][i]
        if isinstance(result, Exception):
            logger.error(f"{connector_name} connector failed: {result}")
        else:
            logger.info(f"{connector_name} connector completed: {result}")
    
    logger.info("Full data update completed")


# MCP Endpoints

@app.get("/mcp/resources/list")
async def list_resources() -> JSONResponse:
    """List all available MCP resources"""
    
    resources = []
    conn = duckdb.connect(DB_PATH)
    
    try:
        # Get fund resources
        fund_count = conn.execute("SELECT COUNT(*) FROM finance.fund_daily").fetchone()[0]
        if fund_count > 0:
            latest_date = conn.execute("SELECT MAX(date) FROM finance.fund_daily").fetchone()[0]
            resources.append(MCPResource(
                uri="duckdb://finance/fund_daily",
                name="Investment Fund Daily Data",
                description=f"Daily NAV and flow data for {fund_count} fund records (latest: {latest_date})",
                mimeType="application/json"
            ))
        
        # Get time series resources
        series_result = conn.execute("""
            SELECT series_id, series_name, COUNT(*) as count, MAX(date) as latest_date
            FROM finance.timeseries 
            GROUP BY series_id, series_name
        """).fetchall()
        
        for series_id, series_name, count, latest_date in series_result:
            resources.append(MCPResource(
                uri=f"duckdb://finance/timeseries/series={series_id}",
                name=f"{series_name} Time Series",
                description=f"Historical data for {series_name} ({count} observations, latest: {latest_date})",
                mimeType="application/json"
            ))
        
        # Get IBGE indicator resources
        ibge_result = conn.execute("""
            SELECT indicator_name, COUNT(*) as count, MAX(date) as latest_date
            FROM finance.ibge_indicator 
            GROUP BY indicator_name
        """).fetchall()
        
        for indicator_name, count, latest_date in ibge_result:
            resources.append(MCPResource(
                uri=f"duckdb://finance/ibge_indicator/indicator={indicator_name}",
                name=f"IBGE {indicator_name}",
                description=f"IBGE statistical data for {indicator_name} ({count} observations, latest: {latest_date})",
                mimeType="application/json"
            ))
        
        # Get bank products resources
        product_count = conn.execute("SELECT COUNT(*) FROM finance.bank_products").fetchone()[0]
        if product_count > 0:
            resources.append(MCPResource(
                uri="duckdb://finance/bank_products",
                name="Banking & Insurance Products",
                description=f"Open Finance product data ({product_count} products)",
                mimeType="application/json"
            ))
            
    except Exception as e:
        logger.error(f"Error listing resources: {e}")
    finally:
        conn.close()
    
    return JSONResponse({"resources": [r.dict() for r in resources]})


@app.get("/mcp/resources/read")
async def read_resource(uri: str) -> JSONResponse:
    """Read a specific MCP resource"""
    
    try:
        conn = duckdb.connect(DB_PATH)
        
        if uri.startswith("duckdb://finance/"):
            table_part = uri.replace("duckdb://finance/", "")
            
            if table_part == "fund_daily":
                # Return recent fund data
                result = conn.execute("""
                    SELECT * FROM finance.fund_daily 
                    WHERE date >= CURRENT_DATE - INTERVAL 30 DAYS
                    ORDER BY date DESC, net_assets DESC
                    LIMIT 1000
                """).fetchdf()
                
            elif table_part.startswith("timeseries/series="):
                series_id = table_part.split("=")[1]
                result = conn.execute("""
                    SELECT * FROM finance.timeseries 
                    WHERE series_id = ?
                    ORDER BY date DESC
                    LIMIT 1000
                """, [series_id]).fetchdf()
                
            elif table_part.startswith("ibge_indicator/indicator="):
                indicator_name = table_part.split("=")[1]
                result = conn.execute("""
                    SELECT * FROM finance.ibge_indicator 
                    WHERE indicator_name = ?
                    ORDER BY date DESC
                    LIMIT 1000
                """, [indicator_name]).fetchdf()
                
            elif table_part == "bank_products":
                result = conn.execute("""
                    SELECT * FROM finance.bank_products 
                    ORDER BY data_fetch_date DESC
                    LIMIT 1000
                """).fetchdf()
                
            else:
                raise HTTPException(status_code=404, detail=f"Resource not found: {uri}")
            
            # Convert DataFrame to JSON
            data = result.to_dict('records')
            
            return JSONResponse({
                "contents": [{
                    "type": "text",
                    "text": f"Data from {uri}:\n{len(data)} records retrieved"
                }, {
                    "type": "resource", 
                    "resource": {
                        "uri": uri,
                        "data": data
                    }
                }]
            })
            
        else:
            raise HTTPException(status_code=404, detail=f"Unsupported URI scheme: {uri}")
            
    except Exception as e:
        logger.error(f"Error reading resource {uri}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals():
            conn.close()


@app.get("/mcp/tools/list")
async def list_tools() -> JSONResponse:
    """List all available MCP tools"""
    
    tools = [
        MCPTool(
            name="sql_query",
            description="Execute read-only SQL queries on the Brazilian finance database",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "SQL query to execute (SELECT statements only)"
                    }
                },
                "required": ["query"]
            }
        ),
        MCPTool(
            name="refresh_data",
            description="Trigger a data refresh for all connectors",
            inputSchema={
                "type": "object",
                "properties": {
                    "connector": {
                        "type": "string",
                        "description": "Specific connector to refresh (optional)",
                        "enum": ["cvm", "bcb", "ibge", "tesouro", "anbima", "susep", "open_finance", "all"]
                    }
                }
            }
        )
    ]
    
    return JSONResponse({"tools": [t.dict() for t in tools]})


@app.post("/mcp/tools/call")
async def call_tool(request: MCPToolCall) -> JSONResponse:
    """Execute an MCP tool"""
    
    try:
        if request.name == "sql_query":
            query = request.arguments.get("query", "").strip()
            
            # Security check - only allow SELECT statements
            if not query.upper().startswith("SELECT"):
                return JSONResponse({
                    "content": [{
                        "type": "text",
                        "text": "Error: Only SELECT queries are allowed for security reasons"
                    }],
                    "isError": True
                })
            
            # Execute query
            conn = duckdb.connect(DB_PATH)
            try:
                result = conn.execute(query).fetchdf()
                
                return JSONResponse({
                    "content": [{
                        "type": "text",
                        "text": f"Query executed successfully. {len(result)} rows returned."
                    }, {
                        "type": "resource",
                        "resource": {
                            "data": result.to_dict('records'),
                            "query": query
                        }
                    }]
                })
                
            finally:
                conn.close()
                
        elif request.name == "refresh_data":
            connector = request.arguments.get("connector", "all")
            
            if connector == "all":
                # Trigger background refresh
                asyncio.create_task(run_all_connectors())
                message = "Full data refresh started in background"
            else:
                # Trigger specific connector
                connector_map = {
                    "cvm": cvm.run,
                    "bcb": bcb.run, 
                    "ibge": ibge.run,
                    "tesouro": tesouro.run,
                    "anbima": anbima.run,
                    "susep": susep.run,
                    "open_finance": open_finance.run
                }
                
                if connector in connector_map:
                    asyncio.create_task(connector_map[connector]())
                    message = f"{connector.upper()} data refresh started in background"
                else:
                    return JSONResponse({
                        "content": [{
                            "type": "text", 
                            "text": f"Error: Unknown connector '{connector}'"
                        }],
                        "isError": True
                    })
            
            return JSONResponse({
                "content": [{
                    "type": "text",
                    "text": message
                }]
            })
            
        else:
            return JSONResponse({
                "content": [{
                    "type": "text",
                    "text": f"Error: Unknown tool '{request.name}'"
                }],
                "isError": True
            })
            
    except Exception as e:
        logger.error(f"Error executing tool {request.name}: {e}")
        return JSONResponse({
            "content": [{
                "type": "text",
                "text": f"Error executing tool: {str(e)}"
            }],
            "isError": True
        })


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database and schedule data updates"""
    await init_database()
    
    # Schedule data updates
    scheduler.add_job(
        run_all_connectors,
        CronTrigger(hour=9, minute=0),  # Daily at 9 AM
        id="daily_update",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("MCP Server started successfully")


# Shutdown event
@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup on shutdown"""
    scheduler.shutdown()
    logger.info("MCP Server shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)