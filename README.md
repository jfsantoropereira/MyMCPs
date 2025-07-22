# Brazilian Finance MCP Server

A comprehensive Model Context Protocol (MCP) server that provides access to Brazilian financial data from official government sources. This server acts as a "USB-C for AI" bridge, connecting Claude and other AI assistants to authoritative Brazilian economic and financial datasets.

## 🇧🇷 Overview

This MCP server aggregates data from Brazil's key financial regulators and institutions:

- **CVM** (Comissão de Valores Mobiliários) - Investment fund daily reports
- **BCB** (Banco Central do Brasil) - Economic time series (SELIC, IPCA, USD rates, etc.)
- **IBGE** (Instituto Brasileiro de Geografia e Estatística) - Statistical indicators  
- **Tesouro Nacional** - Public debt and fiscal data
- **ANBIMA** - Market data and bond prices
- **SUSEP** - Insurance market statistics
- **Open Finance** - Banking and insurance product information

All data is stored locally in a DuckDB database and served through standardized MCP resources and tools, ensuring compliance with regulatory requirements while providing rich context for AI financial analysis.

## 🏗️ Architecture

```mermaid
flowchart LR
    subgraph External_Sources ["Free Finance Data Sources (BR)"]
       A[CVM<br/>Funds Daily] -->|CSV API| HUB
       B[BCB SGS<br/>Time Series] -->|REST JSON| HUB
       C[IBGE SIDRA<br/>Statistics] -->|REST JSON| HUB
       D[Tesouro<br/>Fiscal & Debt] -->|REST/CSV API| HUB
       E[ANBIMA v2<br/>Market Data] -->|OAuth API| HUB
       F[SUSEP<br/>Insurance Data] -->|Open data CSV| HUB
       G[Open Finance APIs<br/>(banks/insurers)] -->|Public REST| HUB
    end
    subgraph Local_MCP_Hub ["Local MCP Server (FastAPI + MCP SDK)"]
       direction TB
       connectors[(Async Connectors)] --> db[(DuckDB<br/>(Iceberg Tables))]
       db --> api[FastAPI<br/>MCP Endpoints]
       api --> connectors:::ctrl 
       classDef ctrl fill:#cee,stroke:#000,stroke-width:1px;
    end
    HUB[[Local ETL Jobs]] -.->|scheduled (cron/Prefect)| connectors
    client[Claude (LLM) 📥] -- MCP protocol --> api
    api -- context (resources/tools) --> client
```

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone and navigate to the project
git clone <repository-url>
cd brazilian-finance-mcp

# Set up environment variables (optional - for ANBIMA API)
echo "ANBIMA_CLIENT_ID=your_client_id" > .env
echo "ANBIMA_CLIENT_SECRET=your_client_secret" >> .env

# Deploy with Docker Compose
make deploy

# Check health
make health
```

The server will be available at `http://localhost:8000` with automatic data updates scheduled daily at 9 AM.

### Local Development

```bash
# Install dependencies
make install

# Run the server locally
make run

# In another terminal, trigger initial data load
make update-data
```

## 📊 Available Resources

The MCP server exposes the following resources:

### Investment Fund Daily Data
- **URI**: `duckdb://finance/fund_daily`
- **Source**: CVM (Comissão de Valores Mobiliários)
- **Content**: Daily NAV, asset values, flows, and investor counts for Brazilian investment funds
- **Update Frequency**: Daily (T+1)

### Economic Time Series
- **URI**: `duckdb://finance/timeseries`
- **Sources**: BCB SGS, ANBIMA, Tesouro Nacional
- **Content**: Key economic indicators including:
  - IPCA inflation rate
  - SELIC interest rate  
  - USD/BRL exchange rate
  - CDI rate
  - Government bond yields
  - Market indices
- **Update Frequency**: Daily for most series

### IBGE Statistical Indicators
- **URI**: `duckdb://finance/ibge_indicator`
- **Source**: IBGE SIDRA API
- **Content**: Official statistics including GDP, unemployment, industrial production
- **Update Frequency**: Monthly/Quarterly based on release calendar

### Banking & Insurance Products
- **URI**: `duckdb://finance/bank_products`
- **Sources**: Open Finance APIs, SUSEP
- **Content**: Product offerings, rates, and terms from major financial institutions
- **Update Frequency**: Weekly

## 🛠️ Available Tools

### SQL Query Tool
Execute read-only SQL queries against the financial database:

```json
{
  "name": "sql_query",
  "arguments": {
    "query": "SELECT AVG(quota_value) as avg_nav FROM finance.fund_daily WHERE date >= '2023-12-01'"
  }
}
```

