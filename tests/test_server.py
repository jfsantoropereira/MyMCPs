"""
Tests for MCP server endpoints
"""

import pytest
from fastapi.testclient import TestClient
import json
from unittest.mock import patch, MagicMock
import duckdb

from server import app


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Create in-memory database for testing"""
    conn = duckdb.connect(":memory:")
    
    # Create test schema
    conn.execute("CREATE SCHEMA finance;")
    
    # Create test tables
    conn.execute("""
        CREATE TABLE finance.fund_daily (
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
        CREATE TABLE finance.timeseries (
            series_id VARCHAR,
            date DATE,
            value DOUBLE,
            series_name TEXT,
            PRIMARY KEY(series_id, date)
        );
    """)
    
    # Insert test data
    conn.execute("""
        INSERT INTO finance.fund_daily VALUES
        ('12.345.678/0001-00', '2023-12-01', 1.234567, 1000000.50, 1100000.50, 50000.00, 25000.00, 150),
        ('98.765.432/0001-00', '2023-12-01', 2.345678, 2000000.75, 2100000.75, 75000.00, 35000.00, 200);
    """)
    
    conn.execute("""
        INSERT INTO finance.timeseries VALUES
        ('433', '2023-12-01', 10.50, 'IPCA'),
        ('11', '2023-12-01', 11.75, 'SELIC');
    """)
    
    return conn


class TestHealthCheck:
    """Test health check endpoint"""
    
    def test_health_endpoint(self, client):
        """Test health check returns 200"""
        response = client.get("/health")
        assert response.status_code == 200
        assert "status" in response.json()
        assert response.json()["status"] == "healthy"


class TestMCPResourceEndpoints:
    """Test MCP resource endpoints"""
    
    @patch('duckdb.connect')
    def test_list_resources(self, mock_connect, client, mock_db):
        """Test resources list endpoint"""
        mock_connect.return_value = mock_db
        
        response = client.get("/mcp/resources/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) > 0
        
        # Check resource structure
        resource = data["resources"][0]
        assert "uri" in resource
        assert "name" in resource
        assert "description" in resource
        assert "mimeType" in resource
    
    @patch('duckdb.connect')
    def test_read_fund_resource(self, mock_connect, client, mock_db):
        """Test reading fund daily resource"""
        mock_connect.return_value = mock_db
        
        response = client.get("/mcp/resources/read?uri=duckdb://finance/fund_daily")
        assert response.status_code == 200
        
        data = response.json()
        assert "contents" in data
        assert len(data["contents"]) > 0
    
    @patch('duckdb.connect')
    def test_read_timeseries_resource(self, mock_connect, client, mock_db):
        """Test reading time series resource"""
        mock_connect.return_value = mock_db
        
        response = client.get("/mcp/resources/read?uri=duckdb://finance/timeseries/series=433")
        assert response.status_code == 200
        
        data = response.json()
        assert "contents" in data
    
    def test_read_invalid_resource(self, client):
        """Test reading invalid resource returns 404"""
        response = client.get("/mcp/resources/read?uri=invalid://resource")
        assert response.status_code == 404


class TestMCPToolEndpoints:
    """Test MCP tool endpoints"""
    
    def test_list_tools(self, client):
        """Test tools list endpoint"""
        response = client.get("/mcp/tools/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) > 0
        
        # Check for expected tools
        tool_names = [tool["name"] for tool in data["tools"]]
        assert "sql_query" in tool_names
        assert "refresh_data" in tool_names
    
    @patch('duckdb.connect')
    def test_sql_query_tool(self, mock_connect, client, mock_db):
        """Test SQL query tool execution"""
        mock_connect.return_value = mock_db
        
        request_data = {
            "name": "sql_query",
            "arguments": {
                "query": "SELECT COUNT(*) as count FROM finance.fund_daily"
            }
        }
        
        response = client.post(
            "/mcp/tools/call",
            json=request_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "content" in data
        assert not data.get("isError", False)
    
    def test_sql_query_security_check(self, client):
        """Test SQL query security - only SELECT allowed"""
        request_data = {
            "name": "sql_query",
            "arguments": {
                "query": "DROP TABLE finance.fund_daily"
            }
        }
        
        response = client.post(
            "/mcp/tools/call",
            json=request_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("isError", False) is True
        assert "Only SELECT queries are allowed" in data["content"][0]["text"]
    
    @patch('asyncio.create_task')
    def test_refresh_data_tool(self, mock_create_task, client):
        """Test data refresh tool"""
        request_data = {
            "name": "refresh_data",
            "arguments": {
                "connector": "all"
            }
        }
        
        response = client.post(
            "/mcp/tools/call",
            json=request_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "content" in data
        assert "refresh started" in data["content"][0]["text"]
        
        # Verify task was created
        mock_create_task.assert_called_once()
    
    def test_invalid_tool(self, client):
        """Test calling invalid tool returns error"""
        request_data = {
            "name": "invalid_tool",
            "arguments": {}
        }
        
        response = client.post(
            "/mcp/tools/call",
            json=request_data
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("isError", False) is True
        assert "Unknown tool" in data["content"][0]["text"]


class TestDatabaseOperations:
    """Test database operations"""
    
    def test_database_initialization(self, mock_db):
        """Test database schema creation"""
        # Check tables exist
        tables = mock_db.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'finance'
        """).fetchall()
        
        table_names = [table[0] for table in tables]
        assert 'fund_daily' in table_names
        assert 'timeseries' in table_names
    
    def test_data_insertion(self, mock_db):
        """Test data can be inserted and queried"""
        # Data should already be inserted by fixture
        result = mock_db.execute("SELECT COUNT(*) FROM finance.fund_daily").fetchone()
        assert result[0] == 2
        
        result = mock_db.execute("SELECT COUNT(*) FROM finance.timeseries").fetchone()
        assert result[0] == 2