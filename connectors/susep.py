"""
SUSEP (Superintendência de Seguros Privados) Connector
Fetches insurance market data and statistics.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class SUSEPConnector:
    """Connector for SUSEP insurance data"""
    
    # SUSEP doesn't have a unified API, so we use known data sources
    DATA_SOURCES = {
        "market_stats": {
            "name": "Insurance Market Statistics",
            "url": "https://www2.susep.gov.br/menuestatistica/ses/principal.aspx",
            "type": "web_scraping"  # Would need to scrape or find CSV downloads
        },
        "open_insurance_sample": {
            "name": "Open Insurance Sample Data",
            "url": "https://api.sample-insurer.com.br/open-insurance/products",
            "type": "api"
        }
    }
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
    
    async def fetch_sample_csv_data(self) -> Optional[pd.DataFrame]:
        """Fetch sample insurance data (simulated)"""
        # In a real implementation, this would download actual CSV files from SUSEP
        # For demonstration, we create sample data structure
        
        try:
            logger.info("Creating sample insurance market data")
            
            # Sample data that might come from SUSEP CSV files
            sample_data = {
                'year': [2022, 2022, 2022, 2023, 2023, 2023],
                'quarter': [1, 2, 3, 1, 2, 3],
                'line_of_business': ['Auto', 'Auto', 'Auto', 'Auto', 'Auto', 'Auto'],
                'direct_premium': [15000000, 16000000, 17000000, 17500000, 18000000, 18500000],
                'claims': [12000000, 12800000, 13600000, 14000000, 14400000, 14800000],
                'loss_ratio': [0.8, 0.8, 0.8, 0.8, 0.8, 0.8]
            }
            
            df = pd.DataFrame(sample_data)
            logger.info(f"Generated {len(df)} sample insurance records")
            return df
            
        except Exception as e:
            logger.error(f"Error generating sample data: {e}")
            return None
    
    async def fetch_open_insurance_products(self, insurer_url: str) -> Optional[pd.DataFrame]:
        """Fetch product data from Open Insurance API"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching Open Insurance products from {insurer_url}")
                
                # In practice, this would call actual insurer APIs
                # For now, we simulate the structure
                sample_products = [
                    {
                        "insurer_id": "12345678",
                        "product_type": "Auto Insurance",
                        "product_name": "Basic Auto Protection",
                        "min_premium": 800.00,
                        "max_premium": 2500.00,
                        "coverage": "Third party liability, theft protection",
                        "data_fetch_date": datetime.now().isoformat()
                    },
                    {
                        "insurer_id": "12345678", 
                        "product_type": "Home Insurance",
                        "product_name": "Home Protection Plus",
                        "min_premium": 300.00,
                        "max_premium": 1200.00,
                        "coverage": "Fire, theft, electrical damage",
                        "data_fetch_date": datetime.now().isoformat()
                    }
                ]
                
                df = pd.DataFrame(sample_products)
                logger.info(f"Generated {len(df)} sample product records")
                return df
                
        except Exception as e:
            logger.error(f"Error fetching Open Insurance products: {e}")
            return None
    
    def transform_market_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform insurance market statistics"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        try:
            # Create date from year and quarter
            df['date'] = pd.to_datetime(
                df['year'].astype(str) + '-' + 
                ((df['quarter'] - 1) * 3 + 1).astype(str).str.zfill(2) + '-01'
            )
            
            # Convert to time series format for key metrics
            series_rows = []
            
            for _, row in df.iterrows():
                line = row['line_of_business']
                date = row['date']
                
                # Premium series
                if 'direct_premium' in row and pd.notna(row['direct_premium']):
                    series_rows.append({
                        'series_id': f"INS_{line.upper()}_PREMIUM",
                        'date': date,
                        'value': float(row['direct_premium']),
                        'series_name': f"{line} Direct Premium"
                    })
                
                # Claims series
                if 'claims' in row and pd.notna(row['claims']):
                    series_rows.append({
                        'series_id': f"INS_{line.upper()}_CLAIMS",
                        'date': date,
                        'value': float(row['claims']),
                        'series_name': f"{line} Claims"
                    })
                
                # Loss ratio series
                if 'loss_ratio' in row and pd.notna(row['loss_ratio']):
                    series_rows.append({
                        'series_id': f"INS_{line.upper()}_LOSS_RATIO",
                        'date': date,
                        'value': float(row['loss_ratio']),
                        'series_name': f"{line} Loss Ratio"
                    })
            
            if series_rows:
                return pd.DataFrame(series_rows)
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Error transforming market data: {e}")
            return pd.DataFrame()
    
    def transform_product_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform Open Insurance product data"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        try:
            # Convert data types
            df['data_fetch_date'] = pd.to_datetime(df['data_fetch_date'])
            df['min_premium'] = pd.to_numeric(df['min_premium'], errors='coerce')
            df['max_premium'] = pd.to_numeric(df['max_premium'], errors='coerce')
            
            # Create JSON details column
            df['json_details'] = df.apply(lambda row: {
                'product_name': row['product_name'],
                'min_premium': row['min_premium'],
                'max_premium': row['max_premium'],
                'coverage': row['coverage']
            }, axis=1).astype(str)
            
            # Select final columns for bank_products table
            df_transformed = df[['insurer_id', 'product_type', 'data_fetch_date', 'json_details']].copy()
            df_transformed = df_transformed.rename(columns={'insurer_id': 'bank_id'})
            
            return df_transformed
            
        except Exception as e:
            logger.error(f"Error transforming product data: {e}")
            return pd.DataFrame()
    
    async def load_to_database(self, df: pd.DataFrame, table: str):
        """Load data to appropriate table"""
        if df.empty:
            return
            
        conn = duckdb.connect(self.db_path)
        try:
            if table == "timeseries":
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
                
                conn.register('temp_susep_data', df)
                conn.execute("""
                    INSERT INTO finance.timeseries 
                    SELECT * FROM temp_susep_data
                    ON CONFLICT (series_id, date) DO UPDATE SET
                        value = EXCLUDED.value,
                        series_name = EXCLUDED.series_name;
                """)
                
            elif table == "bank_products":
                conn.execute("""
                    CREATE SCHEMA IF NOT EXISTS finance;
                    CREATE TABLE IF NOT EXISTS finance.bank_products (
                        bank_id VARCHAR,
                        product_type TEXT,
                        data_fetch_date DATE,
                        json_details JSON
                    );
                """)
                
                conn.register('temp_susep_products', df)
                conn.execute("""
                    INSERT INTO finance.bank_products 
                    SELECT * FROM temp_susep_products;
                """)
            
            logger.info(f"Successfully loaded {len(df)} records to {table} table")
            
        except Exception as e:
            logger.error(f"Error loading data to {table}: {e}")
            raise
        finally:
            conn.close()
    
    async def update_insurance_data(self) -> Dict[str, int]:
        """Update insurance market data and products"""
        results = {"updated_datasets": 0, "total_records": 0, "errors": 0}
        
        try:
            # Fetch market statistics (sample data for now)
            market_df = await self.fetch_sample_csv_data()
            if market_df is not None:
                transformed_market = self.transform_market_data(market_df)
                if not transformed_market.empty:
                    await self.load_to_database(transformed_market, "timeseries")
                    results["updated_datasets"] += 1
                    results["total_records"] += len(transformed_market)
            
            # Fetch Open Insurance product data (sample)
            products_df = await self.fetch_open_insurance_products("https://api.sample-insurer.com.br")
            if products_df is not None:
                transformed_products = self.transform_product_data(products_df)
                if not transformed_products.empty:
                    await self.load_to_database(transformed_products, "bank_products")
                    results["updated_datasets"] += 1
                    results["total_records"] += len(transformed_products)
                    
        except Exception as e:
            logger.error(f"Error updating SUSEP data: {e}")
            results["errors"] += 1
        
        return results


async def run():
    """Main entry point for SUSEP connector"""
    connector = SUSEPConnector()
    results = await connector.update_insurance_data()
    logger.info(f"SUSEP update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())