"""
Tests for data connectors
"""

import pytest
import pandas as pd
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from connectors.cvm import CVMConnector
from connectors.bcb import BCBConnector
from connectors.ibge import IBGEConnector


class TestCVMConnector:
    """Test CVM connector functionality"""
    
    @pytest.fixture
    def connector(self):
        return CVMConnector(db_path=":memory:")
    
    def test_transform_data(self, connector):
        """Test CVM data transformation"""
        sample_data = pd.DataFrame({
            'CNPJ_FUNDO': ['12.345.678/0001-00', '98.765.432/0001-00'],
            'DT_COMPTC': ['2023-12-01', '2023-12-01'],
            'VL_QUOTA': [1.234567, 2.345678],
            'VL_PATRIM_LIQ': [1000000.50, 2000000.75],
            'VL_TOTAL': [1100000.50, 2100000.75],
            'CAPTC_DIA': [50000.00, 75000.00],
            'RESG_DIA': [25000.00, 35000.00],
            'NR_COTST': [150, 200]
        })
        
        result = connector.transform_data(sample_data)
        
        assert len(result) == 2
        assert 'fund_cnpj' in result.columns
        assert 'date' in result.columns
        assert 'quota_value' in result.columns
        assert pd.api.types.is_datetime64_any_dtype(result['date'])
        assert pd.api.types.is_numeric_dtype(result['quota_value'])


class TestBCBConnector:
    """Test BCB connector functionality"""
    
    @pytest.fixture
    def connector(self):
        return BCBConnector(db_path=":memory:")
    
    def test_transform_data(self, connector):
        """Test BCB data transformation"""
        sample_data = pd.DataFrame({
            'data': ['01/12/2023', '02/12/2023'],
            'valor': ['10.50', '10.75'],
            'series_id': ['433', '433'],
            'series_name': ['IPCA', 'IPCA']
        })
        
        result = connector.transform_data(sample_data)
        
        assert len(result) == 2
        assert 'date' in result.columns
        assert 'value' in result.columns
        assert 'series_id' in result.columns
        assert pd.api.types.is_datetime64_any_dtype(result['date'])
        assert pd.api.types.is_numeric_dtype(result['value'])


class TestIBGEConnector:
    """Test IBGE connector functionality"""
    
    @pytest.fixture
    def connector(self):
        return IBGEConnector(db_path=":memory:")
    
    def test_transform_data(self, connector):
        """Test IBGE data transformation"""
        sample_data = pd.DataFrame({
            'indicator_id': [1736, 1736],
            'region_code': ['BR', 'BR'], 
            'period': ['202312', '202311'],
            'value': [10.5, 10.2],
            'unit': ['%', '%']
        })
        
        result = connector.transform_data(sample_data, 'IPCA')
        
        assert len(result) == 2
        assert 'date' in result.columns
        assert 'value' in result.columns
        assert 'indicator_name' in result.columns
        assert result['indicator_name'].iloc[0] == 'IPCA'
        assert pd.api.types.is_datetime64_any_dtype(result['date'])


@pytest.mark.asyncio
class TestConnectorIntegration:
    """Integration tests for connectors"""
    
    @patch('httpx.AsyncClient.get')
    async def test_bcb_fetch_series_data(self, mock_get):
        """Test BCB API call with mocked response"""
        
        # Mock response data
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"data": "01/12/2023", "valor": "10.50"},
            {"data": "02/12/2023", "valor": "10.75"}
        ]
        mock_get.return_value = mock_response
        
        connector = BCBConnector(db_path=":memory:")
        result = await connector.fetch_series_data("433")
        
        assert result is not None
        assert len(result) == 2
        assert 'data' in result.columns
        assert 'valor' in result.columns
        assert 'series_id' in result.columns
    
    @patch('httpx.AsyncClient.get')
    async def test_cvm_fetch_with_http_error(self, mock_get):
        """Test CVM connector handles HTTP errors gracefully"""
        
        # Mock HTTP error
        mock_get.side_effect = Exception("HTTP 404")
        
        connector = CVMConnector(db_path=":memory:")
        result = await connector.fetch_monthly_data(2023, 12)
        
        assert result is None