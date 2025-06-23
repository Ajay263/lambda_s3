import json
import boto3
import requests
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from typing import Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HistoricalWeatherCollector:
    """Collects historical weather data from Open-Meteo API"""
    
    def __init__(self, s3_bucket: str):
        self.s3_client = boto3.client('s3')
        self.s3_bucket = s3_bucket
        self.api_base_url = "https://archive-api.open-meteo.com/v1/archive"
        
        # Nelspruit coordinates
        self.latitude = -25.4753
        self.longitude = 30.9698
        self.location_name = "Nelspruit, Mpumalanga, South Africa"
        
        # API parameters
        self.weather_params = [
            "temperature_2m_max",
            "temperature_2m_min",
            "temperature_2m_mean",
            "relative_humidity_2m_max",
            "relative_humidity_2m_min",
            "relative_humidity_2m_mean",
            "rain_sum",
            "snowfall_sum",
            "precipitation_hours",
            "wind_speed_10m_max",
            "wind_gusts_10m_max",
            "wind_direction_10m_dominant",
            "shortwave_radiation_sum",
            "et0_fao_evapotranspiration"
        ]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def fetch_historical_data(self, start_date: str, end_date: str) -> Dict:
        """Fetch historical weather data with retry mechanism"""
        try:
            params = {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'start_date': start_date,
                'end_date': end_date,
                'daily': self.weather_params,
                'timezone': 'Africa/Johannesburg'
            }
            
            response = requests.get(self.api_base_url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise
    
    def process_monthly_data(self, raw_data: Dict, year: int, month: int) -> List[Dict]:
        """Process raw API data into structured format"""
        if not raw_data or 'daily' not in raw_data:
            return []
        
        daily = raw_data['daily']
        processed_data = []
        
        for i, date in enumerate(daily.get('time', [])):
            # Create data point for each day
            data_point = {
                'date': date,
                'year': year,
                'month': month,
                'location': {
                    'name': self.location_name,
                    'latitude': self.latitude,
                    'longitude': self.longitude
                },
                'weather': {}
            }
            
            # Add all weather parameters
            for param in self.weather_params:
                if param in daily:
                    data_point['weather'][param] = daily[param][i]
            
            # Add metadata
            data_point['metadata'] = {
                'data_source': 'open_meteo_historical',
                'api_version': 'v1',
                'collected_at': datetime.utcnow().isoformat()
            }
            
            processed_data.append(data_point)
        
        return processed_data
    
    def save_to_s3(self, data: List[Dict], year: int, month: int) -> bool:
        """Save processed data to S3 with year/month partitioning"""
        try:
            if not data:
                logger.warning(f"No data to save for {year}-{month:02d}")
                return False
            
            # Create S3 key with year/month partitioning
            s3_key = f"historical/year={year}/month={month:02d}/weather_data.json"
            
            # Convert to JSON with proper formatting
            json_data = json.dumps(data, indent=2)
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=s3_key,
                Body=json_data,
                ContentType='application/json'
            )
            
            logger.info(f"Successfully saved data to s3://{self.s3_bucket}/{s3_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save data to S3: {str(e)}")
            return False
    
    def collect_monthly_data(self, year: int, month: int) -> bool:
        """Collect and save data for a specific month"""
        try:
            # Calculate date range for the month
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            
            # Don't fetch future data
            current_date = datetime.now()
            if start_date > current_date:
                logger.info(f"Skipping future month: {year}-{month:02d}")
                return True
            if end_date > current_date:
                end_date = current_date
            
            logger.info(f"Collecting data for {year}-{month:02d}")
            
            # Fetch data from API
            raw_data = self.fetch_historical_data(
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )
            
            # Process and save data
            processed_data = self.process_monthly_data(raw_data, year, month)
            success = self.save_to_s3(processed_data, year, month)
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to collect data for {year}-{month:02d}: {str(e)}")
            return False
    
    def collect_historical_data(self, years_back: int = 3) -> Dict:
        """Collect historical data for specified number of years"""
        results = {
            'success_months': [],
            'failed_months': [],
            'total_months_processed': 0
        }
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - relativedelta(years=years_back)
        
        current_date = start_date
        while current_date <= end_date:
            year = current_date.year
            month = current_date.month
            
            success = self.collect_monthly_data(year, month)
            
            if success:
                results['success_months'].append(f"{year}-{month:02d}")
            else:
                results['failed_months'].append(f"{year}-{month:02d}")
            
            results['total_months_processed'] += 1
            current_date += relativedelta(months=1)
        
        return results


def lambda_handler(event, context):
    """AWS Lambda handler for historical weather data collection"""
    try:
        # Get S3 bucket from environment
        s3_bucket = os.environ.get('WEATHER_BUCKET')
        if not s3_bucket:
            raise ValueError("WEATHER_BUCKET environment variable is required")
        
        # Get parameters from event
        years_back = event.get('years_back', 3)
        
        # Create collector and run
        collector = HistoricalWeatherCollector(s3_bucket)
        results = collector.collect_historical_data(years_back)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Historical weather data collection completed',
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Historical weather data collection failed',
                'error': str(e)
            })
        } 