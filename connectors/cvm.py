"""
CVM (Comissão de Valores Mobiliários) Connector
Fetches daily fund reports from CVM's open data portal.
"""

import asyncio
import io
import zipfile
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class CVMConnector:
    """Connector for CVM fund daily reports"""
    
    BASE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS"
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
        
    async def fetch_monthly_data(self, year: int, month: int) -> Optional[pd.DataFrame]:
        """Fetch CVM fund data for a specific month"""
        date_str = f"{year:04d}{month:02d}"
        url = f"{self.BASE_URL}/inf_diario_fi_{date_str}.zip"
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                logger.info(f"Fetching CVM data from {url}")
                response = await client.get(url)
                response.raise_for_status()
                
                # Extract CSV from ZIP
                with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
                    csv_filename = f"inf_diario_fi_{date_str}.csv"
                    if csv_filename not in zip_file.namelist():
                        logger.warning(f"CSV file {csv_filename} not found in ZIP")
                        return None
                    
                    with zip_file.open(csv_filename) as csv_file:
                        df = pd.read_csv(csv_file, encoding='latin-1', sep=';')
                        logger.info(f"Loaded {len(df)} records from {csv_filename}")
                        return df
                        
        except Exception as e:
            logger.error(f"Error fetching CVM data for {date_str}: {e}")
            return None
    
    def transform_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform CVM data to match our schema"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        # Rename columns to match our schema
        column_mapping = {
            'CNPJ_FUNDO': 'fund_cnpj',
            'DT_COMPTC': 'date',
            'VL_QUOTA': 'quota_value',
            'VL_PATRIM_LIQ': 'net_assets',
            'VL_TOTAL': 'total_assets',
            'CAPTC_DIA': 'daily_inflow',
            'RESG_DIA': 'daily_outflow',
            'NR_COTST': 'investors'
        }
        
        # Select and rename columns
        df_transformed = df[list(column_mapping.keys())].copy()
        df_transformed = df_transformed.rename(columns=column_mapping)
        
        # Clean and convert data types
        df_transformed['date'] = pd.to_datetime(df_transformed['date'], format='%Y-%m-%d')
        
        # Convert numeric columns, handling Brazilian decimal format
        numeric_columns = ['quota_value', 'net_assets', 'total_assets', 'daily_inflow', 'daily_outflow']
        for col in numeric_columns:
            if col in df_transformed.columns:
                df_transformed[col] = pd.to_numeric(df_transformed[col], errors='coerce')
        
        # Convert investors to integer
        df_transformed['investors'] = pd.to_numeric(df_transformed['investors'], errors='coerce').astype('Int64')
        
        return df_transformed.dropna(subset=['fund_cnpj', 'date'])
    
    async def load_to_database(self, df: pd.DataFrame):
        """Load transformed data to DuckDB"""
        if df.empty:
            logger.warning("No data to load")
            return
            
        conn = duckdb.connect(self.db_path)
        try:
            # Create schema and table if not exists
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
            
            # Insert data with UPSERT (ON CONFLICT DO UPDATE)
            conn.register('temp_cvm_data', df)
            conn.execute("""
                INSERT INTO finance.fund_daily 
                SELECT * FROM temp_cvm_data
                ON CONFLICT (fund_cnpj, date) DO UPDATE SET
                    quota_value = EXCLUDED.quota_value,
                    net_assets = EXCLUDED.net_assets,
                    total_assets = EXCLUDED.total_assets,
                    daily_inflow = EXCLUDED.daily_inflow,
                    daily_outflow = EXCLUDED.daily_outflow,
                    investors = EXCLUDED.investors;
            """)
            
            logger.info(f"Successfully loaded {len(df)} records to fund_daily table")
            
        except Exception as e:
            logger.error(f"Error loading data to database: {e}")
            raise
        finally:
            conn.close()
    
    async def update_funds(self) -> Dict[str, int]:
        """Update fund data for current and previous month"""
        results = {"current_month": 0, "previous_month": 0, "errors": 0}
        
        now = datetime.now()
        
        # Fetch current month
        try:
            current_df = await self.fetch_monthly_data(now.year, now.month)
            if current_df is not None:
                transformed_df = self.transform_data(current_df)
                await self.load_to_database(transformed_df)
                results["current_month"] = len(transformed_df)
        except Exception as e:
            logger.error(f"Error processing current month: {e}")
            results["errors"] += 1
        
        # Fetch previous month
        prev_month = now.replace(day=1) - timedelta(days=1)
        try:
            prev_df = await self.fetch_monthly_data(prev_month.year, prev_month.month)
            if prev_df is not None:
                transformed_df = self.transform_data(prev_df)
                await self.load_to_database(transformed_df)
                results["previous_month"] = len(transformed_df)
        except Exception as e:
            logger.error(f"Error processing previous month: {e}")
            results["errors"] += 1
            
        return results


async def run():
    """Main entry point for CVM connector"""
    connector = CVMConnector()
    results = await connector.update_funds()
    logger.info(f"CVM update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())