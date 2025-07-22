"""
Open Finance Connector
Fetches banking and financial product data from Open Finance APIs in Brazil.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

import httpx
import pandas as pd
import duckdb

logger = logging.getLogger(__name__)


class OpenFinanceConnector:
    """Connector for Open Finance banking data"""
    
    # Sample Open Banking/Finance endpoints
    PARTICIPANT_ENDPOINTS = {
        "banco_do_brasil": {
            "base_url": "https://openbanking.bb.com.br",
            "products_endpoint": "/open-banking/products/v1/personal-loans",
            "name": "Banco do Brasil"
        },
        "caixa": {
            "base_url": "https://openbanking.caixa.gov.br", 
            "products_endpoint": "/open-banking/products/v1/personal-accounts",
            "name": "Caixa Econômica Federal"
        },
        "santander": {
            "base_url": "https://openbanking.santander.com.br",
            "products_endpoint": "/open-banking/products/v1/credit-cards",
            "name": "Banco Santander"
        }
    }
    
    def __init__(self, db_path: str = "finance.duckdb"):
        self.db_path = db_path
    
    async def fetch_bank_products(self, bank_id: str, config: Dict) -> Optional[pd.DataFrame]:
        """Fetch product data from a bank's Open Finance API"""
        url = f"{config['base_url']}{config['products_endpoint']}"
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching Open Finance products from {config['name']}")
                
                # In practice, this would make real API calls
                # For demonstration, we create sample data based on Open Finance standards
                
                # Sample personal loan products
                if "personal-loans" in url:
                    sample_products = [
                        {
                            "type": "EMPRESTIMO_CONSIGNADO",
                            "fees": {
                                "interestRate": 1.2,
                                "monthlyFee": 0.0
                            },
                            "interestRates": [
                                {"referentialRateIndexer": "SEM_INDEXADOR", "rate": 0.012}
                            ],
                            "requiredWarranties": ["CONSIGNACAO_FOLHA_PAGAMENTO"],
                            "minimumRate": 0.008,
                            "maximumRate": 0.025
                        }
                    ]
                    
                # Sample account products
                elif "personal-accounts" in url:
                    sample_products = [
                        {
                            "type": "CONTA_CORRENTE",
                            "fees": {
                                "monthlyFee": 12.90,
                                "withdrawalFee": 3.50
                            },
                            "serviceBundle": {
                                "name": "Conta Completa",
                                "services": ["TRANSFERENCIAS_DOC", "TRANSFERENCIAS_TED"]
                            }
                        }
                    ]
                    
                # Sample credit card products  
                elif "credit-cards" in url:
                    sample_products = [
                        {
                            "type": "CARTAO_CREDITO",
                            "network": "VISA",
                            "fees": {
                                "annualFee": 89.90,
                                "withdrawalFee": 9.90
                            },
                            "interestRates": [
                                {"code": "ROTATIVO", "rate": 0.085}
                            ]
                        }
                    ]
                else:
                    sample_products = []
                
                if sample_products:
                    df = pd.DataFrame([{
                        'bank_id': bank_id,
                        'bank_name': config['name'],
                        'product_type': product.get('type', 'UNKNOWN'),
                        'data_fetch_date': datetime.now().isoformat(),
                        'raw_data': product
                    } for product in sample_products])
                    
                    logger.info(f"Generated {len(df)} sample products for {config['name']}")
                    return df
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"Error fetching products from {config['name']}: {e}")
            return None
    
    def transform_product_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transform Open Finance product data"""
        if df is None or df.empty:
            return pd.DataFrame()
            
        try:
            # Convert data types
            df['data_fetch_date'] = pd.to_datetime(df['data_fetch_date'])
            
            # Create structured JSON details from raw data
            def create_json_details(row):
                raw_data = row['raw_data']
                
                # Extract key information based on product type
                details = {
                    'bank_name': row['bank_name'],
                    'product_type': row['product_type']
                }
                
                if 'fees' in raw_data:
                    details['fees'] = raw_data['fees']
                    
                if 'interestRates' in raw_data:
                    details['interest_rates'] = raw_data['interestRates']
                    
                if 'minimumRate' in raw_data:
                    details['rate_range'] = {
                        'minimum': raw_data['minimumRate'],
                        'maximum': raw_data.get('maximumRate', raw_data['minimumRate'])
                    }
                
                return details
            
            df['json_details'] = df.apply(create_json_details, axis=1).astype(str)
            
            # Select final columns
            df_transformed = df[['bank_id', 'product_type', 'data_fetch_date', 'json_details']].copy()
            
            return df_transformed
            
        except Exception as e:
            logger.error(f"Error transforming Open Finance data: {e}")
            return pd.DataFrame()
    
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
                CREATE TABLE IF NOT EXISTS finance.bank_products (
                    bank_id VARCHAR,
                    product_type TEXT,
                    data_fetch_date DATE,
                    json_details JSON
                );
            """)
            
            # Clear existing data for today (to avoid duplicates)
            today = datetime.now().date()
            conn.execute(
                "DELETE FROM finance.bank_products WHERE data_fetch_date = ?",
                [today]
            )
            
            # Insert new data
            conn.register('temp_open_finance_data', df)
            conn.execute("""
                INSERT INTO finance.bank_products 
                SELECT * FROM temp_open_finance_data;
            """)
            
            logger.info(f"Successfully loaded {len(df)} records to bank_products table")
            
        except Exception as e:
            logger.error(f"Error loading data to database: {e}")
            raise
        finally:
            conn.close()
    
    async def update_open_finance_data(self) -> Dict[str, int]:
        """Update Open Finance product data from all participants"""
        results = {"updated_banks": 0, "total_products": 0, "errors": 0}
        
        all_products = []
        
        for bank_id, config in self.PARTICIPANT_ENDPOINTS.items():
            try:
                df = await self.fetch_bank_products(bank_id, config)
                if df is not None and not df.empty:
                    transformed_df = self.transform_product_data(df)
                    if not transformed_df.empty:
                        all_products.append(transformed_df)
                        results["updated_banks"] += 1
                        results["total_products"] += len(transformed_df)
                        
            except Exception as e:
                logger.error(f"Error updating Open Finance data for {bank_id}: {e}")
                results["errors"] += 1
        
        # Load all products in one batch
        if all_products:
            combined_df = pd.concat(all_products, ignore_index=True)
            await self.load_to_database(combined_df)
        
        return results


async def run():
    """Main entry point for Open Finance connector"""
    connector = OpenFinanceConnector()
    results = await connector.update_open_finance_data()
    logger.info(f"Open Finance update completed: {results}")
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())