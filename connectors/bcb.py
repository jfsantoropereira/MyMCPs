"""
BCB (Banco Central do Brasil) SGS Connector
Fetches economic time series from BCB's SGS (Sistema Gerenciador de Séries Temporais) API.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class BCBConnector:
    """Connector for BCB SGS time series data"""
    
    BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs"
    
    # Key economic series codes
    SERIES_CODES = {
        "433": "IPCA",  # IPCA inflation index
        "11": "SELIC",  # SELIC interest rate
        "1": "USD_BRL",  # USD/BRL exchange rate
        "12": "CDI",  # CDI rate
        "4390": "IGPM",  # IGP-M index
        "7": "TJLP",  # TJLP rate
        "189": "IGP_DI",  # IGP-DI index
        "1178": "UNEMPLOYMENT",  # Unemployment rate
        "4380": "GDP",  # GDP index
        "27574": "FOCUS_IPCA"  # Focus survey IPCA expectation
    }
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
        
    async def fetch_series_data(self, series_code: str, last_n: Optional[int] = None, 
                               start_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Fetch data for a specific series"""
        url = f"{self.BASE_URL}.{series_code}/dados"
        params = {"formato": "json"}
        
        if last_n:
            url += f"/ultimos/{last_n}"
        elif start_date:
            params["dataInicial"] = start_date
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching BCB series {series_code} from {url}")
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                if not data:
                    logger.warning(f"No data returned for series {series_code}")
                    return None
                
                df = pd.DataFrame(data)
                df['series_id'] = series_code
                df['series_name'] = self.SERIES_CODES.get(series_code, f"Series_{series_code}")
                
                logger.info(f"Fetched {len(df)} records for series {series_code}")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching BCB series {series_code}: {e}")
            return None
    
    def transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform BCB data to match our schema"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        # Convert date format from DD/MM/YYYY to YYYY-MM-DD
        df['date'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
        
        # Convert valor to numeric
        df['value'] = pd.to_numeric(df['valor'], errors='coerce')
        
        # Select and rename columns
        df_transformed = df[['series_id', 'date', 'value', 'series_name']].copy()
        
        return df_transformed.dropna(subset=['series_id', 'date', 'value'])
    
    async def load_to_database(self, df: pd.DataFrame):
        """Load transformed data to DuckDB"""
        if df.empty:
            logger.warning("No data to load")
            return
            
        conn = duckdb.connect(self.db_path)
        try:
            # Create table if not exists
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
            conn.register('temp_bcb_data', df)
            conn.execute("""
                INSERT INTO finance.timeseries 
                SELECT * FROM temp_bcb_data
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
    
    async def get_last_update_date(self, series_code: str) -> Optional[datetime]:
        """Get the last update date for a series"""
        conn = duckdb.connect(self.db_path)
        try:
            result = conn.execute(
                "SELECT MAX(date) FROM finance.timeseries WHERE series_id = ?",
                [series_code]
            ).fetchone()
            if result[0]:
                return pd.to_datetime(result[0]).to_pydatetime()
            return None
        except Exception:
            return None
        finally:
            conn.close()
    
    async def update_series(self, incremental: bool = True) -> Dict[str, int]:
        """Update all configured series"""
        results = {"updated_series": 0, "total_records": 0, "errors": 0}
        
        for series_code in self.SERIES_CODES.keys():
            try:
                if incremental:
                    # Get last update date and fetch only recent data
                    last_date = await self.get_last_update_date(series_code)
                    if last_date:
                        # Fetch last 30 values to catch any updates
                        df = await self.fetch_series_data(series_code, last_n=30)
                    else:
                        # Initial load - get last 2 years of data
                        start_date = (datetime.now() - timedelta(days=730)).strftime("%d/%m/%Y")
                        df = await self.fetch_series_data(series_code, start_date=start_date)
                else:
                    # Full refresh - get all available data
                    df = await self.fetch_series_data(series_code)
                
                if df is not None:
                    transformed_df = self.transform_data(df)
                    if not transformed_df.empty:
                        await self.load_to_database(transformed_df)
                        results["updated_series"] += 1
                        results["total_records"] += len(transformed_df)
                        
            except Exception as e:
                logger.error(f"Error updating series {series_code}: {e}")
                results["errors"] += 1
        
        return results


async def run():
    """Main entry point for BCB connector"""
    connector = BCBConnector()
    results = await connector.update_series()
    logger.info(f"BCB update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())