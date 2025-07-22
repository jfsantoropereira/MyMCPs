"""
Tesouro Nacional Connector
Fetches fiscal and debt data from Brazilian Treasury APIs.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class TesouroConnector:
    """Connector for Tesouro Nacional fiscal data"""
    
    BASE_URL = "https://api.tesourotransparente.gov.br"
    DATA_LAKE_URL = "https://apidatalake.tesouro.gov.br"
    
    # Key datasets
    DATASETS = {
        "debt_gross": {
            "name": "Public Debt Gross",
            "endpoint": "/ckan/api/3/action/datastore_search",
            "resource_id": "debt-resource-id",  # Would need actual resource ID
            "series_id": "DEBT_GROSS"
        },
        "debt_net": {
            "name": "Public Debt Net",
            "endpoint": "/ckan/api/3/action/datastore_search", 
            "resource_id": "debt-net-resource-id",
            "series_id": "DEBT_NET"
        }
    }
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
        
    async def fetch_ckan_data(self, resource_id: str, limit: int = 1000) -> Optional[pd.DataFrame]:
        """Fetch data from CKAN API"""
        url = f"{self.BASE_URL}/ckan/api/3/action/datastore_search"
        params = {
            "resource_id": resource_id,
            "limit": limit
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching Tesouro data from CKAN for resource {resource_id}")
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                if not data.get("success"):
                    logger.error(f"CKAN API returned error: {data}")
                    return None
                
                records = data.get("result", {}).get("records", [])
                if not records:
                    logger.warning(f"No records found for resource {resource_id}")
                    return None
                
                df = pd.DataFrame(records)
                logger.info(f"Fetched {len(df)} records for resource {resource_id}")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching Tesouro CKAN data for {resource_id}: {e}")
            return None
    
    async def fetch_debt_data_direct(self) -> Optional[pd.DataFrame]:
        """Fetch debt data directly from known endpoints"""
        # This is a simplified approach - real implementation would use actual API endpoints
        # For demonstration, we'll create sample data structure
        
        try:
            # Example: Fetch from a hypothetical debt API endpoint
            url = f"{self.DATA_LAKE_URL}/debt/monthly"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching debt data from {url}")
                # This would be the actual API call
                # response = await client.get(url)
                # response.raise_for_status()
                # data = response.json()
                
                # For now, return None to indicate we'd need actual endpoints
                logger.warning("Direct debt API endpoints not configured - would need actual URLs")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching debt data: {e}")
            return None
    
    def transform_debt_data(self, df: pd.DataFrame, series_id: str) -> pd.DataFrame:
        """Transform debt data to time series format"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        # This transformation would depend on the actual data structure
        # Common patterns for fiscal data:
        try:
            # Assume columns like: date, value, category, unit
            if 'data' in df.columns:
                df['date'] = pd.to_datetime(df['data'], errors='coerce')
            elif 'Data' in df.columns:
                df['date'] = pd.to_datetime(df['Data'], errors='coerce')
            else:
                # Try to find date column
                date_cols = [col for col in df.columns if 'data' in col.lower() or 'date' in col.lower()]
                if date_cols:
                    df['date'] = pd.to_datetime(df[date_cols[0]], errors='coerce')
                else:
                    logger.error("No date column found in debt data")
                    return pd.DataFrame()
            
            # Find value column
            value_cols = [col for col in df.columns if 'valor' in col.lower() or 'value' in col.lower()]
            if value_cols:
                df['value'] = pd.to_numeric(df[value_cols[0]], errors='coerce')
            else:
                logger.error("No value column found in debt data")
                return pd.DataFrame()
            
            # Create time series format
            df_transformed = pd.DataFrame({
                'series_id': series_id,
                'date': df['date'],
                'value': df['value'],
                'series_name': f"Tesouro {series_id}"
            })
            
            return df_transformed.dropna(subset=['date', 'value'])
            
        except Exception as e:
            logger.error(f"Error transforming debt data: {e}")
            return pd.DataFrame()
    
    async def load_to_database(self, df: pd.DataFrame):
        """Load transformed data to DuckDB"""
        if df.empty:
            logger.warning("No data to load")
            return
            
        conn = duckdb.connect(self.db_path)
        try:
            # Create table if not exists (reuse timeseries table)
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
            
            # Insert data with UPSERT
            conn.register('temp_tesouro_data', df)
            conn.execute("""
                INSERT INTO finance.timeseries 
                SELECT * FROM temp_tesouro_data
                ON CONFLICT (series_id, date) DO UPDATE SET
                    value = EXCLUDED.value,
                    series_name = EXCLUDED.series_name;
            """)
            
            logger.info(f"Successfully loaded {len(df)} records to timeseries table")
            
        except Exception as e:
            logger.error(f"Error loading data to database: {e}")
            raise
        finally:
            conn.close()
    
    async def update_fiscal_data(self) -> Dict[str, int]:
        """Update fiscal and debt data"""
        results = {"updated_series": 0, "total_records": 0, "errors": 0}
        
        # Try direct API approach first
        debt_df = await self.fetch_debt_data_direct()
        if debt_df is not None:
            transformed_df = self.transform_debt_data(debt_df, "DEBT_GROSS")
            if not transformed_df.empty:
                await self.load_to_database(transformed_df)
                results["updated_series"] += 1
                results["total_records"] += len(transformed_df)
        else:
            # Try CKAN approach for each configured dataset
            for dataset_key, config in self.DATASETS.items():
                try:
                    df = await self.fetch_ckan_data(config["resource_id"])
                    if df is not None:
                        transformed_df = self.transform_debt_data(df, config["series_id"])
                        if not transformed_df.empty:
                            await self.load_to_database(transformed_df)
                            results["updated_series"] += 1
                            results["total_records"] += len(transformed_df)
                            
                except Exception as e:
                    logger.error(f"Error updating dataset {dataset_key}: {e}")
                    results["errors"] += 1
        
        return results


async def run():
    """Main entry point for Tesouro connector"""
    connector = TesouroConnector()
    results = await connector.update_fiscal_data()
    logger.info(f"Tesouro update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())