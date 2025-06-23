import json
import boto3
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
import os
from dateutil import parser
import pytz

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
        
        # Set timezone
        self.timezone = pytz.timezone('Africa/Johannesburg')
        
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
                'hourly': ','.join(self.hourly_params),
                'timezone': 'Africa/Johannesburg',
                'forecast_days': 1,
                'past_days': 1  # Include past day to ensure we have current data
            }
            
            logger.info(f"Requesting weather data with params: {params}")
            response = requests.get(self.api_base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"API response received with {len(data.get('hourly', {}).get('time', []))} time points")
            
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            raise
    
    def process_current_weather(self, raw_data: Dict) -> Optional[Dict]:
        """Process current hour's weather data"""
        if not raw_data or 'hourly' not in raw_data:
            logger.error("No hourly data in API response")
            return None

        hourly = raw_data['hourly']
        
        if 'time' not in hourly or not hourly['time']:
            logger.error("No time data in hourly response")
            return None
            
        # Parse API times
        try:
            api_times = [parser.isoparse(t) for t in hourly['time']]
            logger.info(f"API times range: {api_times[0]} to {api_times[-1]}")
        except Exception as e:
            logger.error(f"Failed to parse API times: {e}")
            return None

        # Get current time in South Africa timezone
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        now_local = now_utc.astimezone(self.timezone)
        current_hour = now_local.replace(minute=0, second=0, microsecond=0)
        
        logger.info(f"Current local time: {now_local}")
        logger.info(f"Looking for data at: {current_hour}")

        # Find the closest available time (prefer current or most recent past hour)
        closest_time = None
        closest_index = None
        min_diff = None
        
        for i, api_time in enumerate(api_times):
            # Convert API time to local timezone for comparison
            api_time_local = api_time.astimezone(self.timezone)
            time_diff = abs((current_hour - api_time_local).total_seconds())
            
            # Prefer times that are at or before current time
            if api_time_local <= current_hour:
                if min_diff is None or time_diff < min_diff:
                    min_diff = time_diff
                    closest_time = api_time_local
                    closest_index = i
            # If no past times found, use future time as fallback
            elif closest_time is None:
                if min_diff is None or time_diff < min_diff:
                    min_diff = time_diff
                    closest_time = api_time_local
                    closest_index = i

        if closest_index is None:
            logger.error("No suitable time found in API response")
            return None

        logger.info(f"Using data from: {closest_time} (index {closest_index})")

        # Create weather data point
        weather_data = {
            'timestamp': closest_time.isoformat(),
            'date': closest_time.strftime('%Y-%m-%d'),
            'hour': closest_time.hour,
            'location': {
                'name': self.location_name,
                'latitude': self.latitude,
                'longitude': self.longitude
            },
            'weather': {},
            'metadata': {
                'data_source': 'open_meteo_current',
                'api_version': 'v1',
                'collected_at': datetime.utcnow().isoformat(),
                'local_timezone': 'Africa/Johannesburg'
            }
        }

        # Add all weather parameters
        for param in self.hourly_params:
            if param in hourly and len(hourly[param]) > closest_index:
                value = hourly[param][closest_index]
                weather_data['weather'][param] = value
                logger.debug(f"Added {param}: {value}")

        logger.info(f"Weather data processed successfully for {closest_time}")
        return weather_data
    
    def save_to_s3(self, data: Dict) -> bool:
        """Save current weather data to S3"""
        try:
            if not data:
                logger.warning("No data to save")
                return False
            
            # Extract timestamp components
            timestamp = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
            # Convert to local timezone for partitioning
            timestamp_local = timestamp.astimezone(self.timezone)
            
            year = timestamp_local.year
            month = timestamp_local.month
            day = timestamp_local.day
            hour = timestamp_local.hour
            
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
            logger.info("Starting weather data collection...")
            
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
                
                if save_success:
                    logger.info("Weather data collection completed successfully")
                else:
                    logger.error("Weather data collection failed during S3 save")
            else:
                logger.error("Failed to process weather data")
                results['error'] = "Failed to process weather data"
            
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
        
        logger.info(f"Starting weather collection for bucket: {s3_bucket}")
        
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