### Data Refresh Tool
Trigger data updates for specific connectors:

```json
{
  "name": "refresh_data", 
  "arguments": {
    "connector": "all"  // or "cvm", "bcb", "ibge", etc.
  }
}
```

## 📋 Data Sources Details

| Source | Base URL | Auth Required | Update Frequency | Key Data |
|--------|----------|---------------|------------------|----------|
| **CVM** | dados.cvm.gov.br | No | Daily (T+1) | Fund NAV, flows, assets |
| **BCB SGS** | api.bcb.gov.br | No | Daily/Monthly | Interest rates, FX, inflation |
| **IBGE SIDRA** | servicodados.ibge.gov.br | No | Monthly/Quarterly | GDP, unemployment, indices |
| **Tesouro** | api.tesourotransparente.gov.br | No | Monthly/Daily | Public debt, fiscal data |
| **ANBIMA** | api.anbima.com.br | OAuth2 | Daily | Bond prices, market indices |
| **SUSEP** | www2.susep.gov.br | No | Quarterly | Insurance premiums, claims |
| **Open Finance** | Various bank APIs | No | Weekly | Banking/insurance products |

## 🔧 Configuration

### Environment Variables

- `ANBIMA_CLIENT_ID`: ANBIMA API client ID (optional)
- `ANBIMA_CLIENT_SECRET`: ANBIMA API client secret (optional)
- `LOG_LEVEL`: Logging level (default: INFO)

### Database Schema

The server creates the following tables in DuckDB:

```sql
-- Investment fund data
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

-- Economic time series
CREATE TABLE finance.timeseries (
    series_id VARCHAR,
    date DATE,
    value DOUBLE,
    series_name TEXT,
    PRIMARY KEY(series_id, date)
);

-- IBGE indicators with regional breakdown
CREATE TABLE finance.ibge_indicator (
    indicator_id INT,
    region_code VARCHAR,
    date DATE,
    value DOUBLE,
    unit TEXT,
    indicator_name TEXT,
    PRIMARY KEY(indicator_id, region_code, date)
);

-- Banking and insurance products
CREATE TABLE finance.bank_products (
    bank_id VARCHAR,
    product_type TEXT,
    data_fetch_date DATE,
    json_details JSON
);
```

## 📖 API Reference

### MCP Endpoints

- `GET /mcp/resources/list` - List all available resources
- `GET /mcp/resources/read?uri=<resource_uri>` - Read specific resource
- `GET /mcp/tools/list` - List all available tools
- `POST /mcp/tools/call` - Execute a tool

### Health & Management

- `GET /health` - Health check
- Server automatically schedules data updates daily at 9:00 AM

## 🧪 Testing

```bash
# Run all tests
make test

# Run specific test file
pytest tests/test_connectors.py -v

# Run with coverage
pytest --cov=. tests/
```

## 🐳 Deployment Options

### Docker Compose (Production)
```bash
make deploy
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: brazilian-finance-mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: brazilian-finance-mcp
  template:
    spec:
      containers:
      - name: mcp-server
        image: brazilian-finance-mcp:latest
        ports:
        - containerPort: 8000
        env:
        - name: ANBIMA_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: anbima-credentials
              key: client-id
```

### Claude Desktop Extension (.dxt)
Package as a Claude Desktop extension for one-click installation:

1. Zip the entire project directory
2. Rename to `brazilian-finance-mcp.dxt`
3. Install via Claude Desktop

## 🔒 Security & Compliance

- **Data Sources**: All data sources are official, public APIs from Brazilian government agencies
- **Authentication**: No hard-coded secrets; environment variables only
- **Access Control**: SQL tool restricted to SELECT statements only
- **Network Security**: Outbound connections limited to known API domains
- **Audit Trail**: All data access and updates are logged

## 🛣️ Roadmap

- [ ] **B3 Market Data Integration**: Real-time stock prices and options data
- [ ] **Enhanced Open Finance**: Support for more banking institutions
- [ ] **Data Quality SLAs**: Automated freshness and accuracy monitoring
- [ ] **Advanced Analytics Tools**: Built-in pandas/numpy query capabilities
- [ ] **Multi-user Support**: Authentication and access control
- [ ] **Cloud Deployment**: AWS/GCP deployment templates

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: Report bugs and feature requests on GitHub
- **Documentation**: Additional docs in the `/docs` folder
- **API Examples**: See `/examples` for usage examples

---

**Note**: This server provides access to public data from Brazilian government sources. Users are responsible for compliance with any applicable data usage policies and regulations.