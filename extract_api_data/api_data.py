# Modern Data Lake Architecture with AWS Services
# This is the MOST EFFICIENT approach for production workloads

import json
import os
import boto3
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import requests
import awswrangler as wr  # AWS Data Wrangler for optimized S3/Athena operations


def get_config():
    """Load pipeline configuration from environment variables."""
    return {
        "adzuna_app_id": os.getenv("ADZUNA_APP_ID"),
        "adzuna_app_key": os.getenv("ADZUNA_APP_KEY"),
        "s3_bucket": os.getenv("S3_BUCKET"),
        "s3_processed_prefix": os.getenv("S3_PROCESSED_PREFIX", "processed-data/adzuna-jobs"),
        "dynamodb_state_table": os.getenv("DYNAMODB_STATE_TABLE", "adzuna-pipeline-state"),
        "glue_database": os.getenv("GLUE_DATABASE", "job_data_lake"),
        "glue_table": os.getenv("GLUE_TABLE", "adzuna_jobs"),
        "search_phrase": os.getenv("SEARCH_PHRASE", "data engineer"),
        "overlap_hours": int(os.getenv("OVERLAP_HOURS", "12")),
        "batch_size": int(os.getenv("BATCH_SIZE", "1000")),
    }


def get_state(dynamodb, table_name):
    """Get the last extraction state from DynamoDB."""
    try:
        table = dynamodb.Table(table_name)
        response = table.get_item(Key={"state_id": "adzuna_pipeline_state"}, ConsistentRead=True)
        return response.get("Item", {
            "state_id": "adzuna_pipeline_state",
            "last_extraction_time": (datetime.now() - timedelta(days=7)).isoformat(),
            "total_jobs_extracted": 0,
            "version": 0,
            "created_at": datetime.now().isoformat()
        })
    except Exception as e:
        print(f"Error reading state: {e}")
        return {
            "state_id": "adzuna_pipeline_state",
            "last_extraction_time": (datetime.now() - timedelta(days=7)).isoformat(),
            "total_jobs_extracted": 0,
            "version": 0,
            "created_at": datetime.now().isoformat()
        }


def update_state(dynamodb, table_name, updates):
    """Update the extraction state in DynamoDB atomically."""
    table = dynamodb.Table(table_name)
    current_state = get_state(dynamodb, table_name)
    current_version = current_state.get("version", 0)
    try:
        table.put_item(
            Item={
                "state_id": "adzuna_pipeline_state",
                "version": current_version + 1,
                "updated_at": datetime.now().isoformat(),
                **updates
            },
            ConditionExpression="attribute_not_exists(version) OR version = :current_version",
            ExpressionAttributeValues={":current_version": current_version}
        )
        return True
    except Exception as e:
        print(f"Error updating state: {e}")
        return False


def fetch_jobs_from_adzuna(config, extraction_window):
    """Generator that yields DataFrames of jobs from Adzuna API in batches."""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=10, pool_maxsize=20, max_retries=3)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    all_jobs = []
    page = 1
    while True:
        days_old = (datetime.now() - extraction_window['start_time']).days + 1
        params = {
            "app_id": config["adzuna_app_id"],
            "app_key": config["adzuna_app_key"],
            "results_per_page": 50,
            "what_phrase": config["search_phrase"],
            "max_days_old": min(days_old, 30),
            "sort_by": "date"
        }
        try:
            resp = session.get(
                f"https://api.adzuna.com/v1/api/jobs/ca/search/{page}",
                params=params,
                timeout=30
            )
            if resp.status_code != 200:
                print(f"API error on page {page}: {resp.status_code}")
                break
            jobs_batch = resp.json().get("results", [])
            if not jobs_batch:
                break
            all_jobs.extend(jobs_batch)
            if len(all_jobs) >= config["batch_size"]:
                yield parse_jobs_batch(all_jobs[:config["batch_size"]])
                all_jobs = all_jobs[config["batch_size"]:]
            page += 1
            if len(jobs_batch) < 50:
                break
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
    if all_jobs:
        yield parse_jobs_batch(all_jobs)


def parse_jobs_batch(raw_jobs):
    """Convert a list of raw job dicts to a DataFrame, cleaning and optimizing types."""
    if not raw_jobs:
        return pd.DataFrame()
    jobs_data = {
        "job_id": [job.get("id") for job in raw_jobs],
        "job_title": [job.get("title") for job in raw_jobs],
        "job_location": [job.get("location", {}).get("display_name") for job in raw_jobs],
        "job_company": [job.get("company", {}).get("display_name") for job in raw_jobs],
        "job_category": [job.get("category", {}).get("label") for job in raw_jobs],
        "job_description": [job.get("description") for job in raw_jobs],
        "job_url": [job.get("redirect_url") for job in raw_jobs],
        "job_created": [job.get("created") for job in raw_jobs]
    }
    df = pd.DataFrame(jobs_data)
    df["job_created"] = pd.to_datetime(df["job_created"])
    df = df.dropna(subset=["job_id", "job_title", "job_created"])
    # Optimize types
    for col in ["job_location", "job_company", "job_category"]:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def save_jobs_to_s3_parquet(config, jobs_df):
    """Save jobs DataFrame to S3 as Parquet, partitioned by date, deduplicated by job_id."""
    if jobs_df.empty:
        return {"new_jobs": 0, "files_written": 0}
    jobs_df["extraction_date"] = datetime.now().date()
    jobs_df["extraction_timestamp"] = datetime.now()
    s3_path = f"s3://{config['s3_bucket']}/{config['s3_processed_prefix']}/"
    try:
        result = wr.s3.to_parquet(
            df=jobs_df,
            path=s3_path,
            dataset=True,
            partition_cols=["extraction_date"],
            mode="append",
            database=config["glue_database"],
            table=config["glue_table"],
            merge_column="job_id",
            compression="snappy",
            max_rows_by_file=50000,
            sanitize_columns=True
        )
        return {
            "new_jobs": len(jobs_df),
            "files_written": len(result["paths"]),
            "table_updated": True
        }
    except Exception as e:
        print(f"Error saving to data lake: {e}")
        return {"new_jobs": 0, "files_written": 0, "error": str(e)}


def lambda_handler(event, context):
    """AWS Lambda handler for Adzuna job extraction pipeline."""
    config = get_config()
    dynamodb = boto3.resource("dynamodb")
    state = get_state(dynamodb, config["dynamodb_state_table"])
    extraction_window = {
        "start_time": datetime.fromisoformat(state["last_extraction_time"]) - timedelta(hours=config["overlap_hours"]),
        "end_time": datetime.now()
    }
    total_jobs_processed = 0
    for jobs_batch in fetch_jobs_from_adzuna(config, extraction_window):
        if not jobs_batch.empty:
            filtered_batch = jobs_batch[
                (jobs_batch["job_created"] >= extraction_window["start_time"]) &
                (jobs_batch["job_created"] <= extraction_window["end_time"])
            ]
            if not filtered_batch.empty:
                result = save_jobs_to_s3_parquet(config, filtered_batch)
                total_jobs_processed += result.get("new_jobs", 0)
    update_state(
        dynamodb,
        config["dynamodb_state_table"],
        {
            "last_extraction_time": datetime.now().isoformat(),
            "total_jobs_extracted": state["total_jobs_extracted"] + total_jobs_processed
        }
    )
    return {
        "statusCode": 200,
        "body": json.dumps({
            "success": True,
            "jobs_processed": total_jobs_processed,
            "extraction_window_start": extraction_window["start_time"].isoformat(),
            "extraction_window_end": extraction_window["end_time"].isoformat()
        })
    }