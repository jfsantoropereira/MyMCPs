"""
IBGE (Instituto Brasileiro de Geografia e Estatística) SIDRA Connector
Fetches statistical data from IBGE's SIDRA API.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class IBGEConnector:
    """Connector for IBGE SIDRA statistical data"""
    
    BASE_URL = "https://servicodados.ibge.gov.br/api/v3/agregados"
    
    # Key indicators
    INDICATORS = {
        "1736": {"name": "IPCA", "variable": "63"},  # IPCA inflation
        "1846": {"name": "PIB", "variable": "585"},  # GDP
        "4099": {"name": "UNEMPLOYMENT", "variable": "1619"},  # Unemployment rate
        "1737": {"name": "INPC", "variable": "44"},  # INPC inflation index
        "5932": {"name": "INDUSTRIAL_PRODUCTION", "variable": "544"},  # Industrial production
        "3653": {"name": "RETAIL_SALES", "variable": "1455"}  # Retail sales
    }
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
        
    async def fetch_indicator_data(self, indicator_id: str, variable_id: str, 
                                  periods: str = "all") -> Optional[pd.DataFrame]:
        """Fetch data for a specific indicator"""
        url = (f"{self.BASE_URL}/{indicator_id}/periodos/{periods}/"
               f"variaveis/{variable_id}")
        
        # Default to Brazil (N1[all]) for national data
        params = {
            "localidades": "N1[all]",
            "formato": "json"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching IBGE indicator {indicator_id} from {url}")
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                if not data:
                    logger.warning(f"No data returned for indicator {indicator_id}")
                    return None
                
                # Parse the nested JSON structure
                rows = []
                for item in data:
                    for result in item.get("resultados", []):
                        for serie in result.get("series", []):
                            localidade = serie.get("localidade", {})
                            for period, value in serie.get("serie", {}).items():
                                if value != "..." and value is not None:  # Skip missing values
                                    rows.append({
                                        "indicator_id": int(indicator_id),
                                        "region_code": localidade.get("id", "BR"),
                                        "region_name": localidade.get("nome", "Brasil"),
                                        "period": period,
                                        "value": value,
                                        "unit": result.get("unidade", "")
                                    })
                
                if rows:
                    df = pd.DataFrame(rows)
                    logger.info(f"Fetched {len(df)} records for indicator {indicator_id}")
                    return df
                else:
                    logger.warning(f"No valid data found for indicator {indicator_id}")
                    return None
                
        except Exception as e:
            logger.error(f"Error fetching IBGE indicator {indicator_id}: {e}")
            return None
    
    def transform_data(self, df: pd.DataFrame, indicator_name: str) -> pd.DataFrame:
        """Transform IBGE data to match our schema"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        # Parse period - could be YYYYMM, YYYY, YYYYQQ format
        def parse_period(period_str):
            period_str = str(period_str)
            if len(period_str) == 6:  # YYYYMM
                return f"{period_str[:4]}-{period_str[4:]}-01"
            elif len(period_str) == 4:  # YYYY
                return f"{period_str}-01-01"
            elif len(period_str) == 6 and period_str[4:6].isdigit():  # YYYYQQ
                quarter = int(period_str[4:])
                month = (quarter - 1) * 3 + 1
                return f"{period_str[:4]}-{month:02d}-01"
            else:
                return period_str
        
        df['date'] = pd.to_datetime(df['period'].apply(parse_period), errors='coerce')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        
        # Add indicator name
        df['indicator_name'] = indicator_name
        
        # Select final columns
        df_transformed = df[['indicator_id', 'region_code', 'date', 'value', 'unit', 'indicator_name']].copy()
        
        return df_transformed.dropna(subset=['indicator_id', 'date', 'value'])
    
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
            
            # Insert data with UPSERT
            conn.register('temp_ibge_data', df)
            conn.execute("""
                INSERT INTO finance.ibge_indicator 
                SELECT * FROM temp_ibge_data
                ON CONFLICT (indicator_id, region_code, date) DO UPDATE SET
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    indicator_name = EXCLUDED.indicator_name;
            """)
            
            logger.info(f"Successfully loaded {len(df)} records to ibge_indicator table")
            
        except Exception as e:
            logger.error(f"Error loading data to database: {e}")
            raise
        finally:
            conn.close()
    
    async def update_indicators(self) -> Dict[str, int]:
        """Update all configured indicators"""
        results = {"updated_indicators": 0, "total_records": 0, "errors": 0}
        
        for indicator_id, config in self.INDICATORS.items():
            try:
                # Fetch recent data (last 5 years for most indicators)
                periods = "last5"  # Last 5 periods, or use specific range
                df = await self.fetch_indicator_data(
                    indicator_id, 
                    config["variable"], 
                    periods
                )
                
                if df is not None:
                    transformed_df = self.transform_data(df, config["name"])
                    if not transformed_df.empty:
                        await self.load_to_database(transformed_df)
                        results["updated_indicators"] += 1
                        results["total_records"] += len(transformed_df)
                        
            except Exception as e:
                logger.error(f"Error updating indicator {indicator_id}: {e}")
                results["errors"] += 1
        
        return results


async def run():
    """Main entry point for IBGE connector"""
    connector = IBGEConnector()
    results = await connector.update_indicators()
    logger.info(f"IBGE update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())