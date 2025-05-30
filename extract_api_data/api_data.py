import logging
import boto3
import os
import datetime
import json
from faker import Faker
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def generate_movie_data(n: int, fake: Faker) -> list:
    """Generate fake movie data"""
    
    studios = [
        'Warner Bros.',
        'Universal Pictures',
        'Paramount Pictures',
        'Walt Disney Pictures',
        'Sony Pictures',
        '20th Century Studios',
        'Lionsgate Films',
        'Metro-Goldwyn-Mayer',
        'New Line Cinema',
        'DreamWorks Pictures',
        'A24',
        'Focus Features',
        'Miramax Films',
        'Amblin Entertainment',
        'Blumhouse Productions',
    ]
    
    genres = [
        'Action',
        'Adventure',
        'Comedy',
        'Drama',
        'Horror',
        'Thriller',
        'Sci-Fi',
        'Fantasy',
        'Romance',
        'Animation',
        'Documentary',
        'Crime',
        'Mystery',
        'Family',
        'Musical',
    ]
    
    movies = []
    for _ in range(n):
        movie = {
            "id": fake.uuid4(),
            "title": fake.catch_phrase(),
            "studio": random.choice(studios),
            "rating": fake.random_element(elements=('G', 'PG', 'PG-13', 'R', 'NC-17')),
            "genre": random.choice(genres),
            "runtime": random.randint(80, 210),
            "release_date": fake.date_between(start_date='-10y', end_date='today').isoformat(),
            "budget": float(random.randint(1000000, 250000000)),
            "box_office": float(random.randint(500000, 500000000)),
            "director": fake.name(),
            "popularity": round(random.uniform(1, 10), 1),
            "vote_average": round(random.uniform(1, 10), 1),
            "vote_count": random.randint(10, 50000),
            "overview": fake.paragraph(nb_sentences=5),
            "adult": random.choice([True, False]),
            "original_language": fake.language_code(),
        }
        movies.append(movie)
    
    return movies


def upload_to_s3(bucket_name: str, key: str, data: list) -> bool:
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
        bucket_name = os.environ.get('BUCKET_NAME', 'oakvale-raw-data')
        num_movies = int(os.environ.get('NUM_MOVIES', '100'))
        
        fake = Faker()
        
        # Generate movie data
        logger.info(f'Generating {num_movies} fake movie records...')
        movies = generate_movie_data(num_movies, fake)
        
        if not movies:
            logger.error('No movie data generated')
            return {
                'statusCode': 500,
                'body': json.dumps('No movie data generated')
            }
        
        # Generate S3 key with current date and hour
        today = datetime.datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        datetime_str = today.strftime("%Y-%m-%d_%H")
        key = f"Movies/{date_str}/movies_{datetime_str}.json"
        
        # Upload to S3
        logger.info(f'Uploading {len(movies)} records to S3...')
        upload_success = upload_to_s3(bucket_name, key, movies)
        
        if upload_success:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Data generation and upload completed successfully',
                    'records_processed': len(movies),
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