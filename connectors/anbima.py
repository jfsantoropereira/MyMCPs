"""
ANBIMA (Associação Brasileira das Entidades dos Mercados Financeiro e de Capitais) Connector
Fetches market data from ANBIMA's API v2.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class ANBIMAConnector:
    """Connector for ANBIMA market data"""
    
    BASE_URL = "https://api.anbima.com.br/feed"
    AUTH_URL = "https://api.anbima.com.br/oauth/access-token"
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
        self.access_token = None
        self.token_expires_at = None
        self.client_id = os.getenv("ANBIMA_CLIENT_ID")
        self.client_secret = os.getenv("ANBIMA_CLIENT_SECRET")
        
        if not self.client_id or not self.client_secret:
            logger.warning("ANBIMA credentials not found in environment variables")
    
    async def authenticate(self) -> bool:
        """Get OAuth access token"""
        if not self.client_id or not self.client_secret:
            logger.error("ANBIMA credentials not configured")
            return False
            
        # Check if current token is still valid
        if (self.access_token and self.token_expires_at and 
            datetime.now() < self.token_expires_at):
            return True
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.AUTH_URL,
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "client_credentials"
                    }
                )
                response.raise_for_status()
                
                token_data = response.json()
                self.access_token = token_data["access_token"]
                expires_in = token_data.get("expires_in", 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
                
                logger.info("Successfully authenticated with ANBIMA API")
                return True
                
        except Exception as e:
            logger.error(f"Error authenticating with ANBIMA: {e}")
            return False
    
    async def fetch_funds_data(self, page: int = 1) -> Optional[pd.DataFrame]:
        """Fetch fund data from ANBIMA API"""
        if not await self.authenticate():
            return None
            
        url = f"{self.BASE_URL}/fundos/v2/fundos"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"pagina": page}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching ANBIMA funds data page {page}")
                response = await client.get(url, headers=headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                funds = data.get("fundos", [])
                
                if not funds:
                    logger.info(f"No more funds data on page {page}")
                    return None
                
                df = pd.DataFrame(funds)
                logger.info(f"Fetched {len(df)} funds from page {page}")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching ANBIMA funds page {page}: {e}")
            return None
    
    async def fetch_bond_prices(self) -> Optional[pd.DataFrame]:
        """Fetch government bond prices"""
        if not await self.authenticate():
            return None
            
        url = f"{self.BASE_URL}/precos-indices/v1/titulos-publicos"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info("Fetching ANBIMA bond prices")
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                bonds = data.get("titulosPublicos", [])
                
                if not bonds:
                    logger.warning("No bond data returned")
                    return None
                
                df = pd.DataFrame(bonds)
                logger.info(f"Fetched {len(df)} bond prices")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching ANBIMA bond prices: {e}")
            return None
    
    async def fetch_indices(self) -> Optional[pd.DataFrame]:
        """Fetch market indices"""
        if not await self.authenticate():
            return None
            
        url = f"{self.BASE_URL}/precos-indices/v1/indices"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info("Fetching ANBIMA indices")
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                indices = data.get("indices", [])
                
                if not indices:
                    logger.warning("No indices data returned")
                    return None
                
                df = pd.DataFrame(indices)
                logger.info(f"Fetched {len(df)} indices")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching ANBIMA indices: {e}")
            return None
    
    def transform_fund_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform fund data to our schema"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        try:
            # Map ANBIMA fields to our schema
            # Note: Field names are examples - would need actual ANBIMA API documentation
            fund_mapping = {
                'cnpj': 'fund_cnpj',
                'dataCota': 'date', 
                'valorCota': 'quota_value',
                'patrimonioLiquido': 'net_assets',
                'captacao': 'daily_inflow',
                'resgate': 'daily_outflow'
            }
            
            # Select available columns
            available_cols = [col for col in fund_mapping.keys() if col in df.columns]
            if not available_cols:
                logger.warning("No expected fund columns found in ANBIMA data")
                return pd.DataFrame()
            
            df_transformed = df[available_cols].copy()
            df_transformed = df_transformed.rename(columns=fund_mapping)
            
            # Convert data types
            if 'date' in df_transformed.columns:
                df_transformed['date'] = pd.to_datetime(df_transformed['date'], errors='coerce')
            
            numeric_cols = ['quota_value', 'net_assets', 'daily_inflow', 'daily_outflow']
            for col in numeric_cols:
                if col in df_transformed.columns:
                    df_transformed[col] = pd.to_numeric(df_transformed[col], errors='coerce')
            
            return df_transformed.dropna(subset=['fund_cnpj'] if 'fund_cnpj' in df_transformed.columns else [])
            
        except Exception as e:
            logger.error(f"Error transforming fund data: {e}")
            return pd.DataFrame()
    
    def transform_bond_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform bond data to time series format"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        try:
            # Map bond fields
            bond_rows = []
            for _, row in df.iterrows():
                if 'codigoTitulo' in row and 'dataReferencia' in row:
                    bond_code = row['codigoTitulo']
                    date = pd.to_datetime(row['dataReferencia'], errors='coerce')
                    
                    # Add yield as time series
                    if 'rentabilidade' in row and pd.notna(row['rentabilidade']):
                        bond_rows.append({
                            'series_id': f"BOND_{bond_code}_YIELD",
                            'date': date,
                            'value': pd.to_numeric(row['rentabilidade'], errors='coerce'),
                            'series_name': f"{bond_code} Yield"
                        })
                    
                    # Add price as time series
                    if 'preco' in row and pd.notna(row['preco']):
                        bond_rows.append({
                            'series_id': f"BOND_{bond_code}_PRICE",
                            'date': date,
                            'value': pd.to_numeric(row['preco'], errors='coerce'),
                            'series_name': f"{bond_code} Price"
                        })
            
            if bond_rows:
                return pd.DataFrame(bond_rows).dropna(subset=['date', 'value'])
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error transforming bond data: {e}")
            return pd.DataFrame()
    
    def transform_indices_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform indices data to time series format"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        try:
            index_rows = []
            for _, row in df.iterrows():
                if 'codigo' in row and 'dataReferencia' in row and 'valor' in row:
                    index_rows.append({
                        'series_id': f"INDEX_{row['codigo']}",
                        'date': pd.to_datetime(row['dataReferencia'], errors='coerce'),
                        'value': pd.to_numeric(row['valor'], errors='coerce'),
                        'series_name': row.get('nome', f"Index {row['codigo']}")
                    })
            
            if index_rows:
                return pd.DataFrame(index_rows).dropna(subset=['date', 'value'])
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error transforming indices data: {e}")
            return pd.DataFrame()
    
    async def load_to_database(self, df: pd.DataFrame, table: str):
        """Load data to appropriate table"""
        if df.empty:
            return
            
        conn = duckdb.connect(self.db_path)
        try:
            if table == "fund_daily":
                conn.execute("""
                    CREATE SCHEMA IF NOT EXISTS finance;
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
            elif table == "timeseries":
                conn.execute("""
                    CREATE SCHEMA IF NOT EXISTS finance;
                    CREATE TABLE IF NOT EXISTS finance.timeseries (
                        series_id VARCHAR,
                        date DATE,
                        value DOUBLE,
                        series_name TEXT,
                        PRIMARY KEY(series_id, date)
                    );
                """)
            
            conn.register(f'temp_anbima_data', df)
            
            if table == "fund_daily":
                conn.execute("""
                    INSERT INTO finance.fund_daily 
                    SELECT * FROM temp_anbima_data
                    ON CONFLICT (fund_cnpj, date) DO UPDATE SET
                        quota_value = EXCLUDED.quota_value,
                        net_assets = EXCLUDED.net_assets,
                        daily_inflow = EXCLUDED.daily_inflow,
                        daily_outflow = EXCLUDED.daily_outflow;
                """)
            else:
                conn.execute("""
                    INSERT INTO finance.timeseries 
                    SELECT * FROM temp_anbima_data
                    ON CONFLICT (series_id, date) DO UPDATE SET
                        value = EXCLUDED.value,
                        series_name = EXCLUDED.series_name;
                """)
            
            logger.info(f"Successfully loaded {len(df)} records to {table} table")
            
        except Exception as e:
            logger.error(f"Error loading data to {table}: {e}")
            raise
        finally:
            conn.close()
    
    async def update_market_data(self) -> Dict[str, int]:
        """Update all ANBIMA market data"""
        results = {"updated_datasets": 0, "total_records": 0, "errors": 0}
        
        if not self.client_id or not self.client_secret:
            logger.warning("ANBIMA credentials not configured - skipping update")
            return results
        
        try:
            # Fetch bond prices
            bond_df = await self.fetch_bond_prices()
            if bond_df is not None:
                transformed_bonds = self.transform_bond_data(bond_df)
                if not transformed_bonds.empty:
                    await self.load_to_database(transformed_bonds, "timeseries")
                    results["updated_datasets"] += 1
                    results["total_records"] += len(transformed_bonds)
            
            # Fetch indices
            indices_df = await self.fetch_indices()
            if indices_df is not None:
                transformed_indices = self.transform_indices_data(indices_df)
                if not transformed_indices.empty:
                    await self.load_to_database(transformed_indices, "timeseries")
                    results["updated_datasets"] += 1
                    results["total_records"] += len(transformed_indices)
                    
        except Exception as e:
            logger.error(f"Error updating ANBIMA data: {e}")
            results["errors"] += 1
        
        return results


async def run():
    """Main entry point for ANBIMA connector"""
    connector = ANBIMAConnector()
    results = await connector.update_market_data()
    logger.info(f"ANBIMA update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())