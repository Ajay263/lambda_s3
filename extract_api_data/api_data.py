import logging
import requests
import boto3
import os
import datetime
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def extract_api_data(url: str, headers: dict) -> dict:
    """Extract data from API endpoint"""
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad responses
        
        if response.status_code == 200:
            data = response.json().get('results', [])
            logger.info(f'Successfully extracted {len(data)} records from API')
            return data
        else:
            logger.error(f'API returned status code: {response.status_code}')
            return []
            
    except requests.exceptions.RequestException as e:
        logger.error(f'Error while extracting data from the API: {e}')
        return []
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
        return []

def upload_to_s3(bucket_name: str, key: str, data: dict) -> bool:
    """Upload data to S3 bucket"""
    try:
        data_string = json.dumps(data, indent=2, default=str)
        
        s3 = boto3.client('s3')
        s3.put_object(Bucket=bucket_name, Key=key, Body=data_string)
        
        logger.info(f'Successfully uploaded data to s3://{bucket_name}/{key}')
        return True
        
    except Exception as e:
        logger.error(f'Error uploading to S3: {e}')
        return False

def lambda_handler(event, context):
    """Main Lambda handler function"""
    try:
        # Get environment variables
        authorization = os.environ.get('Authorization')
        bucket_name = os.environ.get('BUCKET_NAME', 'movie-api-data-daily')
        
        if not authorization:
            logger.error('Authorization token not found in environment variables')
            return {
                'statusCode': 500,
                'body': json.dumps('Authorization token missing')
            }
        
        # API configuration
        url = (
            'https://api.themoviedb.org/3/discover/movie?include_adult='
            'false&include_video=false&language=en-US&page=1&sort_by=popularity.desc'
        )
        headers = {
            "accept": "application/json", 
            "Authorization": authorization
        }
        
        # Generate S3 key with current date
        today_date = datetime.date.today().strftime("%Y-%m-%d")
        key = f"api_data/{today_date}/movies.json"
        
        # Extract data from API
        logger.info('Starting API data extraction...')
        data = extract_api_data(url, headers)
        
        if not data:
            logger.error('No data extracted from API')
            return {
                'statusCode': 500,
                'body': json.dumps('No data extracted from API')
            }
        
        # Upload to S3
        logger.info(f'Uploading {len(data)} records to S3...')
        upload_success = upload_to_s3(bucket_name, key, data)
        
        if upload_success:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Data extraction and upload completed successfully',
                    'records_processed': len(data),
                    's3_location': f's3://{bucket_name}/{key}'
                })
            }
        else:
            return {
                'statusCode': 500,
                'body': json.dumps('Failed to upload data to S3')
            }
            
    except Exception as e:
        logger.error(f'Lambda execution failed: {e}')
        return {
            'statusCode': 500,
            'body': json.dumps(f'Lambda execution failed: {str(e)}')
        }