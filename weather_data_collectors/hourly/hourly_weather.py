import json
import boto3
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HourlyWeatherCollector:
    """Collects current weather data from Open-Meteo API"""
    
    def __init__(self, s3_bucket: str):
        self.s3_client = boto3.client('s3')
        self.s3_bucket = s3_bucket
        self.api_base_url = "https://api.open-meteo.com/v1/forecast"
        
        # Nelspruit coordinates
        self.latitude = -25.4753
        self.longitude = 30.9698
        self.location_name = "Nelspruit, Mpumalanga, South Africa"
        
        # API parameters
        self.hourly_params = [
            "temperature_2m",
            "relative_humidity_2m",
            "dew_point_2m",
            "apparent_temperature",
            "precipitation",
            "rain",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "surface_pressure",
            "cloud_cover",
            "visibility"
        ]
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def fetch_current_weather(self) -> Dict:
        """Fetch current weather data with retry mechanism"""
        try:
            params = {
                'latitude': self.latitude,
                'longitude': self.longitude,
                'hourly': self.hourly_params,
                'timezone': 'Africa/Johannesburg',
                'forecast_days': 1
            }
            
            response = requests.get(self.api_base_url, params=params, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise
    
    def process_current_weather(self, raw_data: Dict) -> Optional[Dict]:
        """Process current hour's weather data"""
        try:
            if not raw_data or 'hourly' not in raw_data:
                return None
            
            hourly = raw_data['hourly']
            current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
            
            # Find index for current hour
            try:
                current_index = hourly['time'].index(current_hour.isoformat())
            except ValueError:
                logger.error("Current hour not found in API response")
                return None
            
            # Create weather data point
            weather_data = {
                'timestamp': current_hour.isoformat(),
                'date': current_hour.strftime('%Y-%m-%d'),
                'hour': current_hour.hour,
                'location': {
                    'name': self.location_name,
                    'latitude': self.latitude,
                    'longitude': self.longitude
                },
                'weather': {},
                'metadata': {
                    'data_source': 'open_meteo_current',
                    'api_version': 'v1',
                    'collected_at': datetime.utcnow().isoformat()
                }
            }
            
            # Add all weather parameters
            for param in self.hourly_params:
                if param in hourly:
                    weather_data['weather'][param] = hourly[param][current_index]
            
            return weather_data
            
        except Exception as e:
            logger.error(f"Failed to process current weather: {str(e)}")
            return None
    
    def save_to_s3(self, data: Dict) -> bool:
        """Save current weather data to S3"""
        try:
            if not data:
                logger.warning("No data to save")
                return False
            
            # Extract timestamp components
            timestamp = datetime.fromisoformat(data['timestamp'])
            year = timestamp.year
            month = timestamp.month
            day = timestamp.day
            hour = timestamp.hour
            
            # Create S3 key with time-based partitioning
            s3_key = f"current/year={year}/month={month:02d}/day={day:02d}/hour={hour:02d}/weather_data.json"
            
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
    
    def collect_current_weather(self) -> Dict:
        """Main function to collect current weather data"""
        results = {
            'timestamp': datetime.utcnow().isoformat(),
            'success': False,
            'data_collected': False,
            'error': None
        }
        
        try:
            # Fetch current weather
            raw_data = self.fetch_current_weather()
            
            # Process data
            processed_data = self.process_current_weather(raw_data)
            
            if processed_data:
                # Save to S3
                save_success = self.save_to_s3(processed_data)
                
                results.update({
                    'success': save_success,
                    'data_collected': True,
                    'weather_timestamp': processed_data['timestamp']
                })
            
            return results
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Weather collection failed: {error_msg}")
            results.update({
                'error': error_msg
            })
            return results


def lambda_handler(event, context):
    """AWS Lambda handler for current weather data collection"""
    try:
        # Get S3 bucket from environment
        s3_bucket = os.environ.get('WEATHER_BUCKET')
        if not s3_bucket:
            raise ValueError("WEATHER_BUCKET environment variable is required")
        
        # Create collector and run
        collector = HourlyWeatherCollector(s3_bucket)
        results = collector.collect_current_weather()
        
        return {
            'statusCode': 200 if results['success'] else 500,
            'body': json.dumps({
                'message': 'Current weather data collection completed',
                'results': results
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'Current weather data collection failed',
                'error': str(e)
            })
        } 